"""Google Drive catalog builder.

Lists files from the configured Drive folders, parses their names into
calendar-style keys (cycles, months, quarters), and exposes a cached catalog
suitable for the frontend's date pickers.
"""
from __future__ import annotations

import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_CACHE_TTL = timedelta(minutes=30)

_DEFAULT_FOLDERS = {
    "hrrr_forecast": "1yuEH5020Nh-Km5_PvYfmVpWTQIhzI1Iz",
    # 15-min quarter product (drive_uploader HRRR_HIST_MAIN / HRRR_HIST_ARCHIVE).
    # Repointed 2026-07 — the old IDs held the pre-refactor hourly CONUS files.
    "hrrr_history_main": "1y6-08xMbNUYX9coEYWZsCHTo3GYn8yNj",
    "hrrr_history_archive": "1sGBshGAmcpFVHRg5pGtrd5TSlsOGKqL6",
    # Hourly product (drive_uploader HRRR_HIST_HOURLY_MAIN / HRRR_HIST_HOURLY_ARCHIVE).
    "hrrr_history_hourly_main": "1ASjkTa_EHfWbkXDpVwwX8vM13YkZ2KAK",
    "hrrr_history_hourly_archive": "1jkkzUCtxVoKZ9MLfSCV2rLH761Jd3Qou",
    "noaa_main": "1kAOe-dGHByzZHijHGo8rmL7x4KY6OMav",
    "noaa_archive": "1TTa-bDV88sSf4strSW649UHPRddMHJtr",
    "era5_main": "1jN1NP3b5Nby-gpy5w1rqe2cgctESxqO-",
    "era5_archive": "1PD_y38k6x8HjDR8Wv-15NsZ6pdZ9pVPz",
    "era5_quarterly": "12U8PNHHGIxCy8_GRzsF2KxZ4GneMWy6h",
    "era5_history_zip": "1O8VjwFKXCJ3DR56_UEep-rXyb7OHNGMZ",
    # Curated historical extreme-temperature events, one subfolder per ISO zone.
    # Each event ships a .pww and a matching .mp4 animation.
    "extreme_events": "1qDXPh1yu5XpzJPWFKBDDawdpcktXhA7V",
}

_DEFAULT_CREDENTIALS_PATH = "/app/credentials/service_account.json"


def _folder_id(env_key: str, default_key: str) -> str:
    return os.environ.get(env_key, _DEFAULT_FOLDERS[default_key])


def _credentials_path() -> str:
    return os.environ.get("GDRIVE_CREDENTIALS_JSON", _DEFAULT_CREDENTIALS_PATH)


# ---------------------------------------------------------------------------
# File name patterns
# ---------------------------------------------------------------------------

_RE_HRRR_FORECAST = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2})Z_sfc_48_CONUS\.zip$", re.IGNORECASE)
# Current 15-min product (drive_uploader): daily "YYYY-MM-DD_subh_15min_CONUS.zip",
# monthly "YYYY-MM_subh_15min_CONUS.zip".
_RE_HRRR_HIST15_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_subh_15min_CONUS\.[A-Za-z0-9.]+$", re.IGNORECASE)
_RE_HRRR_HIST15_MONTH = re.compile(r"^(\d{4})-(\d{2})_subh_15min_CONUS\.[A-Za-z0-9.]+$", re.IGNORECASE)
# Hourly product: daily bare "YYYY-MM-DD_hourly_CONUS.pww", monthly "YYYY-MM_hourly_CONUS.zip".
_RE_HRRR_HOURLY_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_hourly_CONUS\.[A-Za-z0-9.]+$", re.IGNORECASE)
_RE_HRRR_HOURLY_MONTH = re.compile(r"^(\d{4})-(\d{2})_hourly_CONUS\.[A-Za-z0-9.]+$", re.IGNORECASE)
# Legacy pre-refactor names, kept as a fallback so any leftover files still list.
_RE_HRRR_HISTORY_MONTH = re.compile(r"^CONUS_?(\d{4})_(\d{2})\.[A-Za-z0-9.]+$", re.IGNORECASE)
_RE_HRRR_HISTORY_DAY = re.compile(r"^CONUS_(\d{4})_(\d{2})_(\d{2})\.[A-Za-z0-9.]+$", re.IGNORECASE)
_RE_NOAA = re.compile(r"Forecast_NorthAmerica_Run(\d{4}-\d{2}-\d{2})T(\d{2})Z\.pww$", re.IGNORECASE)
# Extreme events: "YYYY-MM-DD_Event_Title_ZONE.pww" (+ matching .mp4), and
# "coverage_ZONE.png".  Zone names themselves contain underscores
# (NYISO_ISONE), so the zone is matched against the known list longest-first
# rather than by splitting on the last underscore.
_EXTREME_ZONES = (
    "NYISO_ISONE", "NorthAmerica", "Northwest", "Southeast", "Southwest",
    "CAISO", "MISO", "PJM", "SPP", "Texas",
)
_RE_EXTREME = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)\.(pww|mp4)$", re.IGNORECASE)
_RE_EXTREME_COVERAGE = re.compile(r"^coverage_(.+)\.png$", re.IGNORECASE)

