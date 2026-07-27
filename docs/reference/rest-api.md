# REST API

The Python package is a wrapper around a plain HTTP API. Use it directly from
MATLAB, R, `curl`, or anything else that speaks HTTP.

**Base URL:** `https://weather-data-gui.up.railway.app`

No authentication is required.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness check |
| GET | `/api/status` | pipeline health |
| GET | `/api/catalog` | full catalog (cached 30 min) |
| GET | `/api/catalog/refresh` | force a catalog rebuild |
| GET | `/api/download` | download whole files |
| GET | `/api/regions` | states and ISO zones with bounding boxes |
| GET | `/api/download/region` | download cropped by region and/or time |
| GET | `/api/extreme/video` | event animation (supports range requests) |
| GET | `/api/extreme/coverage` | zone coverage map PNG |
| GET | `/api/debug/folders` | which Drive folders are in use |
| GET | `/api/debug/folder` | raw filenames in a folder |

## `/api/catalog`

```bash
curl https://weather-data-gui.up.railway.app/api/catalog
```

```json
{
  "era5_na":                     {"quarters": ["2026-Q3"], "file_ids": {}},
  "hrrr_forecast":               {"cycles":   ["2026-07-22T12Z"], "file_ids": {}},
  "hrrr_history_current":        {"days":     ["2026-07-21"], "file_ids": {}},
  "hrrr_history_archive":        {"months":   [], "file_ids": {}},
  "hrrr_history_hourly_current": {"days":     ["2026-07-21"], "file_ids": {}},
  "hrrr_history_hourly_archive": {"months":   ["2026-06", "2014-12"], "file_ids": {}},
  "noaa_forecast_recent":        {"cycles":   ["2026-07-22T12Z"], "file_ids": {}},
  "noaa_forecast_archive":       {"cycles":   ["2026-07-06T18Z"], "file_ids": {}},
  "era5_tx":                     {"quarters": [], "file_ids": {}}
}
```

The list key differs per source — `quarters`, `months`, `days`, or `cycles`.

## `/api/download`

| Parameter | Required | Description |
|---|---|---|
| `source` | yes | catalog source key, e.g. `noaa_forecast_recent` |
| `dates` | yes | comma-separated date keys |

One date returns the file itself; several return a ZIP bundle.

```bash
curl -OJ "https://weather-data-gui.up.railway.app/api/download\
?source=noaa_forecast_recent&dates=2026-07-22T12Z"
```

## `/api/download/region`

| Parameter | Required | Description |
|---|---|---|
| `source` | yes | catalog source key |
| `dates` | yes | comma-separated date keys |
| `region_layer` | with `region_ids` | `states`, `iso`, or `custom` |
| `region_ids` | one of | comma-separated postal codes or ISO zone ids |
| `bbox` | one of | `lat_max,lon_min,lat_min,lon_max` |
| `time_start` | no | ISO datetime, e.g. `2026-07-22T12:00:00` |
| `time_end` | no | ISO datetime |

Exactly one of `region_ids` / `bbox` must be given. One date returns a `.pww`;
several return a ZIP of `.pww` files.

```bash
curl -OJ "https://weather-data-gui.up.railway.app/api/download/region\
?source=noaa_forecast_recent&dates=2026-07-22T12Z\
&region_layer=states&region_ids=TX\
&time_start=2026-07-22T12:00:00&time_end=2026-07-22T18:00:00"
```

Times are UTC and both bounds are inclusive. Either may be omitted to leave that
side open.

## `/api/extreme/video`

| Parameter | Required | Description |
|---|---|---|
| `key` | yes | event key, e.g. `2021-02-14_Winter_Storm_Uri_Texas` |

Returns `video/mp4`. **Honours HTTP range requests**, replying `206 Partial
Content` with a `Content-Range` header, so a player fetches only what it needs:

```bash
curl -H "Range: bytes=0-1048575" \
  "https://weather-data-gui.up.railway.app/api/extreme/video\
?key=2021-02-14_Winter_Storm_Uri_Texas" -o part.mp4
```

```text
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1048575/26188969
Content-Type: video/mp4
```

Each response is capped at 4 MB regardless of the range asked for; request more
to continue. A request with no `Range` header returns the whole file with `200`.
A malformed or past-the-end range returns `416`.

## `/api/extreme/coverage`

| Parameter | Required | Description |
|---|---|---|
| `zone` | yes | ISO zone name, e.g. `Texas` |

Returns `image/png`. Both extreme endpoints are cached for a day.

## `/api/regions`

```json
{
  "states": [{"id": "TX", "name": "Texas", "layer": "states",
              "bbox": [36.5, -106.6, 25.8, -93.5]}],
  "iso":    [{"id": "ERCOT", "name": "ERCOT", "layer": "iso",
              "bbox": [36.5, -106.6, 25.8, -93.5]}]
}
```

`bbox` is `[lat_max, lon_min, lat_min, lon_max]`.

## Status codes

| Code | Meaning | What to do |
|---|---|---|
| 400 | bad parameters | check bbox ordering, ISO date format, layer name |
| 404 | no file for that source and date | list the catalog first |
| 413 | area too large to crop server-side | shrink the area, or download whole and crop locally |
| 502 | processing failed | retry; report if it persists |
| 503 | download queue full | honour `Retry-After` and retry |

A 413 body carries a hint:

```json
{"detail": {
  "detail": "Requested area exceeds server memory limit for HRRR monthly archives.",
  "sdk_hint": "Use: client.hrrr.download_region(months=[...], bbox=(...), dest='./data/')"
}}
```

## Rate limiting

There is no request-count limit, but heavy endpoints run behind bounded queues —
a few requests run concurrently, the rest wait, and once the queue is full the
server replies **503** with `Retry-After` rather than accepting work it cannot
finish. Honour that header. The Python client does this for you.

## Debug endpoints

When data does not appear, these show what the server actually sees:

```bash
curl https://weather-data-gui.up.railway.app/api/debug/folders
curl "https://weather-data-gui.up.railway.app/api/debug/folder?folder_id=<id>&limit=20"
```

The first lists the resolved Drive folder ids; the second lists real filenames in
one. Together they distinguish a permissions problem from a filename-pattern
problem.

:::{warning}
The `files` array from `/api/debug/folder` ends with a **sentinel entry** that
is not a file:

```json
{"folder_id": "1kAOe...", "files": [
  {"name": "Forecast_NorthAmerica_Run2026-07-22T12Z.pww", "id": "1ACp..."},
  {"_total_count": "2594"}
]}
```

It carries the folder's true size, which is useful — but it has no `name` key,
so code that does `entry["name"]` over the whole array raises `KeyError`. Filter
on `"name" in entry`.
:::
