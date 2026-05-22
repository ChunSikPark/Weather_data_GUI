# Team Overbye Weather Data Portal — CLAUDE.md

Project context for AI agents working on this repo. Read this before touching code.

## What this is

A weather data download portal for Texas A&M Team Overbye research. Users browse and download weather datasets (ERA5, HRRR, NOAA/GFS) that live as files in Google Drive folders. The backend exposes a catalog/download API; the frontend is a static site.

- **Backend**: FastAPI (Python), deployed on Railway → `https://weatherdatagui-production.up.railway.app`
- **Frontend**: Static HTML/JS/CSS, deployed on Cloudflare Pages → `https://weather-data-gui.pages.dev`
- **Data**: Google Drive (service account, read-only)
- **SDK**: `TeamOverbyeWeather` Python package on PyPI (in `package/`)
- **Repo**: https://github.com/ChunSikPark/Weather_data_GUI

## Architecture

```
frontend/ (Cloudflare Pages)
  ├ index.html       Step 1/2/3 picker UI + region filter panel
  ├ main.js          State, API calls, render functions
  └ styles.css       "Scientific Dark" aesthetic (Bencium-inspired)

backend/ (Railway, Docker)
  ├ main.py          FastAPI app, endpoints
  ├ catalog.py       Drive scanning, regex matching, 30-min cache
  ├ download.py      ZIP bundling, source key lookup, fetch_and_crop()
  ├ pww_io.py        PWW VERSION 2 read/crop/write (numpy-based)
  ├ regions.py       Region catalog: 51 state bboxes + ISO zones from shapefile
  └ status.py        Pipeline health

package/TeamOverbyeWeather/  Python SDK (pip install TeamOverbyeWeather)
  ├ pww_io.py        Copy of backend/pww_io.py for local crop
  └ sources/         hrrr.py, noaa.py, era5.py — each has download_region()
```

## Critical: Google Drive folder IDs

These IDs are **hardcoded directly in `_build_noaa()`** because Railway has stale `GDRIVE_NOAA_FOLDER_ID` env vars that point to wrong folders. Do not "refactor" them back to env-var lookup unless you also clear the env vars on Railway.

| Source | Folder ID | Naming convention |
|---|---|---|
| ERA5 quarterly | `12U8PNHHGIxCy8_GRzsF2KxZ4GneMWy6h` | quarter-tagged ZIPs |
| ERA5 history zip | `1O8VjwFKXCJ3DR56_UEep-rXyb7OHNGMZ` | quarter-tagged ZIPs |
| ERA5 archive | `1PD_y38k6x8HjDR8Wv-15NsZ6pdZ9pVPz` | quarter-tagged ZIPs |
| HRRR forecast | `1yuEH5020Nh-Km5_PvYfmVpWTQIhzI1Iz` | `YYYY-MM-DDTHHZ_sfc_48_CONUS.zip` |
| HRRR history (current year, daily) | `1Uc-tuSPEnh7rJzC3nFvxndFvULrsNe-U` | `CONUS_YYYY_MM_DD.zip` (or `.pww.gz`) |
| HRRR history (archive, monthly) | `1_govjuY2WV0TqHp_7PwVVtrGPCDU-I9v` | `CONUSYYYY_MM.zip` or `CONUSYYYY_MM.pww.gz` |
| NOAA recent | `1kAOe-dGHByzZHijHGo8rmL7x4KY6OMav` | `Forecast_NorthAmerica_RunYYYY-MM-DDTHHZ.pww` |
| NOAA archive | `1TTa-bDV88sSf4strSW649UHPRddMHJtr` | same as above |

The service account email from `service_account.json`'s `client_email` field MUST be granted Viewer access on every folder above.

## Catalog structure (returned by `GET /api/catalog`)

```json
{
  "era5_na":               { "quarters": [...], "file_ids": {...} },
  "era5_tx":               { "quarters": [...], "file_ids": {...} },
  "hrrr_forecast":         { "cycles":   [...], "file_ids": {...} },
  "hrrr_history":          { "months":   [...], "file_ids": {...} },  // legacy combined
  "hrrr_history_current":  { "days":     [...], "file_ids": {...} },  // YYYY-MM-DD keys
  "hrrr_history_archive":  { "months":   [...], "file_ids": {...} },  // YYYY-MM keys
  "noaa_forecast":         { "cycles":   [...], "file_ids": {...} },  // legacy combined
  "noaa_forecast_recent":  { "cycles":   [...], "file_ids": {...} },  // from main folder
  "noaa_forecast_archive": { "cycles":   [...], "file_ids": {...} }   // from archive folder
}
```

