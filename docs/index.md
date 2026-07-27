# Team Overbye Weather Data

Weather datasets for power system studies — ERA5 reanalysis, HRRR history and
forecasts, and NOAA/GFS forecasts — available through a
[web portal](https://weather-data-gui.pages.dev) and a Python package.

The Python package does three things in one call:

1. **Download** a dataset for one or more dates
2. **Crop to a region** — a state, a group of states, an ISO zone, or a bounding box
3. **Crop in time** — keep only the hours you care about

Cropping happens on the server, so you download only what you asked for. A Texas
six-hour NOAA slice is **240 KB** instead of the 120 MB the full North America
file would cost you — about 500× less to move.

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

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

That one call downloads the HRRR hourly file for July 21, crops it to the Texas
bounding box, keeps the 06:00–18:00 UTC window, and writes a `.pww` you can open
directly in PowerWorld.

:::{note}
New here? Read {doc}`getting-started/installation` then
{doc}`getting-started/quick-example`. If you just want files without writing
code, the [web portal](https://weather-data-gui.pages.dev) does the same thing
with a point-and-click interface.
:::

```{toctree}
:maxdepth: 2
:caption: Getting Started

getting-started/installation
getting-started/quick-example
```

```{toctree}
:maxdepth: 2
:caption: Guides

guides/catalog
guides/downloading
guides/regions
guides/time
guides/extreme-events
guides/pww-files
guides/troubleshooting
```

```{toctree}
:maxdepth: 2
:caption: API Reference

reference/client
reference/sources
reference/pww-io
reference/errors
reference/rest-api
```

```{toctree}
:maxdepth: 2
:caption: Development

development/architecture
development/contributing
```
