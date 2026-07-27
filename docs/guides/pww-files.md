# Working with PWW Files

`.pww` is the PowerWorld Timestep Simulation Weather format. You can open the
downloaded files directly in PowerWorld, or read them into numpy with the
`pww_io` module bundled with this package.

## Reading a file

```python
from TeamOverbyeWeather import pww_io

header, stations, arr = pww_io.read_pww(open(path, "rb").read())
```

For large files, read from disk instead — it memory-maps rather than loading
everything at once:

```python
header, stations, arr = pww_io.read_pww_file(path)
```

## The array

`arr` is a 4-dimensional `uint8` array:

```python
arr.shape      # (385, 8, 44, 53)
               #  time, variable, latitude, longitude
```

| Axis | Meaning |
|---|---|
| 0 | time step — `header["sample_sec"]` seconds apart |
| 1 | weather variable — see `header["var_codes"]` |
| 2 | latitude, **ascending** (south to north) |
| 3 | longitude, **descending** (east to west) |

:::{warning}
The longitude axis runs **east to west**, so index 0 is `lon_max`, not
`lon_min`. This trips people up when indexing by hand — the latitude axis runs
the other way.
:::

**255 is the missing-data sentinel**, not a real measurement. Mask it before
doing arithmetic:

```python
import numpy as np

data = arr.astype(float)
data[arr == 255] = np.nan
```

## The header

```python
header
```

```text
{'key1': 2001, 'key2': 8066, 'version': 2,
 'date_min': 46225.5, 'date_max': 46241.5,
 'lat_min': 25.75, 'lat_max': 36.5,
 'lon_min': -106.5, 'lon_max': -93.5,
 'meta_strings': ['PowerWorld Timestep Simulation Weather'],
 'count': 385, 'sample_sec': 3600,
 'loc': 2332, 'loc_fc': 0,
 'varcount': 8, 'var_codes': [102, 104, 106, 107, 119, 110, 120, 121]}
```

| Field | Meaning |
|---|---|
| `version` | 1 or 2 — both are readable |
| `date_min`, `date_max` | first and last time step, in **OLE Automation days** |
| `lat_min` … `lon_max` | grid extent in degrees |
| `count` | number of time steps |
| `sample_sec` | seconds between steps (900 = 15 min, 3600 = hourly) |
| `loc` | number of station records |
| `varcount`, `var_codes` | how many weather variables, and their codes |

`var_codes` are character codes; the mapping to physical quantities is defined by
the PowerWorld weather format. Read them as letters:

```python
print([chr(c) for c in header["var_codes"]])
```

```text
['f', 'h', 'j', 'k', 'w', 'n', 'x', 'y']
```

## Dates

PWW stores time as **OLE Automation days** — days since 30 December 1899 — not
Unix time. Convert:

```python
from datetime import datetime, timezone

OLE_EPOCH = 25569.0     # OLE days between 1899-12-30 and 1970-01-01

def ole_to_utc(ole):
    return datetime.fromtimestamp((ole - OLE_EPOCH) * 86400, tz=timezone.utc)

print(ole_to_utc(header["date_min"]))   # 2026-07-22 12:00:00+00:00
```

Build a timestamp for every step:

```python
import numpy as np

start = ole_to_utc(header["date_min"])
times = [start + np.timedelta64(i * header["sample_sec"], "s").item()
         for i in range(arr.shape[0])]
```

## Coordinates

Grid spacing is 0.25° throughout. Reconstruct the axes:

```python
import numpy as np

lats = np.arange(header["lat_min"], header["lat_max"] + 0.001, 0.25)
lons = np.arange(header["lon_max"], header["lon_min"] - 0.001, -0.25)  # descending

assert len(lats) == arr.shape[2]
assert len(lons) == arr.shape[3]
```

## Station records

VERSION 2 files carry one record per grid point:

```python
stations[0]
```

```text
{'lat': 25.75, 'lon': -93.5, 'elev': 0,
 'who': '+25.75-093.50/', 'country': '', 'region': 'NorthAmerica'}
```

VERSION 1 files (older ERA5) have a station block holding grid metadata rather
than real coordinates, so `read_pww` returns `stations == []` for them. Use the
header extent to build coordinates instead — the code above works for both.

## Cropping locally

If you already have a file on disk and want a smaller piece, crop without
re-downloading:

```python
from TeamOverbyeWeather import localcrop

localcrop.crop_file(
    "data/big_file.zip",
    "data/small.pww",
    bbox=(36.5, -106.6, 25.8, -93.5),
    t_start=None,     # Unix epoch seconds, or None
    t_end=None,
)
```

This handles every on-disk shape — a bare `.pww`, a zip with one `.pww`, a zip
with four quarter `.pww` files, or a zip of daily zips — stitching multi-part
files along the time axis. Given the same inputs it produces the same output as
the server.

The lower-level pieces are available too:

```python
header, stations, arr = pww_io.crop_to_bbox(header, stations, arr, bbox)
header, arr = pww_io.crop_to_timerange(header, arr, t_start, t_end)
data = pww_io.write_pww(header, stations, arr)
```

`crop_to_timerange` takes **Unix epoch seconds**, and either bound may be `None`.

## Writing a file

```python
open("out.pww", "wb").write(pww_io.write_pww(header, stations, arr))
```

The original version and magic numbers are preserved, and VERSION 2 valid-counts
are recomputed from the array — so a file written this way opens in PowerWorld
like any other.

:::{tip}
Always `.copy()` after slicing an array before writing it. Numpy slices are
views, and `write_pww` expects a contiguous buffer. The `crop_*` helpers already
do this for you.
:::