Date key formats:
- ERA5: `YYYY-Qn` (e.g. `2025-Q1`)
- HRRR/NOAA forecast cycles: `YYYY-MM-DDTHHZ`
- HRRR archive months: `YYYY-MM`
- HRRR current days: `YYYY-MM-DD`

## Frontend flow (Step 1 → 2 → 3)

1. **Step 1 — Source**: ERA5 / HRRR / NOAA cards.
2. **Step 2 — Type**: per-source sub-types defined in `TYPE_DEFS` in `main.js`:
   - ERA5: `historical`
   - HRRR: `current` | `archive` | `forecast`
   - NOAA: `recent` | `archive`
3. **Step 3 — Dates**: picker is selected by `renderStep3()` based on (source, type):
   - `renderQuarterPicker()` — ERA5 (with From/To range selector)
   - `renderMonthPicker(catalogKey)` — HRRR archive months
   - `renderDayPicker(catalogKey)` — HRRR current year days
   - `renderCyclePicker(catalogKey)` — HRRR forecast / NOAA cycles

`getApiSourceKey()` in `main.js` maps (source, type) → catalog/download API source string. Keep this in sync with `_SOURCE_LOOKUP` in `download.py`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | health check |
| GET | `/api/status` | pipeline status |
| GET | `/api/catalog` | full catalog (cached 30 min) |
| GET | `/api/catalog/refresh` | force rebuild (browser-friendly) |
| POST | `/api/catalog/refresh` | force rebuild |
| GET | `/api/download?source=...&dates=...` | both single and multi stream via service account (bypasses Drive virus-scan); single returns the bare file, multi returns a ZIP bundle |
| GET | `/api/regions` | region catalog: `{states:[{id,name,bbox},...], iso:[...]}` |
| GET | `/api/download/region?source=...&dates=...&region_layer=...&region_ids=...` | fetch + crop to bbox; single=.pww, multi=ZIP |
| GET | `/api/debug/folders` | resolved folder IDs the catalog is using |
| GET | `/api/debug/folder?folder_id=...&limit=N` | raw filenames in a Drive folder |

The two debug endpoints are gold for diagnosing "data not showing" issues — always use them before guessing.

### `/api/download/region` params

| Param | Required | Description |
|---|---|---|
| `source` | yes | Catalog source key (e.g. `noaa_forecast_recent`) |
| `dates` | yes | Comma-separated date keys |
| `region_layer` | yes | `states`, `iso`, or `custom` |
| `region_ids` | one of | Comma-separated postal codes or ISO zone IDs |
| `bbox` | one of | `lat_max,lon_min,lat_min,lon_max` floats (custom layer) |

Returns 400 if both/neither of `region_ids`/`bbox` are given. Returns 413 with `{"sdk_hint":"..."}` if bbox area ≥ 2380 sq-deg and source is `hrrr_history` or `hrrr_history_archive` (CONUS-scale request — use SDK local crop instead).

## Region crop system

- **`backend/regions.py`**: 51-state bbox dict (hardcoded, keyed by 2-letter postal code) + ISO zones loaded from `D:\Research_Projects\Inputs\Shape_Files\ISO_REGIONS\ISO_Regions_cleaned.shp` via `pyshp`. Alaska clipped to `(71.4, -180.0, 51.2, -129.9)` to avoid antimeridian union issues.
- **`backend/pww_io.py`**: `read_pww(bytes)`, `read_pww_file(path)` (mmap, low RAM), `crop_to_bbox(header, stations, arr, bbox_tuple)`, `write_pww(header, stations, arr)`. Longitude axis descends (east→west), 255 = NaN sentinel. Always `.copy()` after slicing. **Only HRRR files are ZIPs** containing a `.pww` inside; ERA5 and NOAA files are bare `.pww` (VERSION 1 until automation is updated to VERSION 2). The crop pipeline streams Drive files to `/tmp` and mmaps them to keep peak RAM ~64 MB.
- **ISO shapefile**: `.prj` is checked at startup. If it's a projected CRS (starts with `PROJCS[`) or lacks WGS84 datum, the module logs to stderr and `iso` returns `[]` — ISO tab shows empty list, no crash.
- **Memory guard**: `asyncio.Semaphore(1)` on `/api/download/region` prevents concurrent crop ops on Railway's 512 MB container. CONUS-scale HRRR archive requests are blocked at 413 — use `client.hrrr.download_region()` which crops locally.
- **SDK `download_region()`**: available on `HRRRClient`, `NOAAClient`, `ERA5Client`. HRRR archive + large bbox triggers `_local_crop()` (downloads per-month, unzips, crops with `pww_io` locally). `package/TeamOverbyeWeather/pww_io.py` is a copy of the backend module.
- **Frontend region panel**: `<details>` element rendered once after first date is selected (in `renderRegionPanelOnce()`). Three tabs: States (button grid, multi-select), ISO Zones (single-select list), Custom (4 float inputs). `state.selectedRegions = {layer, ids?, bbox?}` drives `buildDownloadURL()`. Resets on source/type change.
- **bbox format everywhere**: `(lat_max, lon_min, lat_min, lon_max)` — note lon comes before lat_min. This matches `extract_region_pww.py`'s `REGIONS` dict convention.

