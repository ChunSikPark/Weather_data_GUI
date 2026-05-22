"""PWW VERSION 1/2 binary I/O — in-memory read, bbox crop, and write.

VERSION 1 (HRRR, NOAA): station block is grid metadata, not real lat/lon.
  Stations are skipped on read; output writes loc=0.
VERSION 2 (ERA5): station block has real lat/lon; filtered by crop bbox.
"""
from __future__ import annotations

import io
import struct

import numpy as np


def _read_cstring(f) -> str:
    buf = bytearray()
    while True:
        b = f.read(1)
        if not b or b == b"\x00":
            break
        buf.extend(b)
    return buf.decode("ascii", errors="replace")


def _parse_header_only(f) -> tuple[dict, int, int]:
    key1 = struct.unpack("<h", f.read(2))[0]
    key2 = struct.unpack("<h", f.read(2))[0]
    version = struct.unpack("<h", f.read(2))[0]
    if version < 1:
        raise ValueError(f"Unsupported PWW version {version}")

    date_min, date_max = struct.unpack("<dd", f.read(16))
    lat_min, lat_max, lon_min, lon_max = struct.unpack("<dddd", f.read(32))
    meta_count = struct.unpack("<h", f.read(2))[0]
    meta_strings = [_read_cstring(f) for _ in range(meta_count)]
    count, sample_sec, loc = struct.unpack("<iii", f.read(12))
    loc_fc, varcount = struct.unpack("<hh", f.read(4))
    var_codes = list(struct.unpack(f"<{varcount}h", f.read(varcount * 2)))
    if version >= 2:
        _bytecount = struct.unpack("<h", f.read(2))[0]
        _valid_cnt = struct.unpack(f"<{_bytecount}i", f.read(_bytecount * 4))

    header = dict(
        key1=key1, key2=key2, version=version,
        date_min=date_min, date_max=date_max,
        lat_min=lat_min, lat_max=lat_max,
        lon_min=lon_min, lon_max=lon_max,
        meta_strings=meta_strings,
        count=count, sample_sec=sample_sec,
        loc=loc, loc_fc=loc_fc,
        varcount=varcount, var_codes=var_codes,
    )
    return header, count, varcount


def _read_stations(f, loc: int) -> list:
    stations = []
    for _ in range(loc):
        lat = struct.unpack("<d", f.read(8))[0]
        lon = struct.unpack("<d", f.read(8))[0]
        elev = struct.unpack("<h", f.read(2))[0]
        who = _read_cstring(f)
        country = _read_cstring(f)
        region = _read_cstring(f)
        stations.append(dict(lat=lat, lon=lon, elev=elev,
                             who=who, country=country, region=region))
    return stations


def read_pww(data: bytes) -> tuple[dict, list, np.ndarray]:
    """Parse a PWW binary from bytes (VERSION 1 or 2).

    VERSION 1 station block is skipped (grid metadata, not real lat/lon).
    """
    f = io.BytesIO(data)
    header, count, varcount = _parse_header_only(f)
    n_lat = round((header["lat_max"] - header["lat_min"]) / 0.25) + 1
    n_lon = round((header["lon_max"] - header["lon_min"]) / 0.25) + 1
    nbytes = count * varcount * n_lat * n_lon

    if header["version"] >= 2:
        stations = _read_stations(f, header["loc"])
        arr_offset = f.tell()
    else:
        stations = []
        header["loc"] = 0
        arr_offset = len(data) - nbytes

    arr = np.frombuffer(data, dtype=np.uint8, offset=arr_offset, count=nbytes) \
            .reshape(count, varcount, n_lat, n_lon).copy()
    return header, stations, arr


def crop_to_bbox(header: dict, stations: list, arr: np.ndarray, region: tuple) -> tuple[dict, list, np.ndarray]:
    """Crop a full-grid PWW array to a bounding box.

    region : (lat_max, lon_min, lat_min, lon_max) — CDS convention (N, W, S, E).
    """
    if not (isinstance(region, tuple) and len(region) == 4):
        raise ValueError("region must be a (lat_max, lon_min, lat_min, lon_max) tuple")
    r_lat_max, r_lon_min, r_lat_min, r_lon_max = region

    src_lat_min = header["lat_min"]
    src_lon_max = header["lon_max"]  # lon axis is DESCENDING: index 0 = lon_max

    lat_s = round((r_lat_min - src_lat_min) / 0.25)
    lat_e = round((r_lat_max - src_lat_min) / 0.25) + 1
    lon_s = round((src_lon_max - r_lon_max) / 0.25)
    lon_e = round((src_lon_max - r_lon_min) / 0.25) + 1

    lat_s = max(0, lat_s); lat_e = min(arr.shape[2], lat_e)
    lon_s = max(0, lon_s); lon_e = min(arr.shape[3], lon_e)

    cropped = arr[:, :, lat_s:lat_e, lon_s:lon_e].copy()

    new_lat_min = src_lat_min + lat_s * 0.25
    new_lat_max = src_lat_min + (lat_e - 1) * 0.25
    new_lon_max = src_lon_max - lon_s * 0.25
    new_lon_min = src_lon_max - (lon_e - 1) * 0.25

    # Filter stations against grid-aligned bounds so loc == n_lat_crop * n_lon_crop exactly
    eps = 1e-6
    new_stations = [
        s for s in stations
        if (new_lat_min - eps) <= s["lat"] <= (new_lat_max + eps)
        and (new_lon_min - eps) <= s["lon"] <= (new_lon_max + eps)
    ]

    new_header = dict(header)
    new_header.update(
        lat_min=new_lat_min, lat_max=new_lat_max,
        lon_min=new_lon_min, lon_max=new_lon_max,
        loc=len(new_stations),
    )
    return new_header, new_stations, cropped


