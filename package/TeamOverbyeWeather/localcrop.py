"""Client-side crop for files the server refuses to crop (CONUS-scale archives).

Mirrors ``fetch_and_crop`` in ``backend/download.py``, but reads from a file on
disk instead of Drive.  Handles every on-disk shape by *content*, not by source
name:

* bare ``.pww``                     — ERA5, NOAA, hourly HRRR history
* zip with one ``.pww``             — HRRR forecast
* zip with four quarter ``.pww``    — HRRR history 15-min daily (stitched)
* zip of daily zips                 — HRRR history 15-min monthly (recursed)

Members are cropped one at a time and concatenated along the time axis, so peak
memory is one cropped member rather than a whole month.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import pww_io


def _quarter_of(name: str) -> tuple:
    """Sort key putting ``..._Q1_...`` .. ``_Q4_`` in ascending time order.

    Falls back to the plain name so daily members inside a monthly archive sort
    by date (``2026-05-01_...`` before ``2026-05-02_...``).
    """
    base = os.path.basename(name)
    m = re.search(r"_Q(\d)_", base)
    return (base[: m.start()] if m else base, int(m.group(1)) if m else 0, base)


def _extract_members(zip_path: str, workdir: str) -> list[str]:
    """Extract every ``.pww`` from a zip to *workdir*, recursing into nested zips.

    Returns paths in ascending time order.  The caller owns *workdir*.
    """
    out: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(zf.namelist(), key=_quarter_of)
        pww_names = [n for n in names if n.lower().endswith(".pww")]
        zip_names = [n for n in names if n.lower().endswith(".zip")]

        for n in pww_names:
            fd, path = tempfile.mkstemp(suffix=".pww", dir=workdir)
            with os.fdopen(fd, "wb") as dst, zf.open(n) as src:
                shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
            out.append(path)

        # Monthly archives are zips of daily zips — recurse one level per member.
        for n in zip_names:
            fd, nested = tempfile.mkstemp(suffix=".zip", dir=workdir)
            with os.fdopen(fd, "wb") as dst, zf.open(n) as src:
                shutil.copyfileobj(src, dst, length=8 * 1024 * 1024)
            try:
                out.extend(_extract_members(nested, workdir))
            finally:
                os.unlink(nested)

    if not out:
        raise ValueError(f"No .pww file found inside {os.path.basename(zip_path)}")
    return out


def crop_file(
    src_path: str | Path,
    dest_path: str | Path,
    bbox: tuple | None = None,
    t_start: float | None = None,
    t_end: float | None = None,
) -> Path:
    """Crop a downloaded PWW/ZIP to *bbox* and/or a Unix-epoch time range.

    Args:
        src_path: Downloaded ``.pww`` or ``.zip``.
        dest_path: Where to write the cropped ``.pww``.
        bbox: ``(lat_max, lon_min, lat_min, lon_max)``; ``None`` keeps the full grid.
        t_start: Unix epoch seconds; ``None`` keeps from the first timestep.
        t_end: Unix epoch seconds; ``None`` keeps through the last timestep.

    Returns:
        Path to the written ``.pww``.
    """
    src_path = Path(src_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(src_path):
        workdir = tempfile.mkdtemp(prefix="towx_crop_")
        try:
            members = _extract_members(str(src_path), workdir)
            pieces = []
            for mp in members:
                h, s, a = pww_io.read_pww_file(mp)
                pieces.append(pww_io.crop_to_bbox(h, s, a, bbox) if bbox else (h, s, a))
                os.unlink(mp)
            header, stations, arr = pww_io.concat_time(pieces)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    else:
        header, stations, arr = pww_io.read_pww_file(str(src_path))
        if bbox:
            header, stations, arr = pww_io.crop_to_bbox(header, stations, arr, bbox)

    if t_start is not None or t_end is not None:
        ts = t_start if t_start is not None else header["date_min"]
        te = t_end if t_end is not None else header["date_max"]
        header, arr = pww_io.crop_to_timerange(header, arr, ts, te)

    dest_path.write_bytes(pww_io.write_pww(header, stations, arr))
    return dest_path
