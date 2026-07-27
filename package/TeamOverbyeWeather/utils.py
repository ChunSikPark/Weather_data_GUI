"""Utility helpers for TeamOverbyeWeather."""

from __future__ import annotations

import datetime as _dt
import os
import re
import time
import urllib.parse
from pathlib import Path

import requests
from tqdm import tqdm

from .errors import RegionTooLargeError, ServerBusyError, WeatherAPIError

_CHUNK = 1 << 20  # 1 MiB


def server_detail(resp: requests.Response) -> tuple[str, str]:
    """Extract ``(detail, sdk_hint)`` from a FastAPI error body."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:500] or resp.reason, ""
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        return str(detail.get("detail", detail)), str(detail.get("sdk_hint", ""))
    return str(detail), ""


def _filename_from_headers(resp: requests.Response) -> str | None:
    """Read the filename the server suggested via Content-Disposition.

    The value is reduced to a bare filename: it is attacker-controlled whenever
    the client talks to an untrusted or redirected host, and both ``..`` and an
    absolute path would otherwise escape the destination directory (``Path(d) /
    "/etc/x"`` discards ``d`` entirely).  Percent-encoding is decoded *before*
    stripping, so ``%2e%2e%2f`` cannot smuggle a separator through.
    """
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if not m:
        return None
    name = urllib.parse.unquote(m.group(1)).strip()
    name = os.path.basename(name.replace("\\", "/").split(":")[-1]).strip()
    return name or None


def safe_target(dest_dir: Path | str, name: str) -> Path:
    """Resolve *name* inside *dest_dir*, refusing anything that escapes it.

    Args:
        dest_dir: Directory the file must land in.
        name: Candidate filename (already reduced to a basename).

    Returns:
        The absolute path to write to.

    Raises:
        ValueError: If the resolved path falls outside *dest_dir*.
    """
    base = Path(dest_dir).resolve()
    target = (base / name).resolve()
    if target == base or base not in target.parents:
        raise ValueError(
            f"Refusing to write {name!r}: resolves outside the destination "
            f"directory {str(base)!r}."
        )
    return target


def download_file(
    url: str,
    dest_path: Path | str | None = None,
    show_progress: bool = True,
    dest_dir: Path | str | None = None,
    max_retries: int = 3,
) -> Path:
    """Stream a download to disk, retrying while the server queue is full.

    Either *dest_path* (exact target) or *dest_dir* (name taken from the
    server's ``Content-Disposition``) must be given.

    A 503 means the bounded download queue is full — transient, so it is retried
    after ``Retry-After``.  A 413 means the request is genuinely too big to crop
    server-side and is raised as :class:`RegionTooLargeError` for the caller to
    handle (the client falls back to a local crop).

    Args:
        url: Fully-formed request URL.
        dest_path: Exact file path to write.
        show_progress: Show a tqdm progress bar.
        dest_dir: Directory to write into, naming the file from the response.
        max_retries: How many times to retry a queue-full (503) response.

    Returns:
        Path to the saved file.

    Raises:
        RegionTooLargeError: Server refused a CONUS-scale crop (413).
        ServerBusyError: Queue stayed full across every retry (503).
        WeatherAPIError: Any other non-2xx response.
    """
    if (dest_path is None) == (dest_dir is None):
        raise ValueError("Provide exactly one of dest_path or dest_dir")

    for attempt in range(max_retries + 1):
        with requests.get(url, allow_redirects=True, stream=True, timeout=(30, 900)) as resp:
            if resp.status_code == 503 and attempt < max_retries:
                wait = float(resp.headers.get("retry-after", 5))
                print(f"Server queue full, retrying in {wait:.0f}s "
                      f"({attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue

            if not resp.ok:
                detail, hint = server_detail(resp)
                if resp.status_code == 413:
                    raise RegionTooLargeError(detail, hint)
                if resp.status_code == 503:
                    raise ServerBusyError(detail)
                raise WeatherAPIError(resp.status_code, detail)

            if dest_path is not None:
                target = Path(dest_path)
                target.parent.mkdir(parents=True, exist_ok=True)
            else:
                # The name comes from the server, so confine it to dest_dir.
                Path(dest_dir).mkdir(parents=True, exist_ok=True)
                name = _filename_from_headers(resp) or "download.bin"
                target = safe_target(dest_dir, name)

            total = int(resp.headers.get("content-length", 0)) or None
            with open(target, "wb") as fh:
                if show_progress:
                    with tqdm(total=total, unit="B", unit_scale=True,
                              unit_divisor=1024, desc=target.name) as bar:
                        for chunk in resp.iter_content(chunk_size=_CHUNK):
                            if chunk:
                                fh.write(chunk)
                                bar.update(len(chunk))
                else:
                    for chunk in resp.iter_content(chunk_size=_CHUNK):
                        if chunk:
                            fh.write(chunk)
            return target


def to_iso(value) -> str:
    """Normalise a time bound to the ISO string the API expects.

    Accepts a :class:`datetime.datetime`, :class:`datetime.date`, or an ISO
    string.  Naive datetimes are treated as UTC (matching the server).

    Raises:
        ValueError: If the value is not a recognisable datetime.
    """
    if isinstance(value, _dt.datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day).isoformat()
    if isinstance(value, str):
        try:
            _dt.datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(
                f"Invalid time {value!r}. Use ISO format "
                f"('2026-07-22T12:00:00') or a datetime object."
            )
        return value
    raise ValueError(f"Invalid time {value!r}. Use an ISO string or a datetime.")


def to_epoch(value) -> float:
    """Convert a time bound to Unix epoch seconds (for local cropping)."""
    dt = _dt.datetime.fromisoformat(to_iso(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt.timestamp()


def parse_quarter(q: str) -> tuple[int, int]:
    """Parse a quarter string like ``"2025-Q1"`` into ``(2025, 1)``.

    Raises:
        ValueError: If the string does not match ``YYYY-QN``.
    """
    match = re.fullmatch(r"(\d{4})-Q([1-4])", q.strip())
    if not match:
        raise ValueError(
            f"Invalid quarter format {q!r}. Expected format: 'YYYY-QN' (e.g. '2025-Q1')."
        )
    return int(match.group(1)), int(match.group(2))


def quarter_to_source_key(region: str) -> str:
    """Map an ERA5 region name to its catalog source key.

    Raises:
        ValueError: If region is not ``"north_america"`` or ``"texas"``.
    """
    mapping = {"north_america": "era5_na", "texas": "era5_tx"}
    if region not in mapping:
        raise ValueError(f"Unknown region {region!r}. Valid options: {list(mapping.keys())}.")
    return mapping[region]


def validate_region_args(region_ids, region_layer, bbox):
    """Validate that exactly one of (region_ids, bbox) is given and layer is valid."""
    have_ids = region_ids is not None
    have_bbox = bbox is not None
    if have_ids and have_bbox:
        raise ValueError("Provide exactly one of region_ids or bbox, not both")
    if not have_ids and not have_bbox:
        raise ValueError("Provide region_ids or bbox")
    if have_ids and region_layer not in ("states", "iso"):
        raise ValueError("region_layer must be 'states' or 'iso' when region_ids is given")
