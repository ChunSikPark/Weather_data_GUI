# TeamOverbyeWeather

Python SDK for the **Team Overbye Weather Data API** at Texas A&M University.
Provides a clean, Pythonic interface to ERA5 reanalysis, HRRR forecast/history,
and NOAA/GFS forecast datasets maintained by Team Overbye.

---

## Installation

```bash
pip install TeamOverbyeWeather
```

Requires Python 3.10 or newer.

---

## Quick start

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()  # uses https://api.teamoverbye.tamu.edu by default

# Or point at a custom deployment:
# client = WeatherClient(base_url="https://api.teamoverbye.example.com")
```

---

## Data Sources

| Source | Description |
|--------|-------------|
| **ERA5** | ECMWF ERA5 reanalysis data, available in quarterly ZIP archives for North America and Texas |
| **HRRR** | High-Resolution Rapid Refresh — both operational forecasts (per cycle) and historical monthly archives |
| **NOAA/GFS** | NOAA Global Forecast System PWW files, available per forecast initialisation cycle |

---

## Usage

### Pipeline status

```python
status = client.status()
# {"noaa": "ok", "hrrr_forecast": "ok", "hrrr_history": "ok", "era5": "ok"}
print(status)
```

### Full catalog

```python
catalog = client.catalog()
print(catalog.keys())
# dict_keys(['era5_na', 'era5_tx', 'hrrr_history', 'hrrr_forecast', 'noaa'])
```

---

### ERA5

```python
# List available quarters for North America (default)
quarters = client.era5.list_quarters()
# ['2025-Q1', '2024-Q4', '2024-Q3', ...]

# List available quarters for Texas
quarters_tx = client.era5.list_quarters(region="texas")

# Download a single quarter (North America)
paths = client.era5.download(["2025-Q1"])
# [PosixPath('ERA5_era5_na_2025-Q1.zip')]

# Download multiple quarters into a custom directory
paths = client.era5.download(
    ["2025-Q1", "2024-Q4"],
    region="north_america",
    dest="/data/era5",
)
# [PosixPath('/data/era5/TeamOverbye_era5_na_20250506T120000Z.zip')]

# Download Texas data
paths = client.era5.download(["2025-Q1"], region="texas", dest="/data/era5")
```

---

### HRRR

```python
# List available historical months
months = client.hrrr.list_months()
# ['2025-01', '2024-12', '2024-11', ...]

# Download a single historical month
paths = client.hrrr.download_history(["2025-01"])
# [PosixPath('HRRR_history_2025-01.zip')]

# Download multiple months into a directory
paths = client.hrrr.download_history(["2025-01", "2024-12"], dest="/data/hrrr")

# List available forecast cycles
cycles = client.hrrr.list_forecast_cycles()
# ['2026-04-21T06Z', '2026-04-21T00Z', ...]

# Download a specific forecast cycle
paths = client.hrrr.download_forecast(["2026-04-21T06Z"], dest="/data/hrrr")

# Download multiple forecast cycles
paths = client.hrrr.download_forecast(
    ["2026-04-21T06Z", "2026-04-21T00Z"],
    dest="/data/hrrr",
)

# Download the most recent forecast cycle
path = client.hrrr.download_latest_forecast(dest="/data/hrrr")
print(path)
# /data/hrrr/HRRR_forecast_2026-04-21T06Z.zip
```

---

### NOAA/GFS

```python
# List available forecast cycles
cycles = client.noaa.list_forecast_cycles()
# ['2026-04-21T12Z', '2026-04-21T06Z', ...]

# Download specific forecast cycles
paths = client.noaa.download_forecast(["2026-04-21T12Z"], dest="/data/noaa")

# Download multiple cycles
paths = client.noaa.download_forecast(
    ["2026-04-21T12Z", "2026-04-21T06Z"],
    dest="/data/noaa",
)

# Download the most recent NOAA/GFS cycle
path = client.noaa.download_latest(dest="/data/noaa")
print(path)
# /data/noaa/NOAA_forecast_2026-04-21T12Z.zip
```

---

## Error handling

```python
import requests
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

try:
    paths = client.era5.download(["2025-Q1"], region="north_america")
except ValueError as exc:
    # Bad region name or malformed quarter string
    print(f"Input error: {exc}")
except requests.HTTPError as exc:
    # Non-2xx response from the API
    print(f"API error {exc.response.status_code}: {exc}")
```

---

## Web portal

Browse and download data interactively at the Team Overbye web portal:
**https://weather.teamoverbye.tamu.edu**

---

## License

MIT — see [LICENSE](LICENSE) for details.