_RE_ERA5_QUARTER = re.compile(r"(\d{4})[^0-9]{0,4}Q(\d)", re.IGNORECASE)
_RE_ERA5_TX = re.compile(r"(texas|_tx[_\.\b]|northtexas|tx_)", re.IGNORECASE)
_RE_ERA5_NA = re.compile(r"(northamerica|north_america|_na[_\.\b])", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Drive client
# ---------------------------------------------------------------------------


class DriveClient:
    """Thin wrapper around the Drive v3 API for listing folders."""

    def __init__(self, credentials_path: str | None = None) -> None:
        self._credentials_path = credentials_path or _credentials_path()
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        content = os.environ.get("GDRIVE_CREDENTIALS_JSON_CONTENT")
        if content:
            import json as _json
            info = _json.loads(content)
            creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
        elif os.path.exists(self._credentials_path):
            creds = Credentials.from_service_account_file(
                self._credentials_path, scopes=_SCOPES
            )
        else:
            raise FileNotFoundError(
                f"Service account credentials not found at {self._credentials_path}"
            )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def list_files(self, folder_id: str, *, recursive: bool = True, max_depth: int = 4) -> list[dict[str, Any]]:
        """List every non-trashed file in ``folder_id`` (recursing into subfolders).

        Returns a list of ``{id, name, webContentLink, createdTime}`` dicts. On
        any Drive error an empty list is returned and the failure is logged.
        """
        if not folder_id:
            return []

        try:
            service = self._get_service()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[catalog] Drive auth failed: {exc}", file=sys.stderr)
            return []

        files: list[dict[str, Any]] = []
        # BFS over folder tree
        queue: list[tuple[str, int]] = [(folder_id, 0)]
        visited: set[str] = set()
        fields = "nextPageToken, files(id, name, webContentLink, createdTime, mimeType)"

        while queue:
            current_folder, depth = queue.pop(0)
            if current_folder in visited:
                continue
            visited.add(current_folder)

            page_token: str | None = None
            query = f"'{current_folder}' in parents and trashed = false"
            try:
                while True:
                    resp = (
                        service.files()
                        .list(
                            q=query,
                            fields=fields,
                            pageSize=1000,
                            pageToken=page_token,
                            supportsAllDrives=True,
                            includeItemsFromAllDrives=True,
                        )
                        .execute()
                    )
                    for item in resp.get("files", []):
                        if item.get("mimeType") == "application/vnd.google-apps.folder":
                            if recursive and depth < max_depth and item.get("id"):
                                queue.append((item["id"], depth + 1))
                            continue
                        files.append(
                            {
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "webContentLink": item.get("webContentLink")
                                or _direct_download_url(item.get("id")),
                                "createdTime": item.get("createdTime"),
                            }
                        )
                    page_token = resp.get("nextPageToken")
                    if not page_token:
                        break
            except HttpError as exc:
                print(
                    f"[catalog] Drive list_files failed for folder {current_folder}: {exc}",
                    file=sys.stderr,
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive
                print(
                    f"[catalog] Unexpected error listing folder {current_folder}: {exc}",
                    file=sys.stderr,
                )
                continue

        return files


def _direct_download_url(file_id: str | None) -> str | None:
    if not file_id:
        return None
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ---------------------------------------------------------------------------
# Catalog construction
# ---------------------------------------------------------------------------


def _empty_catalog() -> dict[str, dict[str, Any]]:
    return {
        "hrrr_forecast": {"cycles": [], "file_ids": {}},
        "hrrr_history": {"months": [], "file_ids": {}},
        "hrrr_history_current": {"days": [], "file_ids": {}},
        "hrrr_history_archive": {"months": [], "file_ids": {}},
        "hrrr_history_hourly_current": {"days": [], "file_ids": {}},
        "hrrr_history_hourly_archive": {"months": [], "file_ids": {}},
        "noaa_forecast": {"cycles": [], "file_ids": {}},
        "noaa_forecast_recent": {"cycles": [], "file_ids": {}},
        "noaa_forecast_archive": {"cycles": [], "file_ids": {}},
        "era5_na": {"quarters": [], "file_ids": {}},
        "era5_tx": {"quarters": [], "file_ids": {}},
        "extreme_events": {
            "keys": [], "zones": [], "events": {},
            "coverage": {}, "file_ids": {}, "video_ids": {},
        },
    }


def _entry(file_obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": file_obj.get("id"),
        "webContentLink": file_obj.get("webContentLink")
        or _direct_download_url(file_obj.get("id")),
    }


def _build_hrrr_forecast(client: DriveClient) -> dict[str, Any]:
    folder = _folder_id("GDRIVE_HRRR_FORECAST_FOLDER_ID", "hrrr_forecast")
    out: dict[str, Any] = {"cycles": [], "file_ids": {}}
    seen: dict[str, dict[str, Any]] = {}

    for f in client.list_files(folder):
        name = f.get("name") or ""
        m = _RE_HRRR_FORECAST.search(name)
        if not m:
            continue
        cycle = f"{m.group(1)}T{m.group(2)}Z"
        if cycle not in seen:
            seen[cycle] = _entry(f)

    cycles_sorted = sorted(seen.keys(), reverse=True)
    out["cycles"] = cycles_sorted
    out["file_ids"] = {c: seen[c] for c in cycles_sorted}
    return out


def _hist15_day_key(name: str) -> str | None:
    """YYYY-MM-DD from a 15-min daily name (new pattern, legacy CONUS_ fallback)."""
    m = _RE_HRRR_HIST15_DAY.match(name) or _RE_HRRR_HISTORY_DAY.match(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _hist15_month_key(name: str) -> str | None:
    """YYYY-MM from a 15-min monthly name (new pattern, legacy CONUS_ fallback)."""
    m = _RE_HRRR_HIST15_MONTH.match(name) or _RE_HRRR_HISTORY_MONTH.match(name)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def _pack_days(d: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(d.keys(), reverse=True)
    return {"days": keys, "file_ids": {k: d[k] for k in keys}}


def _pack_months(d: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = sorted(d.keys(), reverse=True)
    return {"months": keys, "file_ids": {k: d[k] for k in keys}}


def _build_hrrr_history(client: DriveClient) -> dict[str, dict[str, Any]]:
    """15-min HRRR history: current-year daily zips + past-year monthly zips."""
    main_folder = _folder_id("GDRIVE_HRRR_HISTORY_FOLDER_ID", "hrrr_history_main")
    archive_folder = _folder_id(
        "GDRIVE_HRRR_HISTORY_ARCHIVE_FOLDER_ID", "hrrr_history_archive"
    )

    current_days: dict[str, dict[str, Any]] = {}
    for f in client.list_files(main_folder):
        key = _hist15_day_key(f.get("name") or "")
        if key:
            current_days.setdefault(key, _entry(f))

    archive_months: dict[str, dict[str, Any]] = {}
    for f in client.list_files(archive_folder):
        name = f.get("name") or ""
        key = _hist15_month_key(name)
        if key:
            archive_months.setdefault(key, _entry(f))
            continue
        # A stray daily file in the archive folder rolls into its month bucket.
        dkey = _hist15_day_key(name)
        if dkey:
            archive_months.setdefault(dkey[:7], _entry(f))

    # Combined view: roll current daily into months, merge with archive.
    current_as_months: dict[str, dict[str, Any]] = {}
    for day_key, entry in current_days.items():
        current_as_months.setdefault(day_key[:7], entry)
    combined = {**archive_months, **current_as_months}

    return {
        "hrrr_history": _pack_months(combined),
        "hrrr_history_current": _pack_days(current_days),
        "hrrr_history_archive": _pack_months(archive_months),
    }


def _build_hrrr_history_hourly(client: DriveClient) -> dict[str, dict[str, Any]]:
    """Hourly HRRR history: current-year daily bare .pww + past-year monthly zips."""
    main_folder = _folder_id(
        "GDRIVE_HRRR_HISTORY_HOURLY_FOLDER_ID", "hrrr_history_hourly_main"
    )
    archive_folder = _folder_id(
        "GDRIVE_HRRR_HISTORY_HOURLY_ARCHIVE_FOLDER_ID", "hrrr_history_hourly_archive"
    )

    days: dict[str, dict[str, Any]] = {}
    for f in client.list_files(main_folder):
        m = _RE_HRRR_HOURLY_DAY.match(f.get("name") or "")
        if m:
            days.setdefault(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", _entry(f))

    months: dict[str, dict[str, Any]] = {}
    for f in client.list_files(archive_folder):
        name = f.get("name") or ""
        m = _RE_HRRR_HOURLY_MONTH.match(name)
        if m:
            months.setdefault(f"{m.group(1)}-{m.group(2)}", _entry(f))
            continue
        md = _RE_HRRR_HOURLY_DAY.match(name)
        if md:
            months.setdefault(f"{md.group(1)}-{md.group(2)}", _entry(f))

    return {
        "hrrr_history_hourly_current": _pack_days(days),
        "hrrr_history_hourly_archive": _pack_months(months),
    }


def _build_noaa(client: DriveClient) -> dict[str, dict[str, Any]]:
    # Hardcoded — ignore env var overrides since Railway has stale/wrong values set
    main_folder = "1kAOe-dGHByzZHijHGo8rmL7x4KY6OMav"
    archive_folder = "1TTa-bDV88sSf4strSW649UHPRddMHJtr"

    def _scan(folder: str) -> dict[str, dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for f in client.list_files(folder):
            name = f.get("name") or ""
            m = _RE_NOAA.search(name)
            if not m:
                continue
            cycle = f"{m.group(1)}T{m.group(2)}Z"
            seen.setdefault(cycle, _entry(f))
        return seen

    def _pack(d: dict[str, dict[str, Any]]) -> dict[str, Any]:
        keys = sorted(d.keys(), reverse=True)
        return {"cycles": keys, "file_ids": {k: d[k] for k in keys}}

    recent = _scan(main_folder)        # ONLY the recent/main folder
    archive = _scan(archive_folder)    # ONLY the archive folder
    combined = {**archive, **recent}   # recent wins on overlap

    return {
        "noaa_forecast": _pack(combined),
        "noaa_forecast_recent": _pack(recent),
        "noaa_forecast_archive": _pack(archive),
    }


def _build_era5(client: DriveClient) -> dict[str, dict[str, Any]]:
    folders = [
        _folder_id("GDRIVE_ERA5_QUARTERLY_FOLDER_ID", "era5_quarterly"),
        _folder_id("GDRIVE_ERA5_HISTORY_ZIP_FOLDER_ID", "era5_history_zip"),
        _folder_id("GDRIVE_ERA5_ARCHIVE_FOLDER_ID", "era5_archive"),
    ]

    na: dict[str, dict[str, Any]] = {}
    tx: dict[str, dict[str, Any]] = {}

    for folder in folders:
        for f in client.list_files(folder):
            name = f.get("name") or ""
            m = _RE_ERA5_QUARTER.search(name)
            if not m:
                continue
            quarter = f"{m.group(1)}-Q{m.group(2)}"

            bucket = na
            if _RE_ERA5_TX.search(name):
                bucket = tx
            elif _RE_ERA5_NA.search(name):
                bucket = na

            if quarter not in bucket:
                bucket[quarter] = _entry(f)

    def pack(d: dict[str, dict[str, Any]]) -> dict[str, Any]:
        keys = sorted(d.keys(), reverse=True)
        return {"quarters": keys, "file_ids": {k: d[k] for k in keys}}

    return {"era5_na": pack(na), "era5_tx": pack(tx)}


def _split_extreme_zone(stem: str) -> tuple[str, str]:
    """Split "Event_Title_ZONE" into ``(title, zone)``.

    Zone names contain underscores, so the known zones are tried longest-first.
    Files with no zone suffix (the 1899 continent-wide event) fall back to
    NorthAmerica.
    """
    for zone in sorted(_EXTREME_ZONES, key=len, reverse=True):
        if stem.endswith("_" + zone):
            return stem[: -len(zone) - 1], zone
        if stem == zone:
            return stem, zone
    return stem, "NorthAmerica"


def _build_extreme(client: DriveClient) -> dict[str, Any]:
    """Curated historical extreme-temperature events, grouped by ISO zone.

    Each event contributes a ``.pww`` (the data) and usually a matching ``.mp4``
    animation; the two are paired on the event key.  ``coverage_ZONE.png`` files
    describe each zone's extent.  The same event can appear in several zone
    subfolders (the 1899 outbreak does), so entries are deduplicated by key.
    """
    folder = _folder_id("GDRIVE_EXTREME_FOLDER_ID", "extreme_events")

    pww: dict[str, dict[str, Any]] = {}
    mp4: dict[str, dict[str, Any]] = {}
    meta: dict[str, dict[str, str]] = {}
    coverage: dict[str, dict[str, Any]] = {}

    for f in client.list_files(folder):
        name = f.get("name") or ""

        cov = _RE_EXTREME_COVERAGE.match(name)
        if cov:
            coverage.setdefault(cov.group(1), _entry(f))
            continue

        m = _RE_EXTREME.match(name)
        if not m:
            continue
        date, stem, ext = m.group(1), m.group(2), m.group(3).lower()
        title, zone = _split_extreme_zone(stem)
        key = f"{date}_{stem}"

        if ext == "pww":
            pww.setdefault(key, _entry(f))
        else:
            mp4.setdefault(key, _entry(f))
        meta.setdefault(key, {
            "key": key,
            "date": date,
            "title": title.replace("_", " ").strip(),
            "zone": zone,
        })

    # Only events with actual data are listed; a stray .mp4 is not an event.
    keys = sorted(pww.keys(), key=lambda k: (meta[k]["date"], k), reverse=True)

    events: dict[str, list[dict[str, Any]]] = {}
    for k in keys:
        info = dict(meta[k])
        info["has_video"] = k in mp4
        events.setdefault(info["zone"], []).append(info)

    zones = sorted(events.keys())
    return {
        "keys": keys,
        "zones": zones,
        "events": events,
        "coverage": coverage,
        "file_ids": {k: pww[k] for k in keys},
        "video_ids": {k: mp4[k] for k in keys if k in mp4},
    }


def build_catalog() -> dict[str, Any]:
    """Build the full catalog by listing every relevant Drive folder."""
    client = DriveClient()
    catalog = _empty_catalog()

    try:
        catalog["hrrr_forecast"] = _build_hrrr_forecast(client)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] hrrr_forecast failed: {exc}", file=sys.stderr)

    try:
        hrrr = _build_hrrr_history(client)
        catalog["hrrr_history"] = hrrr["hrrr_history"]
        catalog["hrrr_history_current"] = hrrr["hrrr_history_current"]
        catalog["hrrr_history_archive"] = hrrr["hrrr_history_archive"]
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] hrrr_history failed: {exc}", file=sys.stderr)

    try:
        hourly = _build_hrrr_history_hourly(client)
        catalog["hrrr_history_hourly_current"] = hourly["hrrr_history_hourly_current"]
        catalog["hrrr_history_hourly_archive"] = hourly["hrrr_history_hourly_archive"]
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] hrrr_history_hourly failed: {exc}", file=sys.stderr)

    try:
        noaa = _build_noaa(client)
        catalog["noaa_forecast"] = noaa["noaa_forecast"]
        catalog["noaa_forecast_recent"] = noaa["noaa_forecast_recent"]
        catalog["noaa_forecast_archive"] = noaa["noaa_forecast_archive"]
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] noaa_forecast failed: {exc}", file=sys.stderr)

    try:
        era5 = _build_era5(client)
        catalog["era5_na"] = era5["era5_na"]
        catalog["era5_tx"] = era5["era5_tx"]
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] era5 failed: {exc}", file=sys.stderr)

    try:
        catalog["extreme_events"] = _build_extreme(client)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] extreme_events failed: {exc}", file=sys.stderr)

    return catalog


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_catalog_cache: dict[str, Any] | None = None
_cache_time: datetime | None = None
_cache_lock = threading.Lock()


def _cache_is_fresh() -> bool:
    if _catalog_cache is None or _cache_time is None:
        return False
    return datetime.now(timezone.utc) - _cache_time < _CACHE_TTL


def get_catalog() -> dict[str, Any]:
    """Return the cached catalog, rebuilding if stale or missing."""
    global _catalog_cache, _cache_time
    with _cache_lock:
        if _cache_is_fresh() and _catalog_cache is not None:
            return _catalog_cache
        try:
            built = build_catalog()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[catalog] build_catalog failed: {exc}", file=sys.stderr)
            built = _catalog_cache or _empty_catalog()
        _catalog_cache = built
        _cache_time = datetime.now(timezone.utc)
        return _catalog_cache


def refresh_catalog() -> dict[str, Any]:
    """Force a rebuild of the catalog and return the new value."""
    global _catalog_cache, _cache_time
    with _cache_lock:
        try:
            built = build_catalog()
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[catalog] refresh_catalog failed: {exc}", file=sys.stderr)
            built = _empty_catalog()
        _catalog_cache = built
        _cache_time = datetime.now(timezone.utc)
        return _catalog_cache


def cache_age_seconds() -> float | None:
    if _cache_time is None:
        return None
    return (datetime.now(timezone.utc) - _cache_time).total_seconds()
