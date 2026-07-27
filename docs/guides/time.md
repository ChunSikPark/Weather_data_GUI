# Cropping in Time

Weather files cover long spans — a NOAA forecast runs 16 days, an HRRR day holds
96 fifteen-minute steps. `time_start` and `time_end` keep only the window you
need.

## A time window

```python
client.download(
    "noaa",
    dates="2026-07-22T12Z",
    region="TX",
    time_start="2026-07-22T12:00",
    time_end="2026-07-22T18:00",
    dest="./data",
)
```

385 time steps become 7. Both ends are **inclusive**, so 12:00 through 18:00 at
hourly resolution is seven steps, not six.

## One-sided windows

Either bound may be omitted:

```python
client.download(..., time_start="2026-07-23T00:00")   # from then to end of file
client.download(..., time_end="2026-07-23T00:00")     # from start of file to then
```

## Times are UTC

A time without a timezone is treated as UTC, matching the data. Weather files are
stored in UTC and there is no local-time conversion anywhere in the pipeline.

To work from local time, convert first:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

central = datetime(2026, 7, 22, 8, 0, tzinfo=ZoneInfo("America/Chicago"))
client.download(..., time_start=central.astimezone(ZoneInfo("UTC")))
```

`datetime` objects are accepted directly, so you can skip string formatting:

```python
from datetime import datetime
client.download(..., time_start=datetime(2026, 7, 22, 12, 0))
```

## Accepted formats

Any ISO 8601 string, or a `datetime` / `date`:

```text
2026-07-22T12:00:00
2026-07-22T12:00
2026-07-22
```

A malformed string fails immediately, before any download starts:

```text
ValueError: Invalid time '07/22/2026'. Use ISO format
('2026-07-22T12:00:00') or a datetime object.
```

## Time steps per source

The window snaps to the file's own sampling interval, so know what you are
slicing:

| Source | Step | Steps per file |
|---|---|---|
| HRRR `current` / `archive` | 15 min | 96 per day |
| HRRR `hourly_*` | 1 hour | 24 per day |
| HRRR `forecast` | 1 hour | 49 (0–48 h) |
| NOAA | 1 hour | 385 (16 days) |
| ERA5 | 1 hour | one quarter |

A one-hour window against 15-minute HRRR data returns five steps (`:00`, `:15`,
`:30`, `:45`, and the closing `:00`).

## Cropping time without cropping space

You do not need a region to crop time. Ask for a window on its own and the full
grid is kept:

```python
client.download("noaa", dates="2026-07-22T12Z",
                time_start="2026-07-22T12:00",
                time_end="2026-07-22T18:00",
                dest="./data")
```

Internally this is sent as a whole-globe bounding box, which the server clamps to
the file's own grid — so nothing is lost spatially.

:::{note}
For **HRRR monthly archives** a time-only crop counts as a CONUS-scale request
and triggers the local-crop fallback, which means downloading the whole archive.
If you only need a few hours from a month, pull the matching `current` /
`hourly_current` day instead — far less data moves.
:::

## Requesting a window outside the file

If no time step falls in the range you get a clear error naming both spans:

```text
ValueError: No time steps in requested range
[2026-08-20T00:00Z, 2026-08-21T00:00Z];
file covers [2026-07-22T12:00Z, 2026-08-07T12:00Z]
```

Check what a file covers before slicing it:

```python
from TeamOverbyeWeather import pww_io
from datetime import datetime, timezone

header, _, arr = pww_io.read_pww(open(path, "rb").read())
to_utc = lambda ole: datetime.fromtimestamp((ole - 25569.0) * 86400, tz=timezone.utc)

print("covers:", to_utc(header["date_min"]), "->", to_utc(header["date_max"]))
print("steps:", arr.shape[0], "every", header["sample_sec"], "s")
```

## Naming

Time-cropped files carry the window in the filename, so a directory of downloads
stays self-describing:

```text
noaa_forecast_recent_2026-07-22T12Z_TX_T20260722H1200to20260722H1800.pww
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       from 2026-07-22 12:00 to 18:00
```

One-sided windows get a single stamp: `_T20260722H1200`.

The stamp includes minutes, so two windows within the same hour produce
different filenames rather than the second silently overwriting the first —
which matters when slicing 15-minute HRRR data.