## Painful lessons (read these before debugging)

1. **Service account credentials**: Production reads from `GDRIVE_CREDENTIALS_JSON_CONTENT` env var (the entire JSON as a string). Local dev uses `/app/credentials/service_account.json`. PyDrive2 OAuth tokens are NOT service account JSONs — easy mistake.

2. **Railway env vars override defaults**: `_folder_id(env_key, default_key)` reads env vars first. Railway has at least one stale folder-ID env var (`GDRIVE_NOAA_FOLDER_ID = 1wICJMuO0MRopG3hpPFt7MzFmx5M33v4R` — old wrong NOAA folder). NOAA folder IDs are now hardcoded in `_build_noaa()` to dodge this. If you need to change them, edit the constants directly.

3. **Drive folders can have subfolders**: `list_files()` recurses up to 4 levels deep. If you see "folder has files but catalog is empty", check the regex first, then check folder access.

4. **Filename conventions vary wildly between folders**:
   - HRRR forecast: `2026-05-07T12Z_sfc_48_CONUS.zip` (date-prefix)
   - HRRR history daily: `CONUS_2026_05_06.zip` (CONUS-prefix, underscores)
   - HRRR history monthly: `CONUS2026_04.zip` (no underscore between CONUS and year) — also `.pww.gz` for older years
   - NOAA: `Forecast_NorthAmerica_RunYYYY-MM-DDTHHZ.pww`
   - **Always run `/api/debug/folder` to see actual filenames** before writing/changing a regex.

5. **HRRR history regex is intentionally loose** on extension: `[A-Za-z0-9.]+$` matches `.zip`, `.pww.gz`, `.pww`, `.gz`. Don't tighten it to `\.zip$` — older archives are `.pww.gz`.

6. **NOAA "Recent" vs "Archive" is folder-based, not date-based**. Earlier attempts at date-based splitting all failed because the dataset's "newness" doesn't match wall-clock time. Each tab pulls strictly from its own folder.

7. **Cache TTL is 30 minutes**. Use `GET /api/catalog/refresh` to force a rebuild after deployment or after sharing a new folder with the service account.

8. **Single-file downloads go through the service account, not direct Drive URLs.** Large Drive files (>~100 MB) trigger a virus-scan confirmation HTML page when fetched via `webContentLink`, which produces silent failures (empty downloads or HTML where binary data should be). All download paths now use `MediaIoBaseDownload` through the service account; the dead-code helper `get_file_url` in `download.py` remains as a landmine — don't reintroduce it.

9. **`_FILENAME_PATTERNS` extension MUST match the actual Drive file format.** If the suggested filename says `.zip` but the bytes are bare `.pww`, the user's PWW viewer rejects the extracted file. ERA5 and NOAA single files are `.pww`; HRRR single files are `.zip` (containing one `.pww`). Inside a multi-file ZIP bundle, each entry inherits this same naming, so getting it right matters in both single and bundle contexts.

10. **Concurrency caps protect the worker from threadpool starvation and `/tmp` exhaustion.** `_single_dl_sem(4)` caps simultaneous single-file Drive streams; `_region_sem(1)` serializes region crops; `_download_sem(1)` serializes multi-file ZIP builds. The single-file semaphore wraps the streaming generator (not just the route handler) so the cap holds for the full duration of the transfer.

11. **`_fetch_drive_to_tmp` must clean up its temp file on any error** — a Drive error mid-download otherwise orphans a multi-GB `/tmp` file with no reaper. Wrap the body in `try: ... except BaseException: os.unlink(path); raise`.

