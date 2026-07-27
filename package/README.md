# TeamOverbyeWeather

Python client for the **Team Overbye Weather Data API** at Texas A&M University —
ERA5 reanalysis, HRRR history and forecasts, and NOAA/GFS forecasts, as
PowerWorld `.pww` files.

Download, crop to a region, and crop in time, in one call.

## Installation

```bash
pip install TeamOverbyeWeather
```

Python 3.10 or newer. No credentials needed.

## Quick start

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

# What is available?
client.sources()                        # ['era5', 'hrrr', 'noaa']
client.types("hrrr")                    # ['archive', 'current', 'forecast', ...]
client.list("hrrr", "hourly_current")   # ['2026-07-21', '2026-07-20', ...]

# Download, cropped to Texas and to a six-hour window
client.download(
    "hrrr",
    type="hourly_current",
    dates="2026-07-21",
    region="TX",
    time_start="2026-07-21T06:00",
    time_end="2026-07-21T18:00",
    dest="./data",
)
```

Cropping happens server-side, so only what you asked for crosses the network — a
Texas six-hour NOAA slice is 240 KB instead of the 120 MB full file.

One file is written per date key, already cropped, ready to open in PowerWorld.

## Selecting a region

Use exactly one of:

```python
client.download(..., region="TX")                       # one state
client.download(..., region=["TX", "OK", "NM"])         # union bounding box
client.download(..., iso="ERCOT")                       # ISO zone
client.download(..., bbox=(33.0, -100.0, 30.0, -96.0))  # lat_max, lon_min, lat_min, lon_max
```

List valid ids with `client.region_ids("states")` and `client.region_ids("iso")`.
Multiple states crop to the union rectangle, not to the state outlines.

## Selecting a time window

```python
client.download(..., time_start="2026-07-21T06:00", time_end="2026-07-21T18:00")
client.download(..., time_start="2026-07-21T06:00")   # to the end of the file
client.download(..., time_end="2026-07-21T18:00")     # from the start
```

Times are UTC and both bounds are inclusive. `datetime` objects work too.

## Data sources

| Source | Types | Date key |
|---|---|---|
| `era5` | `historical`, `texas` | `YYYY-Qn` |
| `hrrr` | `current`, `archive` (15-min), `hourly_current`, `hourly_archive`, `forecast` | `YYYY-MM-DD`, `YYYY-MM`, `YYYY-MM-DDTHHZ` |
| `noaa` | `recent`, `archive` | `YYYY-MM-DDTHHZ` |
| `extreme` | `events` | `YYYY-MM-DD_Title_Zone` |

## Extreme temperature events

62 curated historical events (1899–2023) — the three hottest and three coldest
per ISO zone, plus notable scenarios like ERCOT's 2011 rolling outages. Each
comes with an animation.

```python
client.extreme.zones()                       # ISO zones with events
client.extreme.events("Texas")               # events in a zone, newest first
client.extreme.find("uri")                   # search by title

event = client.extreme.find("uri")[0]
client.extreme.download(event["key"], region_ids=["TX"], region_layer="states",
                        time_start="2021-02-15T00:00", dest="./data")
client.extreme.video(event["key"], dest="./data")     # the .mp4 animation
client.extreme.coverage("Texas", dest="./data")       # zone coverage map
```

Always take date keys from `client.list(source, type)` — formats differ per
source, and NOAA `recent` / `archive` are separate folders rather than a date
split.

## Reading the data

```python
from TeamOverbyeWeather import pww_io

header, stations, arr = pww_io.read_pww(open(path, "rb").read())
arr.shape        # (time, variable, latitude, longitude)
```

`255` marks missing data. Latitude ascends, longitude descends.

## Documentation

Full guides and API reference: **https://chunsikpark.github.io/TeamOverbyeWeather/**

Point-and-click alternative: **https://weather-data-gui.pages.dev**

`demo.ipynb` in this repository is a runnable walkthrough of everything above.

## Problems or questions

**[Open an issue](https://github.com/ChunSikPark/TeamOverbyeWeather/issues/new/choose)**
— bugs and data questions are both welcome. For bugs, include your version
(`TeamOverbyeWeather.__version__`), the code you ran, and the full traceback.

Two things worth checking first:

- `AttributeError: 'WeatherClient' object has no attribute ...` almost always
  means an old version. Run `pip install --upgrade TeamOverbyeWeather`, then
  **restart your kernel** — Python will not replace a module that is already
  imported, so upgrading mid-session appears to do nothing.
- A source showing no data may genuinely be empty. Check
  `client.list(source, type)`, and try `client.catalog(refresh=True)` — the
  catalog is cached for 30 minutes.

## Development

```bash
git clone https://github.com/ChunSikPark/TeamOverbyeWeather.git
cd TeamOverbyeWeather
pip install -e .
```

Point the client at a local backend with
`WeatherClient(base_url="http://localhost:8000")`.

The backend and web portal live in a separate repository; this one holds the
Python package only.

## License

MIT
