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
    "hrrr_history_main": "1Uc-tuSPEnh7rJzC3nFvxndFvULrsNe-U",
    "hrrr_history_archive": "1_govjuY2WV0TqHp_7PwVVtrGPCDU-I9v",
    "noaa_main": "1kAOe-dGHByzZHijHGo8rmL7x4KY6OMav",
    "noaa_archive": "1TTa-bDV88sSf4strSW649UHPRddMHJtr",
    "era5_main": "1jN1NP3b5Nby-gpy5w1rqe2cgctESxqO-",
    "era5_archive": "1PD_y38k6x8HjDR8Wv-15NsZ6pdZ9pVPz",
    "era5_quarterly": "12U8PNHHGIxCy8_GRzsF2KxZ4GneMWy6h",
    "era5_history_zip": "1O8VjwFKXCJ3DR56_UEep-rXyb7OHNGMZ",
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
_RE_HRRR_HISTORY_MONTH = re.compile(r"^(\d{4}-\d{2})_sfc_01_CONUS\.zip$", re.IGNORECASE)
_RE_HRRR_HISTORY_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})_sfc_01_CONUS(?:\.pww)?\.zip$", re.IGNORECASE)
_RE_NOAA = re.compile(r"Forecast_NorthAmerica_Run(\d{4}-\d{2}-\d{2})T(\d{2})Z\.pww$", re.IGNORECASE)
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

    def list_files(self, folder_id: str) -> list[dict[str, Any]]:
        """List every non-trashed file in ``folder_id``.

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
        page_token: str | None = None
        query = f"'{folder_id}' in parents and trashed = false"
        fields = "nextPageToken, files(id, name, webContentLink, createdTime, mimeType)"

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
                f"[catalog] Drive list_files failed for folder {folder_id}: {exc}",
                file=sys.stderr,
            )
            return files
        except Exception as exc:  # pragma: no cover - defensive
            print(
                f"[catalog] Unexpected error listing folder {folder_id}: {exc}",
                file=sys.stderr,
            )
            return files

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
        "noaa_forecast": {"cycles": [], "file_ids": {}},
        "era5_na": {"quarters": [], "file_ids": {}},
        "era5_tx": {"quarters": [], "file_ids": {}},
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


def _build_hrrr_history(client: DriveClient) -> dict[str, Any]:
    main_folder = _folder_id("GDRIVE_HRRR_HISTORY_FOLDER_ID", "hrrr_history_main")
    archive_folder = _folder_id(
        "GDRIVE_HRRR_HISTORY_ARCHIVE_FOLDER_ID", "hrrr_history_archive"
    )

    out: dict[str, Any] = {"months": [], "file_ids": {}}
    monthly: dict[str, dict[str, Any]] = {}

    for folder in (main_folder, archive_folder):
        for f in client.list_files(folder):
            name = f.get("name") or ""
            m = _RE_HRRR_HISTORY_MONTH.match(name)
            if m:
                month = m.group(1)
                if month not in monthly:
                    monthly[month] = _entry(f)
                continue
            # Daily files roll up into their month bucket only if no monthly bundle exists yet.
            d = _RE_HRRR_HISTORY_DAY.match(name)
            if d:
                month = d.group(1)[:7]
                monthly.setdefault(month, _entry(f))

    months_sorted = sorted(monthly.keys(), reverse=True)
    out["months"] = months_sorted
    out["file_ids"] = {m: monthly[m] for m in months_sorted}
    return out


def _build_noaa(client: DriveClient) -> dict[str, Any]:
    main_folder = _folder_id("GDRIVE_NOAA_FOLDER_ID", "noaa_main")
    archive_folder = _folder_id("GDRIVE_NOAA_ARCHIVE_FOLDER_ID", "noaa_archive")

    out: dict[str, Any] = {"cycles": [], "file_ids": {}}
    seen: dict[str, dict[str, Any]] = {}

    for folder in (main_folder, archive_folder):
        for f in client.list_files(folder):
            name = f.get("name") or ""
            m = _RE_NOAA.search(name)
            if not m:
                continue
            cycle = f"{m.group(1)}T{m.group(2)}Z"
            if cycle not in seen:
                seen[cycle] = _entry(f)

    cycles_sorted = sorted(seen.keys(), reverse=True)
    out["cycles"] = cycles_sorted
    out["file_ids"] = {c: seen[c] for c in cycles_sorted}
    return out


def _build_era5(client: DriveClient) -> dict[str, dict[str, Any]]:
    folders = [
        _folder_id("GDRIVE_ERA5_QUARTERLY_FOLDER_ID", "era5_quarterly"),
        _folder_id("GDRIVE_ERA5_HISTORY_ZIP_FOLDER_ID", "era5_history_zip"),
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


def build_catalog() -> dict[str, Any]:
    """Build the full catalog by listing every relevant Drive folder."""
    client = DriveClient()
    catalog = _empty_catalog()

    try:
        catalog["hrrr_forecast"] = _build_hrrr_forecast(client)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] hrrr_forecast failed: {exc}", file=sys.stderr)

    try:
        catalog["hrrr_history"] = _build_hrrr_history(client)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] hrrr_history failed: {exc}", file=sys.stderr)

    try:
        catalog["noaa_forecast"] = _build_noaa(client)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] noaa_forecast failed: {exc}", file=sys.stderr)

    try:
        era5 = _build_era5(client)
        catalog["era5_na"] = era5["era5_na"]
        catalog["era5_tx"] = era5["era5_tx"]
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[catalog] era5 failed: {exc}", file=sys.stderr)

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
