"""PWW VERSION 1/2 binary I/O — read, bbox crop, and write.

Ported from extract_region_pww.py.  Two entry points:
  read_pww(data: bytes)  — in-memory (SDK / tests)
  read_pww_file(path: str) — mmap-backed; file never fully loaded into RAM
"""
from __future__ import annotations

import io
import mmap
import os
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
    """Parse fixed header fields from a file-like object.

    Returns (header, count, varcount).  Does NOT read the station block.
    The caller is responsible for locating the array (either via f.tell()
    after reading stations, or by computing from the end of the file).
    """
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
    # VERSION 2+ has a bytecount + valid_counts block; VERSION 1 goes straight to stations
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


def _grid_shape(header: dict) -> tuple[int, int]:
    n_lat = round((header["lat_max"] - header["lat_min"]) / 0.25) + 1
    n_lon = round((header["lon_max"] - header["lon_min"]) / 0.25) + 1
    return n_lat, n_lon


def read_pww(data: bytes) -> tuple[dict, list, np.ndarray]:
    """Parse a PWW binary from bytes (VERSION 1 or 2).

    VERSION 1 files (HRRR, NOAA) have a station block whose records are grid
    metadata, not real lat/lon stations.  We skip that block entirely and
    return stations=[] to avoid corrupting outputs with garbage coordinates.
    """
    f = io.BytesIO(data)
    header, count, varcount = _parse_header_only(f)
    n_lat, n_lon = _grid_shape(header)
    nbytes = count * varcount * n_lat * n_lon

    if header["version"] >= 2:
        # VERSION 2: station records have valid lat/lon — parse them
        stations = _read_stations(f, header["loc"])
        arr_offset = f.tell()
    else:
        # VERSION 1: station block is grid metadata, not real stations — skip it
        stations = []
        header["loc"] = 0
        arr_offset = len(data) - nbytes

    arr = np.frombuffer(data, dtype=np.uint8, offset=arr_offset, count=nbytes) \
            .reshape(count, varcount, n_lat, n_lon).copy()
    return header, stations, arr


def read_pww_file(path: str) -> tuple[dict, list, np.ndarray]:
    """Parse a PWW file using mmap — the file is never fully loaded into RAM.

    VERSION 1 station block is skipped (see read_pww docstring).
    """
    file_size = os.path.getsize(path)
    with open(path, "rb") as fh:
        header, count, varcount = _parse_header_only(fh)
        n_lat, n_lon = _grid_shape(header)
        nbytes = count * varcount * n_lat * n_lon

        if header["version"] >= 2:
            stations = _read_stations(fh, header["loc"])
            arr_offset = fh.tell()
        else:
            stations = []
            header["loc"] = 0
            arr_offset = file_size - nbytes

        mm = mmap.mmap(fh.fileno(), length=0, access=mmap.ACCESS_READ)
        try:
            arr = np.frombuffer(mm, dtype=np.uint8, offset=arr_offset, count=nbytes) \
                    .reshape(count, varcount, n_lat, n_lon).copy()
        finally:
            mm.close()
    return header, stations, arr


def crop_to_bbox(header: dict, stations: list, arr: np.ndarray, region: tuple) -> tuple[dict, list, np.ndarray]:
    """Crop a full-grid PWW array to a bounding box.

    region : (lat_max, lon_min, lat_min, lon_max) tuple — CDS convention (N, W, S, E).
    """
    if not (isinstance(region, tuple) and len(region) == 4):
        raise ValueError("region must be a (lat_max, lon_min, lat_min, lon_max) tuple")
    r_lat_max, r_lon_min, r_lat_min, r_lon_max = region

    src_lat_min = header["lat_min"]
    src_lon_max = header["lon_max"]

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

    eps = 1e-6
    new_stations = [
        s for s in stations
        if (r_lat_min - eps) <= s["lat"] <= (r_lat_max + eps)
        and (r_lon_min - eps) <= s["lon"] <= (r_lon_max + eps)
    ]

    new_header = dict(header)
    new_header.update(
        lat_min=new_lat_min, lat_max=new_lat_max,
        lon_min=new_lon_min, lon_max=new_lon_max,
        loc=len(new_stations),
    )
    return new_header, new_stations, cropped


def write_pww(header: dict, stations: list, arr: np.ndarray) -> bytes:
    """Write a VERSION 2 PWW binary to bytes."""
    count, varcount, _n_lat, _n_lon = arr.shape
    loc = len(stations)

    sta_buf = bytearray()
    for s in stations:
        sta_buf += struct.pack("<d", s["lat"])
        sta_buf += struct.pack("<d", s["lon"])
        sta_buf += struct.pack("<h", int(s["elev"]))
        sta_buf += s["who"].encode("ascii", errors="replace") + b"\x00"
        sta_buf += s["country"].encode("ascii", errors="replace") + b"\x00"
        sta_buf += s["region"].encode("ascii", errors="replace") + b"\x00"

    f = io.BytesIO()
    f.write(struct.pack("<h", 2001))
    f.write(struct.pack("<h", 8066))
    f.write(struct.pack("<h", 2))
    f.write(struct.pack("<d", header["date_min"]))
    f.write(struct.pack("<d", header["date_max"]))
    f.write(struct.pack("<d", header["lat_min"]))
    f.write(struct.pack("<d", header["lat_max"]))
    f.write(struct.pack("<d", header["lon_min"]))
    f.write(struct.pack("<d", header["lon_max"]))
    f.write(struct.pack("<h", 1))
    f.write(b"PowerWorld Timestep Simulation Weather\x00")
    f.write(struct.pack("<i", count))
    f.write(struct.pack("<i", header["sample_sec"]))
    f.write(struct.pack("<i", loc))
    f.write(struct.pack("<h", 0))
    f.write(struct.pack("<h", varcount))
    for code in header["var_codes"]:
        f.write(struct.pack("<h", code))
    f.write(struct.pack("<h", varcount))
    for i in range(varcount):
        f.write(struct.pack("<i", int((arr[:, i, :, :] != 255).sum())))
    f.write(sta_buf)
    f.write(arr.tobytes())
    return f.getvalue()