12. **Frontend uses one unified download flow** — every request goes through `_fetchWithProgress` against `buildDownloadURL()`. While waiting for the first byte, the frontend rotates through phase-specific status messages every 20s ("Downloading from Drive…", "Cropping to region…", "Building the ZIP archive…") so the user knows what stage the server is at; once bytes start flowing, it switches to "Downloading — X MB / Y MB (Z%)". Don't reintroduce per-case branching with divergent messages.

## Deployment

### Frontend (Cloudflare Pages)
Auto-deploys on push to `main`. Build output dir = `frontend`. No build step.

### Backend — two options

**Option A: Railway (current)**

Railway auto-deploys on push to `main` (~90s). Verify with `curl /api/health` then `curl /api/debug/folders`.
Env vars needed: `GDRIVE_CREDENTIALS_JSON_CONTENT`, `CORS_ORIGINS=https://weather-data-gui.pages.dev`.
Note: Railway Starter plan has 512 MB RAM — the backend is tuned for this limit (semaphores prevent concurrent OOM). NOAA folder env vars on Railway are stale; ignore them (folder IDs are hardcoded in `catalog.py`).

The pipeline status indicator will read `unknown` for every source on Railway because the `config/alert_state.json` file produced by the weather-auto pipelines is not available there. This is cosmetic — the data API works regardless.

**Option B: Self-hosted Docker + Cloudflare Tunnel (alternative)**

The backend runs on the team's automation computer via Docker. Cloudflare Tunnel exposes it to the internet without port forwarding.

```bash
# 1. Copy and fill in credentials
cp .env.example .env
# Edit .env: set GDRIVE_CREDENTIALS_JSON_CONTENT and CORS_ORIGINS

# 2. Start the backend
docker compose up -d --build

# 3. Install cloudflared and create a tunnel (one-time setup)
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
cloudflared tunnel login
cloudflared tunnel create weather-backend
cloudflared tunnel route dns weather-backend <your-subdomain.yourdomain.com>
cloudflared tunnel run --url http://localhost:8000 weather-backend

# 4. Update CORS_ORIGINS in .env to the tunnel URL, then restart:
docker compose restart backend
```

After the tunnel is running, update the frontend's `API_BASE` in `frontend/main.js` to the tunnel URL and push.

**Verify after start:**
```bash
curl https://your-tunnel-url/api/health
curl https://your-tunnel-url/api/debug/folders
```


## Frontend extras worth knowing

- ERA5 has a **From/To range selector** above the quarter grid — pick a start, pick an end, click "Select Range" and every available quarter in between gets highlighted.
- HRRR Current Year picker shows individual **days** (not months), because the daily folder has individual day ZIPs.
- "Pipelines" status dots in the header poll `/api/status` every 5 minutes.
- Multi-file downloads are bundled as a streaming ZIP (`ZIP_STORED`, no recompression).
- **Region filter panel** appears below the date picker once at least one date is selected. Tabs: States (51 buttons, multi-select → union bbox), ISO Zones (single-select), Custom (4 inputs). Panel is hidden until dates are chosen; resets when source or type changes.

## Common workflows

**"NOAA shows no data"**
1. `curl /api/debug/folders` — confirm the folder ID being used
2. `curl /api/debug/folder?folder_id=<that_id>` — confirm files exist + see filenames
3. If folder ID is wrong but files exist: env var override → hardcode it in `_build_noaa()`
4. If folder is empty: ask user for the right folder ID
5. If folder has files but they don't match regex: check filename pattern, fix `_RE_NOAA`

**"HRRR shows no data"**
1. Same as above with `_build_hrrr_history()` and `_RE_HRRR_HISTORY_DAY` / `_RE_HRRR_HISTORY_MONTH`
2. Daily folder uses `CONUS_YYYY_MM_DD.*`, monthly uses `CONUSYYYY_MM.*` — different regexes

**"Adding a new data source"**
1. Add folder ID to `_DEFAULT_FOLDERS` in `catalog.py`
2. Add a `_build_<source>()` function and call it from `build_catalog()`
3. Add the new key to `_empty_catalog()`
4. Add `_SOURCE_LOOKUP` + `_FILENAME_PATTERNS` entries in `download.py`
5. Add `TYPE_DEFS` entry in `main.js`, update `getApiSourceKey()` and `renderStep3()`
6. Update `API_DOCS.md`

## Tone note

The user is a researcher, not a developer. Respond directly to what's asked, don't over-explain. If something isn't working, USE THE DEBUG ENDPOINTS before guessing — guessing wastes their time and patience.
