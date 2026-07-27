# Downloading Data

Everything goes through one method:
{meth}`~TeamOverbyeWeather.WeatherClient.download`.

```python
client.download(source, dates, type=None, *,
                region=None, iso=None, bbox=None,
                time_start=None, time_end=None,
                dest=".", show_progress=None,
                local_crop=True, keep_raw=False)
```

It returns a list of {class}`pathlib.Path` — **one file per date key**, never a
ZIP you have to unpack.

## One date

```python
paths = client.download("noaa", dates="2026-07-22T12Z", dest="./data")
```

`dates` accepts a bare string for a single key.

## Many dates

```python
paths = client.download(
    "hrrr",
    type="hourly_current",
    dates=["2026-07-21", "2026-07-20", "2026-07-19"],
    dest="./data",
)
print(len(paths))   # 3
```

Each date is fetched as its own request and written as its own file. If one date
fails, the exception tells you which — you are not left guessing which member of
a ZIP is missing.

## File names

The server names files, and the client keeps that name. Cropped files record
what was done to them:

```text
Forecast_NorthAmerica_Run2026-07-22T12Z.pww               uncropped
noaa_forecast_recent_2026-07-22T12Z_TX.pww                region crop
noaa_forecast_recent_..._TX_T20260722H1200to20260722H1800.pww  region + time
noaa_forecast_recent_2026-07-22T12Z_TX+OK+NM.pww          multi-state union
noaa_forecast_recent_2026-07-22T12Z_ERCOT.pww             ISO zone
noaa_forecast_recent_2026-07-22T12Z_custom.pww            custom bbox
```

## File formats

What lands on disk depends on the source:

| Source | Uncropped format |
|---|---|
| ERA5 | bare `.pww` |
| NOAA | bare `.pww` |
| HRRR hourly, daily | bare `.pww` |
| HRRR forecast | `.zip` holding one `.pww` |
| HRRR 15-minute, daily | `.zip` holding **four** quarter `.pww` files |
| HRRR monthly archives | `.zip` of daily `.zip` files |

**Any cropped download is always a single flat `.pww`**, whatever the source
format. Multi-part files are stitched back together along the time axis before
you get them, so a cropped 15-minute day is one file with all 96 steps — not
four files with 24 each.

## Progress bars

On by default. Turn them off for scripts and batch jobs:

```python
client = WeatherClient(show_progress=False)          # for every call
client.download(..., show_progress=False)            # for one call
```

## Choosing where files go

```python
client.download("noaa", dates="2026-07-22T12Z", dest="./data/noaa")
```

The directory is created if it does not exist.

## When the server is busy

Downloads run behind a bounded queue so a handful of large requests cannot
exhaust the server's memory. If the queue is full the server replies **503**, and
the client waits the interval it asks for and retries:

```text
Server queue full, retrying in 5s (1/3)...
```

This is normal under load and needs no action. If all retries are exhausted you
get {class}`~TeamOverbyeWeather.ServerBusyError` — wait a minute and try again.

## Very large requests

The server refuses to crop CONUS-scale HRRR monthly archives, because holding a
whole month in memory would take the service down. When that happens the client
falls back automatically:

```text
Server can't crop hrrr_history_hourly_archive 2014-11 at this scale —
downloading in full and cropping locally.
```

It downloads the untouched archive and does the crop on your machine, giving
identical output at the cost of a much larger transfer. To make that a hard
error instead:

```python
client.download(..., local_crop=False)   # raises RegionTooLargeError
```

To keep the raw archive after cropping — worth it if you plan several crops of
the same month:

```python
client.download(..., keep_raw=True)
```

The usual way to avoid the fallback altogether is to ask for a smaller area, or
to pull the per-day `current` / `hourly_current` files instead of a whole month.

## Back-compatible methods

The older per-source calls still work and now accept the new arguments:

```python
client.noaa.download_forecast(["2026-07-22T12Z"], dest="./data")
client.noaa.download_forecast(["..."], type="archive", dest="./data")
client.hrrr.download_region(days=["2026-07-21"], type="hourly_current",
                            region_ids=["TX"], region_layer="states",
                            time_start="2026-07-21T06:00", dest="./data")
client.era5.download(["2026-Q1"], region="north_america", dest="./data")
```

See {doc}`../reference/sources` for the full list. New code should prefer
`client.download()`.
