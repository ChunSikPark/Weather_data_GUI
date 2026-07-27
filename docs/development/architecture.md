# Architecture

How the pieces fit together, for anyone modifying the system.

## Overview

```text
  Web portal (Cloudflare Pages)        Python package (PyPI)
  weather-data-gui.pages.dev           TeamOverbyeWeather
              |                                  |
              +----------------+-----------------+
                               |
                     FastAPI backend (Railway)
                weather-data-gui.up.railway.app
                               |
                     Google Drive (service account)
```

Both front ends are thin. All catalog logic, cropping, and Drive access live in
the backend; the browser and the Python package only make HTTP requests.

## Repository layout

```text
frontend/                  static site — index.html, main.js, styles.css
backend/
  main.py                  FastAPI app, endpoints, concurrency gates
  catalog.py               Drive scanning, filename matching, 30-min cache
  download.py              file lookup, ZIP bundling, fetch_and_crop()
  pww_io.py                PWW read / crop / write
  regions.py               state bounding boxes and ISO zones
  status.py                pipeline health
package/TeamOverbyeWeather/
  client.py                WeatherClient.download() and discovery
  registry.py              (source, type) -> API key mapping
  localcrop.py             client-side crop fallback
  pww_io.py                copy of the backend module
  errors.py                exception types
  sources/                 back-compatible per-source wrappers
docs/                      this documentation
```

## Three places that must agree

Adding or renaming a data source means touching all three:

| Location | What it defines |
|---|---|
| `backend/download.py` — `_SOURCE_LOOKUP` | API key → catalog key and list key |
| `package/.../registry.py` — `_API_KEYS`, `_TYPES` | user-facing source/type → API key |
| `frontend/main.js` — `TYPE_DEFS`, `getApiSourceKey()` | the portal's picker |

They are kept deliberately parallel. If a source works in the portal but not the
package, this mismatch is the first thing to check.

`package/TeamOverbyeWeather/pww_io.py` is a **copy** of `backend/pww_io.py`.
Change one, copy to the other — a divergence here produces crops that differ
between server and client.

## The crop pipeline

`fetch_and_crop()` in `backend/download.py` is the core:

1. Resolve `(source, date_key)` to a Drive file id
2. Stream the file to `/tmp` — never fully into memory
3. Detect the shape **by content**, not by source name
4. Crop each part to the bounding box, then stitch along time
5. Apply the time crop if requested
6. Write PWW bytes and return them

Step 3 matters. `zipfile.is_zipfile()` decides whether to unzip, so a source that
changes format does not need a code change. Four on-disk shapes are handled: a
bare `.pww`, a zip with one `.pww`, a zip with four quarter `.pww` files, and a
zip of daily zips.

Cropping each member *before* concatenating keeps peak memory at one cropped
member instead of a whole month.

`package/TeamOverbyeWeather/localcrop.py` mirrors this for the client-side
fallback, reading from disk rather than Drive.

## Concurrency and load shedding

Heavy endpoints sit behind `_Gate(concurrency, max_wait)` in `main.py`. Each gate
runs a few requests concurrently, queues the rest, and returns **503 with
`Retry-After`** once too many are waiting — shedding load rather than accepting
work that would exhaust memory.

| Gate | Covers | Environment variable | Default |
|---|---|---|---|
| `_single_gate` | single-file streams | `SINGLE_CONCURRENCY` | 6 |
| `_region_gate` | region crops | `REGION_CONCURRENCY` | 2 |
| `_download_gate` | multi-file ZIP builds | `BUNDLE_CONCURRENCY` | 2 |
| all | queue depth before 503 | `MAX_DOWNLOAD_QUEUE` | 50 |

All are tunable on Railway without a code change. Region crops are the heaviest
path — lower `REGION_CONCURRENCY` first if memory is tight.

For streamed responses the slot is taken *before* the response is returned and
released in the generator's `finally`, so the limit holds for the whole transfer
rather than just the headers.

## Why cropping is server-side

Client-side cropping always requires transferring the whole file first. Measured:

| Request | Transferred |
|---|---|
| NOAA cycle, uncropped | 120 MB |
| Cropped to Texas | 7.3 MB |
| Texas plus a 6-hour window | 240 KB |
| HRRR 15-minute day, uncropped | 534 MB |

The server is the only place that can avoid moving the large number. The gates
above exist so it can do that safely; the 413 fallback exists for the one case
where it genuinely cannot.

## Deployment

**Frontend** — Cloudflare Pages, auto-deploys from `main`. Output directory
`frontend`, no build step.

**Backend** — Railway, auto-deploys from `main`, roughly 90 seconds. The service
root directory must be `backend`, since the Dockerfile lives there. Required
environment variables are `GDRIVE_CREDENTIALS_JSON_CONTENT` (the whole
service-account JSON) and `CORS_ORIGINS`.

After deploying, verify:

```bash
curl <url>/api/health
curl <url>/api/debug/folders
curl <url>/api/catalog/refresh
```

Do not set `GDRIVE_*_FOLDER_ID` variables — several are stale, so folder ids are
hard-coded in `catalog.py`.

**Package** — built from `package/` and published to PyPI.

**Documentation** — this site, built by Read the Docs from `docs/`.
