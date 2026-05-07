# Team Overbye Weather Data API

Base URL: `https://api.teamoverbye.tamu.edu`

All endpoints return JSON unless otherwise noted. No authentication required for public access.

---

## Endpoints

### Health Check

```
GET /api/health
```

**Response**
```json
{
  "status": "ok"
}
```

---

### Pipeline Status

Returns the current health of each data pipeline.

```
GET /api/status
```

**Response**
```json
{
  "noaa": "ok",
  "hrrr_forecast": "ok",
  "hrrr_history": "ok",
  "era5": "error"
}
```

| Value | Meaning |
|-------|---------|
| `"ok"` | Pipeline ran successfully |
| `"error"` | Pipeline alert is active |
| `"unknown"` | Status unavailable |

---

### Data Catalog

Returns all available files grouped by source and date.

```
GET /api/catalog
```

**Response**
```json
{
  "era5_na": {
    "quarters": ["2025-Q1", "2024-Q4", "2024-Q3"],
    "file_ids": {
      "2025-Q1": { "id": "...", "webContentLink": "https://..." }
    }
  },
  "era5_tx": {
    "quarters": ["2025-Q1", "2024-Q4"],
    "file_ids": { ... }
  },
  "hrrr_history": {
    "months": ["2025-04", "2025-03", "2025-02"],
    "file_ids": { ... }
  },
  "hrrr_forecast": {
    "cycles": ["2026-05-07T12Z", "2026-05-07T06Z", "2026-05-07T00Z"],
    "file_ids": { ... }
  },
  "noaa_forecast": {
    "cycles": ["2026-05-07T12Z", "2026-05-07T06Z"],
    "file_ids": { ... }
  }
}
```

**Date key formats by source**

| Source | Format | Example |
|--------|--------|---------|
| `era5_na` / `era5_tx` | `YYYY-QN` | `2025-Q1` |
| `hrrr_history` | `YYYY-MM` | `2025-04` |
| `hrrr_forecast` | `YYYY-MM-DDThhZ` | `2026-05-07T06Z` |
| `noaa_forecast` | `YYYY-MM-DDThhZ` | `2026-05-07T06Z` |

---

### Force Catalog Refresh

Bypasses the 30-minute cache and rebuilds the catalog immediately from Google Drive.

```
POST /api/catalog/refresh
```

**Response** — same shape as `GET /api/catalog`

---

### Download File(s)

Download one or more files. Single file returns a redirect to the original file; multiple files are bundled into a ZIP.

```
GET /api/download?source={source}&dates={dates}
```

**Parameters**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `source` | Yes | One of: `era5_na`, `era5_tx`, `hrrr_history`, `hrrr_forecast`, `noaa_forecast` |
| `dates` | Yes | Single date key, or comma-separated list for multi-file ZIP |

**Single file — redirects to the file directly**
```
GET /api/download?source=era5_na&dates=2025-Q1

→ 302 redirect → ERA5_NorthAmerica_2025_Q1.zip
```

**Multiple files — streams a ZIP bundle**
```
GET /api/download?source=hrrr_history&dates=2025-01,2025-02,2025-03

→ 200 application/zip → hrrr_history_bundle_3_files.zip
```

**Error responses**

| Status | Meaning |
|--------|---------|
| `400` | Unknown source or missing/empty `dates` parameter |
| `404` | Requested date(s) not found in catalog |
| `502` | Failed to fetch file from upstream storage |

```json
{ "detail": "No file for era5_na 2020-Q1" }
```

---

## Python SDK

Install:
```bash
pip install TeamOverbyeWeather
```

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()  # defaults to production API

# Check pipeline health
print(client.status())
# {'noaa': 'ok', 'hrrr_forecast': 'ok', 'hrrr_history': 'ok', 'era5': 'ok'}

# List available ERA5 quarters
quarters = client.era5.list_quarters(region="north_america")
# ['2025-Q1', '2024-Q4', '2024-Q3', ...]

# Download ERA5 data
client.era5.download(quarters=["2025-Q1"], region="north_america", dest="./data/")

# Download latest NOAA/GFS forecast
client.noaa.download_latest(dest="./data/")

# Download latest HRRR forecast
client.hrrr.download_latest_forecast(dest="./data/")

# Download HRRR history for specific months
client.hrrr.download_history(months=["2025-01", "2025-02"], dest="./data/")
```

**Custom API URL (for local testing)**
```python
client = WeatherClient(base_url="http://localhost:8000")
```

---

## Data Sources

| Source Key | Dataset | Region | Resolution | Update Frequency |
|------------|---------|--------|------------|-----------------|
| `era5_na` | ERA5 Historical | North America | 0.25° | Quarterly |
| `era5_tx` | ERA5 Historical | Texas | 0.25° | Quarterly |
| `hrrr_history` | HRRR Historical | CONUS | ~3 km | Monthly archives |
| `hrrr_forecast` | HRRR Forecast | CONUS | ~3 km | Every 6 h (48-h horizon) |
| `noaa_forecast` | NOAA/GFS Forecast | North America | 0.25° | Every 6 h (384-h horizon) |

All files use the **PWW binary format** (Team Overbye custom weather data format).
