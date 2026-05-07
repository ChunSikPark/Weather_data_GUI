"""FastAPI entrypoint for the Team Overbye Weather Data backend."""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

import catalog as catalog_module
import download as download_module
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
)


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
        try:
            url = download_module.get_file_url(source, date_keys[0], catalog_data)
        except HTTPException:
            raise
        return RedirectResponse(url=url, status_code=302)

    entries = download_module.collect_entries(source, date_keys, catalog_data)

    def _build() -> "BytesIO":  # type: ignore[name-defined]
        return download_module.build_zip_stream(entries)

    buf = await loop.run_in_executor(None, _build)
    filename = download_module.zip_filename_for(source, date_keys)
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    return StreamingResponse(
        download_module.iter_zip_chunks(buf),
        media_type="application/zip",
        headers=headers,
    )
