# Team Overbye Weather Data Portal

A public website for browsing and downloading Texas A&M weather research data from Google Drive — by source, region, and date range. Includes a companion Python package (`TeamOverbyeWeather`) for programmatic access.

---

## Architecture

```
weather-website/
  frontend/          HTML + CSS + JS  →  Cloudflare Pages
  backend/           FastAPI          →  Railway / Render (Docker)
  package/           Python SDK       →  PyPI (pip install TeamOverbyeWeather)
```

```
Browser
  │  static assets
  ▼
Cloudflare Pages (frontend/)
  │  /api/* requests (proxied via Cloudflare)
  ▼
Railway / Render (backend/ Docker container)
  │  PyDrive2 service account
  ▼
Google Drive  ←── weather_auto pipelines upload here
  
notify_bot/config/alert_state.json  ──── mounted into backend container
```

---

## Quick Start — Local Development

### Prerequisites
- Python 3.12+
- Google Drive service account JSON key (from `weather_auto/credentials/`)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Copy and configure env vars
cp ../.env.example ../.env
# Edit .env: set GDRIVE_CREDENTIALS_JSON to path of your service account JSON

uvicorn main:app --reload --port 8000
```

API available at `http://localhost:8000`:
- `GET /api/health` — health check
- `GET /api/status` — pipeline status
- `GET /api/catalog` — available files
- `GET /api/download?source=era5_na&dates=2025-Q1` — download file

### Frontend

The frontend is plain HTML/CSS/JS — no build step required.

```bash
cd frontend
python -m http.server 3000
# Open http://localhost:3000
```

By default the frontend points to `http://localhost:8000` for API calls. To point it at a different API, set `window.API_BASE` before loading `main.js`:

```html
<script>window.API_BASE = 'https://api.yoursite.com'</script>
```

---

## Deployment

### Backend — Railway (Recommended)

1. Create a new project at [railway.app](https://railway.app)
2. Connect your GitHub repo, select the `backend/` folder as root (or use monorepo config)
3. Railway auto-detects the Dockerfile and builds it
4. Add environment variables in Railway dashboard (copy from `.env.example`)
5. For `GDRIVE_CREDENTIALS_JSON`: upload the service account JSON as a Railway Volume or embed its content as an env var:
   ```bash
   # Alternative: set as env var
   GDRIVE_CREDENTIALS_JSON_CONTENT='{"type":"service_account",...}'
   ```
6. Note the Railway service URL (e.g. `https://weather-api-production.up.railway.app`)

**Alternative: Render**
- Create a Web Service, Docker environment
- Set env vars in Render dashboard
- Free tier works for low-traffic research use

**Alternative: Docker on existing host**
```bash
cd backend
docker compose up -d --build
```
The `docker-compose.yml` mounts `alert_state.json` from `ALERT_STATE_HOST_PATH`.

### Frontend — Cloudflare Pages

1. Push this repo to GitHub
2. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → Pages → Create a project
3. Connect GitHub repo → select branch `main`
4. Build settings:
   - **Framework preset**: None
   - **Build command**: *(leave empty)*
   - **Build output directory**: `frontend`
5. Add environment variable (optional):
   - `API_BASE` = your Railway/Render backend URL
6. Deploy → Cloudflare gives you a `*.pages.dev` URL

**Point frontend at backend:**
Edit `frontend/index.html` — find this line near the top and set your backend URL:
```html
<script>window.API_BASE = 'https://your-backend.railway.app'</script>
```

**Custom domain:**
In Cloudflare Pages → Custom domains → add your domain.
Then add a Cloudflare Proxy rule to route `/api/*` to your backend — this avoids CORS issues and makes both frontend + backend appear on the same domain.

### Cloudflare Proxy Rule (Optional, Recommended)

In Cloudflare Dashboard → your domain → Rules → Transform Rules → URL Rewrites:
```
If: URI Path starts with /api/
Then: Rewrite to: https://your-backend.railway.app/api/[path]
```

This lets you set `CORS_ORIGINS` to just your domain instead of `*`.

---

## Pipeline Status Integration

The backend reads `alert_state.json` written by `notify_bot`. On the Docker host running both services:

```bash
# In backend/docker-compose.yml, set:
ALERT_STATE_HOST_PATH=/path/to/weather_auto/notify_bot/config/alert_state.json
```

The file is mounted read-only into the backend container at `ALERT_STATE_PATH`.

For Railway/Render deployments where you can't mount a local file: expose `alert_state.json` via a small HTTP endpoint on the notify_bot container (or skip status integration and the UI will show grey "unknown" dots).

---

## Google Drive Setup

1. Share all relevant Drive folders with the service account as **Editor** (or at minimum Viewer):
   - `drive-script-bot@pydrive2-461721.iam.gserviceaccount.com`
2. Place the service account JSON key at the path set in `GDRIVE_CREDENTIALS_JSON`
3. The backend will automatically list and cache all available files on startup

---

## Python Package

```bash
pip install TeamOverbyeWeather
```

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()  # defaults to production API

# List available ERA5 quarters
quarters = client.era5.list_quarters(region="north_america")

# Download ERA5 Q1 2025
client.era5.download(quarters=["2025-Q1"], region="north_america", dest="./data/")

# Latest NOAA forecast
client.noaa.download_latest(dest="./data/")

# Pipeline health
print(client.status())
```

See `package/README.md` for full SDK documentation.

---

## Data Sources

| Source | Type | Region | Resolution | Update frequency |
|--------|------|--------|------------|-----------------|
| ERA5 | Historical | North America / Texas | 0.25° | Monthly (quarterly archives) |
| HRRR | Historical | CONUS | ~3 km | Daily (monthly archives) |
| HRRR | Forecast | CONUS | ~3 km | Every 6 h (48-h horizon) |
| NOAA/GFS | Forecast | North America | 0.25° | Every 6 h (384-h horizon) |

All files use the **PWW binary format** (Team Overbye custom). See `weather_auto/CLAUDE.md` for format spec.

---

## File Naming Reference

| Dataset | File pattern | Example |
|---------|-------------|---------|
| HRRR Forecast | `{YYYY-MM-DD}T{HH}Z_sfc_48_CONUS.zip` | `2026-04-21T06Z_sfc_48_CONUS.zip` |
| HRRR History (monthly) | `{YYYY-MM}_sfc_01_CONUS.zip` | `2026-04_sfc_01_CONUS.zip` |
| NOAA Forecast | `Forecast_NorthAmerica_Run{YYYY-MM-DD}T{HH}Z.pww` | `Forecast_NorthAmerica_Run2026-04-21T06Z.pww` |
| ERA5 Quarterly | `ERA5_{Region}_{YYYY}_Q{N}.zip` | `ERA5_NorthAmerica_2025_Q1.zip` |
