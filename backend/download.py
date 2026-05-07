"""Download helpers: ZIP bundling and direct URL lookup."""
from __future__ import annotations

import io
import sys
import zipfile
from collections.abc import Iterable
from typing import Any

import httpx
from fastapi import HTTPException


# Source identifier -> (catalog key, key field name on the catalog entry)
_SOURCE_LOOKUP: dict[str, dict[str, str]] = {
    "hrrr_forecast": {"catalog_key": "hrrr_forecast", "list_key": "cycles"},
    "hrrr_history": {"catalog_key": "hrrr_history", "list_key": "months"},
    "hrrr_history_current": {"catalog_key": "hrrr_history_current", "list_key": "days"},
    "hrrr_history_archive": {"catalog_key": "hrrr_history_archive", "list_key": "months"},
    "noaa_forecast": {"catalog_key": "noaa_forecast", "list_key": "cycles"},
    "noaa_forecast_recent": {"catalog_key": "noaa_forecast_recent", "list_key": "cycles"},
    "noaa_forecast_archive": {"catalog_key": "noaa_forecast_archive", "list_key": "cycles"},
    "era5_na": {"catalog_key": "era5_na", "list_key": "quarters"},
    "era5_tx": {"catalog_key": "era5_tx", "list_key": "quarters"},
}

# Default download filename pattern per source.
_FILENAME_PATTERNS: dict[str, str] = {
    "hrrr_forecast": "{key}_sfc_48_CONUS.zip",
    "hrrr_history": "{key}_sfc_01_CONUS.zip",
    "hrrr_history_current": "{key}_sfc_01_CONUS.zip",
    "hrrr_history_archive": "{key}_sfc_01_CONUS.zip",
    "noaa_forecast": "Forecast_NorthAmerica_Run{key}.pww",
    "noaa_forecast_recent": "Forecast_NorthAmerica_Run{key}.pww",
    "noaa_forecast_archive": "Forecast_NorthAmerica_Run{key}.pww",
    "era5_na": "ERA5_NorthAmerica_{key}.zip",
    "era5_tx": "ERA5_Texas_{key}.zip",
}


def _resolve_section(source: str, catalog: dict[str, Any]) -> dict[str, Any]:
    info = _SOURCE_LOOKUP.get(source)
    if info is None:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    section = catalog.get(info["catalog_key"])
    if not isinstance(section, dict):
        raise HTTPException(status_code=404, detail=f"No catalog entry for {source}")
    return section


def _entry_for(source: str, date_key: str, catalog: dict[str, Any]) -> dict[str, Any]:
    section = _resolve_section(source, catalog)
    file_ids = section.get("file_ids") or {}
    entry = file_ids.get(date_key)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=f"No file for {source} {date_key}",
        )
    return entry


def get_file_url(source: str, date_key: str, catalog: dict[str, Any]) -> str:
    """Return the Drive download URL for a single (source, date_key) pair."""
    entry = _entry_for(source, date_key, catalog)
    url = entry.get("webContentLink")
    file_id = entry.get("id")
    if not url and file_id:
        url = f"https://drive.google.com/uc?export=download&id={file_id}"
    if not url:
        raise HTTPException(
            status_code=404,
            detail=f"No download link for {source} {date_key}",
        )
    return url


def _filename_for(source: str, date_key: str) -> str:
    pattern = _FILENAME_PATTERNS.get(source, "{key}.bin")
    return pattern.format(key=date_key)


def collect_entries(
    source: str, date_keys: Iterable[str], catalog: dict[str, Any]
) -> list[dict[str, str]]:
    """Resolve a list of (source, key) pairs into download entries.

    Each entry has ``name`` and ``url`` fields suitable for ``build_zip_stream``.
    """
    out: list[dict[str, str]] = []
    missing: list[str] = []
    for key in date_keys:
        try:
            url = get_file_url(source, key, catalog)
        except HTTPException:
            missing.append(key)
            continue
        out.append({"name": _filename_for(source, key), "url": url})
    if not out:
        raise HTTPException(
            status_code=404,
            detail=f"No files resolved for {source} ({', '.join(missing) or 'no keys'})",
        )
    return out


def build_zip_stream(file_entries: list[dict[str, str]]) -> io.BytesIO:
    """Fetch each file via HTTP and pack them into an in-memory ZIP archive.

    Returns a ``BytesIO`` positioned at offset 0. ``ZIP_STORED`` is used because
    the inputs are already compressed (.zip / .pww) so re-deflating is wasteful.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED) as zf:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            for entry in file_entries:
                name = entry["name"]
                url = entry["url"]
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(
                        f"[download] Failed to fetch {name} from {url}: {exc}",
                        file=sys.stderr,
                    )
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to fetch {name} from upstream",
                    )
                zf.writestr(name, resp.content)
    buf.seek(0)
    return buf


def iter_zip_chunks(buf: io.BytesIO, chunk_size: int = 64 * 1024) -> Iterable[bytes]:
    """Yield the contents of ``buf`` in fixed-size chunks for streaming."""
    while True:
        chunk = buf.read(chunk_size)
        if not chunk:
            break
        yield chunk


def zip_filename_for(source: str, date_keys: list[str]) -> str:
    """Construct a stable filename for the produced ZIP bundle."""
    if len(date_keys) == 1:
        return f"{source}_{date_keys[0]}.zip"
    return f"{source}_bundle_{len(date_keys)}_files.zip"


def parse_dates_param(dates: str | None) -> list[str]:
    if not dates:
        raise HTTPException(status_code=400, detail="Missing 'dates' query parameter")
    keys = [d.strip() for d in dates.split(",") if d.strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="No valid dates provided")
    return keys
