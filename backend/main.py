"""FastAPI entrypoint for the Team Overbye Weather Data backend."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

import catalog as catalog_module
import download as download_module
import regions as regions_module
import status as status_module


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


async def _refresh_catalog_background() -> None:
    """Run the (synchronous) catalog refresh off the event loop."""
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, catalog_module.refresh_catalog)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[main] Background catalog refresh failed: {exc}", file=sys.stderr)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Kick off an initial catalog warm-up so the first user request is fast.
    asyncio.create_task(_refresh_catalog_background())
    yield


app = FastAPI(
    title="Team Overbye Weather Data API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

# Serialize region-crop work so concurrent requests can't OOM the Railway worker.
_region_sem = asyncio.Semaphore(1)
# Serialize regular multi-file ZIP builds to cap peak /tmp usage.
_download_sem = asyncio.Semaphore(1)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
async def pipeline_status() -> JSONResponse:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, status_module.get_pipeline_status)
    return JSONResponse(data)


@app.get("/api/catalog")
async def get_catalog() -> JSONResponse:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, catalog_module.get_catalog)
    age = catalog_module.cache_age_seconds()
    # If cache is stale beyond TTL, kick off a background rebuild but still
    # serve the cached payload immediately.
    if age is not None and age > 30 * 60:
        asyncio.create_task(_refresh_catalog_background())
    return JSONResponse(data)


@app.post("/api/catalog/refresh")
async def post_catalog_refresh() -> JSONResponse:
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, catalog_module.refresh_catalog)
    return JSONResponse(data)


@app.get("/api/catalog/refresh")
async def get_catalog_refresh() -> JSONResponse:
    """GET-friendly alias so users can trigger refresh from a browser."""
    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, catalog_module.refresh_catalog)
    return JSONResponse(data)


@app.get("/api/debug/folders")
async def debug_folders() -> JSONResponse:
    """Return the folder IDs the catalog is actually using (env-overridden or default)."""
    folders = {
        "noaa_main":            catalog_module._folder_id("GDRIVE_NOAA_FOLDER_ID", "noaa_main"),
        "noaa_archive":         catalog_module._folder_id("GDRIVE_NOAA_ARCHIVE_FOLDER_ID", "noaa_archive"),
        "hrrr_forecast":        catalog_module._folder_id("GDRIVE_HRRR_FORECAST_FOLDER_ID", "hrrr_forecast"),
        "hrrr_history_main":    catalog_module._folder_id("GDRIVE_HRRR_HISTORY_FOLDER_ID", "hrrr_history_main"),
        "hrrr_history_archive": catalog_module._folder_id("GDRIVE_HRRR_HISTORY_ARCHIVE_FOLDER_ID", "hrrr_history_archive"),
        "era5_quarterly":       catalog_module._folder_id("GDRIVE_ERA5_QUARTERLY_FOLDER_ID", "era5_quarterly"),
        "era5_history_zip":     catalog_module._folder_id("GDRIVE_ERA5_HISTORY_ZIP_FOLDER_ID", "era5_history_zip"),
        "era5_archive":         catalog_module._folder_id("GDRIVE_ERA5_ARCHIVE_FOLDER_ID", "era5_archive"),
    }
    return JSONResponse(folders)


@app.get("/api/debug/folder")
async def debug_folder(
    folder_id: str = Query(..., description="Drive folder ID to inspect"),
    limit: int = Query(20, ge=1, le=200),
) -> JSONResponse:
    """Return raw filenames in a Drive folder (with subfolders) for debugging."""
    def _list() -> list[dict[str, str]]:
        client = catalog_module.DriveClient()
        files = client.list_files(folder_id)
        return [{"name": f.get("name", ""), "id": f.get("id", "")} for f in files[:limit]] + [
            {"_total_count": str(len(files))}  # type: ignore[dict-item]
        ]

    loop = asyncio.get_running_loop()
    data = await loop.run_in_executor(None, _list)
    return JSONResponse({"folder_id": folder_id, "files": data})


@app.get("/api/download")
async def download(
    source: str = Query(..., description="Data source identifier"),
    dates: str = Query(..., description="Comma-separated list of date keys"),
):
    date_keys = download_module.parse_dates_param(dates)

    loop = asyncio.get_running_loop()
    catalog_data = await loop.run_in_executor(None, catalog_module.get_catalog)

    if len(date_keys) == 1:
        # Proxy through service account — bypasses Drive virus-scan confirmation page.
        file_id = download_module.get_file_id(source, date_keys[0], catalog_data)
        size = await loop.run_in_executor(None, download_module.get_drive_file_size, file_id)
        filename = download_module._filename_for(source, date_keys[0])
        headers: dict[str, str] = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }
        if size:
            headers["Content-Length"] = str(size)
        return StreamingResponse(
            iterate_in_threadpool(download_module.stream_drive_file(file_id)),
            media_type="application/octet-stream",
            headers=headers,
        )

    async with _download_sem:
        entries = download_module.collect_entries(source, date_keys, catalog_data)

        def _build() -> str:
            return download_module.build_zip_stream(entries)

        zip_path = await loop.run_in_executor(None, _build)
        filename = download_module.zip_filename_for(source, date_keys)

        async def _stream_and_cleanup():
            try:
                with open(zip_path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        yield chunk
            finally:
                try:
                    os.unlink(zip_path)
                except OSError:
                    pass

        return StreamingResponse(
            _stream_and_cleanup(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@app.get("/api/regions")
async def get_regions() -> JSONResponse:
    return JSONResponse(regions_module._build_payload())


@app.get("/api/download/region")
async def download_region(
    source: str = Query(...),
    dates: str = Query(...),
    region_layer: str | None = Query(None),
    region_ids: str | None = Query(None),
    bbox: str | None = Query(None),
    time_start: str | None = Query(None, description="ISO datetime, e.g. 2026-05-21T06:00:00"),
    time_end: str | None = Query(None, description="ISO datetime, e.g. 2026-05-21T18:00:00"),
):
    have_ids = bool(region_ids and region_ids.strip())
    have_bbox = bool(bbox and bbox.strip())
    if have_ids and have_bbox:
        raise HTTPException(status_code=400, detail="Provide exactly one of region_ids or bbox, not both")
    if not have_ids and not have_bbox:
        raise HTTPException(status_code=400, detail="Provide region_ids or bbox")

    if have_ids:
        if region_layer not in ("states", "iso"):
            raise HTTPException(status_code=400, detail="region_layer must be 'states' or 'iso' when region_ids is given")
        ids = [x.strip() for x in region_ids.split(",") if x.strip()]
        try:
            bboxes = [regions_module.get_bbox(region_layer, rid) for rid in ids]
            resolved = regions_module.union_bbox(bboxes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError("bbox must have exactly 4 floats: lat_max,lon_min,lat_min,lon_max")
            lat_max, lon_min, lat_min, lon_max = parts
            if not (-90 <= lat_min < lat_max <= 90 and -180 <= lon_min < lon_max <= 180):
                raise ValueError("bbox out of range or inverted (lat_max > lat_min, lon_max > lon_min required)")
            resolved = (lat_max, lon_min, lat_min, lon_max)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid bbox: {exc}")

    region_tag = "+".join(ids) if have_ids else "custom"

    area = (resolved[0] - resolved[2]) * (resolved[3] - resolved[1])
    if area >= 2380 and source in ("hrrr_history", "hrrr_history_archive"):
        raise HTTPException(
            status_code=413,
            detail={
                "detail": "Requested area exceeds server memory limit for HRRR monthly archives.",
                "sdk_hint": f"Use: client.hrrr.download_region(months=[...], bbox={resolved}, dest='./data/')",
            },
        )

    def _parse_iso_to_epoch(s: str, param: str) -> float:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid {param}: {s!r} (use ISO format, e.g. 2026-05-21T06:00:00)")

    t_start_epoch = _parse_iso_to_epoch(time_start, "time_start") if time_start else None
    t_end_epoch = _parse_iso_to_epoch(time_end, "time_end") if time_end else None

    def _time_tag() -> str:
        if not (t_start_epoch or t_end_epoch):
            return ""
        from datetime import datetime, timezone
        fmt = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dH%H") if ts else ""
        s, e = fmt(t_start_epoch), fmt(t_end_epoch)
        if s and e:
            return f"_T{s}to{e}"
        return f"_T{s or e}"

    ttag = _time_tag()

    date_keys = download_module.parse_dates_param(dates)
    loop = asyncio.get_running_loop()
    catalog_data = await loop.run_in_executor(None, catalog_module.get_catalog)

    async with _region_sem:
        if len(date_keys) == 1:
            pww_bytes = await loop.run_in_executor(
                None, download_module.fetch_and_crop, source, date_keys[0], resolved, catalog_data,
                t_start_epoch, t_end_epoch,
            )
            filename = f"{source}_{date_keys[0]}_{region_tag}{ttag}.pww"
            return Response(
                content=pww_bytes,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(pww_bytes)),
                },
            )

        filename = f"{source}_{region_tag}{ttag}_bundle_{len(date_keys)}_files.zip"

        async def _stream_zip():
            fd, zip_path = tempfile.mkstemp(suffix=".zip", dir="/tmp")
            os.close(fd)
            try:
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                    for key in date_keys:
                        try:
                            pww_bytes = await loop.run_in_executor(
                                None, download_module.fetch_and_crop, source, key, resolved, catalog_data,
                                t_start_epoch, t_end_epoch,
                            )
                            zf.writestr(f"{source}_{key}_{region_tag}{ttag}.pww", pww_bytes)
                            del pww_bytes
                        except Exception as exc:
                            print(f"[region] skip {key}: {exc}", file=sys.stderr)
                with open(zip_path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        yield chunk
            finally:
                try:
                    os.unlink(zip_path)
                except OSError:
                    pass

        return StreamingResponse(
            _stream_zip(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
