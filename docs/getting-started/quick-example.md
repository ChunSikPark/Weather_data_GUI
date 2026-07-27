# Quick Example

This page walks through a complete session: find what data exists, download a
slice of it, and check what you got. Every output shown here is real.

## 1. Connect

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()
```

## 2. See what is available

Three sources, each with sub-types:

```python
for source in client.sources():
    print(source, "->", client.types(source))
```

```text
era5 -> ['historical', 'na', 'north_america', 'texas', 'tx']
hrrr -> ['archive', 'current', 'forecast', 'history', 'hourly_archive', 'hourly_current']
noaa -> ['archive', 'forecast', 'recent']
```

List the dates each one covers, newest first:

```python
print(client.list("noaa"))                      # forecast cycles
print(client.list("hrrr", "hourly_current"))    # daily, hourly steps
print(client.list("hrrr", "hourly_archive"))    # monthly, hourly steps
print(client.list("era5"))                      # quarters
```

```text
['2026-07-22T12Z', '2026-07-22T06Z', '2026-07-22T00Z', ...]
['2026-07-21', '2026-07-20', '2026-07-19', ...]
['2026-06', '2014-12', '2014-11', '2014-10', ...]
['2026-Q3', '2026-Q2', '2026-Q1', ...]
```

Date formats differ by source — quarters, months, days, or forecast cycles. Use
whatever {meth}`~TeamOverbyeWeather.WeatherClient.list` gives you and you cannot
get it wrong.

## 3. Download a whole file

```python
paths = client.download("noaa", dates="2026-07-22T12Z", dest="./data")
print(paths[0])
```

```text
data/Forecast_NorthAmerica_Run2026-07-22T12Z.pww
```

## 4. Crop to a region

Pass `region` with a state postal code:

```python
path = client.download("noaa", dates="2026-07-22T12Z",
                       region="TX", dest="./data")[0]
```

```text
data/noaa_forecast_recent_2026-07-22T12Z_TX.pww
```

The grid shrinks from North America to a 44×53 box around Texas.

## 5. Crop in time as well

```python
path = client.download(
    "noaa",
    dates="2026-07-22T12Z",
    region="TX",
    time_start="2026-07-22T12:00",
    time_end="2026-07-22T18:00",
    dest="./data",
)[0]
```

```text
data/noaa_forecast_recent_2026-07-22T12Z_TX_T20260722H1200to20260722H1800.pww
```

The filename records both crops. What actually changed:

| Request | Time steps | Grid | Size |
|---|---|---|---|
| Full file | 385 | North America | 120 MB |
| `region="TX"` | 385 | 44 × 53 | 7.3 MB |
| `region="TX"` + 6-hour window | 7 | 44 × 53 | 240 KB |

Both crops happen on the server, so the small number is what crosses the
network — not the large one.

## 6. Check what you got

```python
from TeamOverbyeWeather import pww_io

header, stations, arr = pww_io.read_pww(open(path, "rb").read())
print("time steps:", arr.shape[0])
print("grid:", arr.shape[2], "x", arr.shape[3])
print("step seconds:", header["sample_sec"])
```

```text
time steps: 7
grid: 44 x 53
step seconds: 3600
```

## Putting it together

A realistic request — every 15-minute HRRR step for one day over ERCOT, business
hours only:

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

paths = client.download(
    "hrrr",
    type="current",                  # 15-minute steps, current year
    dates=client.list("hrrr", "current")[:3],   # three most recent days
    iso="ERCOT",
    time_start="2026-07-21T08:00",
    time_end="2026-07-21T20:00",
    dest="./data",
)

for p in paths:
    print(p.name)
```

One file per day, each already cropped to ERCOT and to the hours you asked for.

## Where to go next

- {doc}`../guides/catalog` — how the date keys and sub-types work
- {doc}`../guides/regions` — states, ISO zones, and custom bounding boxes
- {doc}`../guides/time` — time windows in detail
- {doc}`../guides/pww-files` — reading `.pww` data into numpy
