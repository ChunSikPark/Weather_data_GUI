# Troubleshooting

## "No file for … " (HTTP 404)

```text
WeatherAPIError: [HTTP 404] No file ID for era5_tx 2026-Q3
```

The date key does not exist for that source and type. Two usual causes:

**The date is not in that collection.** List first:

```python
client.list("era5", "texas")     # []  -> nothing published for Texas yet
client.list("era5")              # ['2026-Q3', '2026-Q2', ...]
```

**Wrong type.** NOAA `recent` and `archive` are different folders, and HRRR has
four separate history collections. A key present in one will 404 in another.

## Empty list from `list()`

The collection genuinely has no files, or the catalog is stale. Force a rebuild:

```python
client.catalog(refresh=True)
client.list("hrrr", "archive")
```

The server caches the catalog for 30 minutes; newly uploaded data may not appear
until it refreshes.

## Empty ISO zone list

```python
client.region_ids("iso")    # []
```

ISO zones load from a shapefile on the server. If it is missing, or in a
projected rather than geographic coordinate system, the server logs the problem
and serves an empty list instead of crashing. States are unaffected. Report it —
this needs a server-side fix.

## "Server queue full, retrying…"

```text
Server queue full, retrying in 5s (1/3)...
```

Normal. Downloads run behind a bounded queue so heavy requests cannot exhaust the
server's memory, and the client waits and retries automatically. If it gives up
you get {class}`~TeamOverbyeWeather.ServerBusyError`; wait a minute and retry.

Reduce your load by requesting fewer dates at once, or by cropping to a smaller
region so each request is cheaper.

## "Server can't crop … downloading in full"

```text
Server can't crop hrrr_history_hourly_archive 2014-11 at this scale —
downloading in full and cropping locally.
```

Expected for large-area requests against HRRR **monthly archives**. The server
refuses (HTTP 413) rather than run out of memory, and the client downloads the
whole archive and crops on your machine. The result is identical; the transfer is
much bigger.

To avoid it:

- Ask for a smaller area (under 2380 square degrees)
- Use `current` / `hourly_current` per-day files instead of a month
- Pass `keep_raw=True` if you will crop the same month more than once

To turn it into an error instead:

```python
client.download(..., local_crop=False)   # raises RegionTooLargeError
```

## "No time steps in requested range"

```text
ValueError: No time steps in requested range [2026-08-20T00:00Z, 2026-08-21T00:00Z];
file covers [2026-07-22T12:00Z, 2026-08-07T12:00Z]
```

Your window falls outside the file. The message reports what the file actually
covers — pick a window inside it. Remember times are UTC.

## Downloaded file will not open in PowerWorld

Check the extension matches the contents. ERA5 and NOAA files are bare `.pww`;
HRRR forecast and 15-minute history files are `.zip` archives containing `.pww`
files. If you renamed a `.zip` to `.pww` it will not open — unzip it first.

**Every cropped download is a flat `.pww`** regardless of source, so this only
comes up with uncropped downloads.

## Cropped file has fewer time steps than expected

A 15-minute HRRR day should have **96** steps. If you see 24, you are looking at
a single quarter rather than the stitched day — the daily zip holds four
six-hour `.pww` files. Both the server and `localcrop.crop_file` stitch them
automatically; hand-written code that reads only the first member will silently
lose three quarters of the day.

```python
from TeamOverbyeWeather import pww_io
header, _, arr = pww_io.read_pww(open(path, "rb").read())
print(arr.shape[0], "steps every", header["sample_sec"], "s")   # 96 steps every 900 s
```

## Wrong region in the output

Check the bounding box ordering. It is `(lat_max, lon_min, lat_min, lon_max)` —
north, west, south, east — and western longitudes are negative. See
{doc}`regions`.

Also remember that multiple states crop to their **union rectangle**, not to the
state outlines.

## `AttributeError: 'WeatherClient' object has no attribute 'extreme'`

You have a version older than 0.4.0. The error does not say so, and plain
`pip install TeamOverbyeWeather` will **not** fix it — pip sees the requirement
as already satisfied and leaves the old version in place. You need `--upgrade`:

```bash
pip install --upgrade TeamOverbyeWeather
```

```python
import TeamOverbyeWeather
print(TeamOverbyeWeather.__version__)     # 0.4.0 or newer
```

In a notebook, restart the kernel afterwards — an already-imported module is not
replaced by installing over it.

## `ImportError: No module named numpy`

Version 0.3.0 added numpy as a dependency. Upgrade:

```bash
pip install --upgrade TeamOverbyeWeather
```

## Connection timeouts

Large downloads can take several minutes. The client allows 15 minutes per
transfer. If you are on a slow link, crop harder — the whole point of the region
and time arguments is to move less data.

## Status shows `unknown` for everything

Cosmetic. The pipeline health file is produced by the ingest machines and is not
present on the hosted API. Data downloads are unaffected — check
{meth}`~TeamOverbyeWeather.WeatherClient.list` instead.

## Still stuck

The two debug endpoints tell you what the server can actually see:

```text
GET /api/debug/folders               which Drive folders are in use
GET /api/debug/folder?folder_id=...  raw filenames in a folder
```

Use them before guessing — a "no data" problem is almost always a folder
permission or filename issue, and these show which.