def write_pww(header: dict, stations: list, arr: np.ndarray) -> bytes:
    """Write a PWW binary to bytes, preserving the original version and magic numbers."""
    count, varcount, _n_lat, _n_lon = arr.shape
    version = header.get("version", 2)
    loc = len(stations)

    sta_buf = bytearray()
    for s in stations:
        sta_buf += struct.pack("<d", s["lat"])
        sta_buf += struct.pack("<d", s["lon"])
        sta_buf += struct.pack("<h", int(s["elev"]))
        sta_buf += s["who"].encode("ascii", errors="replace") + b"\x00"
        sta_buf += s["country"].encode("ascii", errors="replace") + b"\x00"
        sta_buf += s["region"].encode("ascii", errors="replace") + b"\x00"

    meta_strings = header.get("meta_strings") or []

    f = io.BytesIO()
    f.write(struct.pack("<h", header["key1"]))
    f.write(struct.pack("<h", header["key2"]))
    f.write(struct.pack("<h", version))
    f.write(struct.pack("<d", header["date_min"]))
    f.write(struct.pack("<d", header["date_max"]))
    f.write(struct.pack("<d", header["lat_min"]))
    f.write(struct.pack("<d", header["lat_max"]))
    f.write(struct.pack("<d", header["lon_min"]))
    f.write(struct.pack("<d", header["lon_max"]))
    f.write(struct.pack("<h", len(meta_strings)))
    for s in meta_strings:
        f.write(s.encode("ascii", errors="replace") + b"\x00")
    f.write(struct.pack("<i", count))
    f.write(struct.pack("<i", header["sample_sec"]))
    f.write(struct.pack("<i", loc))
    f.write(struct.pack("<h", header.get("loc_fc", 0)))
    f.write(struct.pack("<h", varcount))
    for code in header["var_codes"]:
        f.write(struct.pack("<h", code))
    if version >= 2:
        f.write(struct.pack("<h", varcount))
        for i in range(varcount):
            f.write(struct.pack("<i", int((arr[:, i, :, :] != 255).sum())))
    f.write(sta_buf)
    f.write(arr.tobytes())
    return f.getvalue()


_OLE_EPOCH_OFFSET = 25569.0  # OLE days from Dec 30 1899 to Unix epoch Jan 1 1970

def _unix_to_ole(unix_sec: float) -> float:
    """Convert Unix epoch seconds to OLE Automation days."""
    return unix_sec / 86400 + _OLE_EPOCH_OFFSET


def crop_to_timerange(header: dict, arr: np.ndarray, t_start: float, t_end: float) -> tuple[dict, np.ndarray]:
    """Crop the time axis of a PWW array to [t_start, t_end] (Unix epoch seconds).

    PWW stores date_min/date_max as OLE Automation days (days since Dec 30 1899).
    t_start/t_end are converted to OLE days before indexing.
    Returns (new_header, cropped_arr).  Raises ValueError if no time steps fall
    within the range.
    """
    date_min_ole = header["date_min"]
    date_max_ole = header["date_max"]
    sample_sec = header["sample_sec"]
    sample_days = sample_sec / 86400
    count = arr.shape[0]

    ole_start = _unix_to_ole(t_start)
    ole_end = _unix_to_ole(t_end)

    i_start = max(0, round((ole_start - date_min_ole) / sample_days))
    i_end = min(count, round((ole_end - date_min_ole) / sample_days) + 1)

    if i_start >= i_end:
        from datetime import datetime, timezone
        def _ole_to_iso(ole):
            unix = (ole - _OLE_EPOCH_OFFSET) * 86400
            return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        raise ValueError(
            f"No time steps in requested range "
            f"[{_ole_to_iso(ole_start)}, {_ole_to_iso(ole_end)}]; "
            f"file covers [{_ole_to_iso(date_min_ole)}, {_ole_to_iso(date_max_ole)}]"
        )

    cropped = arr[i_start:i_end].copy()
    new_date_min = date_min_ole + i_start * sample_days
    new_date_max = date_min_ole + (i_end - 1) * sample_days

    new_header = dict(header)
    new_header.update(date_min=new_date_min, date_max=new_date_max)
    return new_header, cropped
