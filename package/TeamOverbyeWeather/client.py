"""WeatherClient — top-level entry point for the Team Overbye Weather Data API."""

from __future__ import annotations

import tempfile
from pathlib import Path

import requests

from . import localcrop, registry
from .errors import RegionTooLargeError, WeatherAPIError
from .utils import download_file, server_detail, to_epoch, to_iso

DEFAULT_BASE_URL = "https://weather-data-gui.up.railway.app"

# Whole-globe box, used when a time crop is requested without a spatial one.
# crop_to_bbox clamps to the file's own grid, so this is a no-op spatially.
_WORLD_BBOX = (90.0, -180.0, -90.0, 180.0)


class WeatherClient:
    """Client for the Team Overbye Weather Data API.

    One call does download, region crop, and time crop::

        c = WeatherClient()
        c.download("hrrr", type="hourly_current", dates="2026-07-21",
                   region="TX", time_start="2026-07-21T06:00",
                   time_end="2026-07-21T18:00", dest="./data")

    Args:
        base_url: Base URL of the weather data API.
        show_progress: Default for per-call progress bars.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        show_progress: bool = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._show_progress = show_progress
        self._catalog_cache: dict | None = None

        # Back-compat namespaces (thin wrappers over download()).
        from .sources.era5 import ERA5Client
        from .sources.extreme import ExtremeClient
        from .sources.hrrr import HRRRClient
        from .sources.noaa import NOAAClient
        self.era5 = ERA5Client(self)
        self.hrrr = HRRRClient(self)
        self.noaa = NOAAClient(self)
        self.extreme = ExtremeClient(self)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Return pipeline health for each source (``ok``/``error``/``unknown``)."""
        return self._json("/api/status")

    def catalog(self, refresh: bool = False) -> dict:
        """Return the full catalog of available files.

        Args:
            refresh: Force the server to rebuild its 30-minute cache, and drop
                this client's in-process cache.
        """
        if refresh:
            self._catalog_cache = self._json("/api/catalog/refresh")
        elif self._catalog_cache is None:
            self._catalog_cache = self._json("/api/catalog")
        return self._catalog_cache

    def sources(self) -> list[str]:
        """List the source names accepted by :meth:`download`."""
        return registry.all_sources()

    def types(self, source: str) -> list[str]:
        """List the sub-types available for *source*."""
        return registry.types_for(source)

    def list(self, source: str, type: str | None = None) -> list[str]:
        """List available date keys for a source, newest first.

        Args:
            source: ``"era5"``, ``"hrrr"``, ``"noaa"``, or a full API key.
            type: Sub-type — see :meth:`types`.

        Returns:
            Date keys in the format that source uses: ``YYYY-Qn`` (ERA5),
            ``YYYY-MM`` (monthly archives), ``YYYY-MM-DD`` (daily), or
            ``YYYY-MM-DDTHHZ`` (forecast cycles).
        """
        api_key = registry.resolve(source, type)
        section = self.catalog().get(api_key) or {}
        return sorted(section.get(registry.list_key(api_key), []), reverse=True)

    def regions(self) -> dict:
        """Return the region catalog: ``{"states": [...], "iso": [...]}``.

        Each entry has ``id``, ``name``, and ``bbox``.
        """
        return self._json("/api/regions")

    def region_ids(self, layer: str = "states") -> list[str]:
        """List valid region ids for ``"states"`` or ``"iso"``."""
        if layer not in ("states", "iso"):
            raise ValueError("layer must be 'states' or 'iso'")
        return [r["id"] for r in self.regions().get(layer, [])]

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        source: str,
        dates,
        type: str | None = None,
        *,
        region=None,
        iso=None,
        bbox: tuple | None = None,
        time_start=None,
        time_end=None,
        dest: str | Path = ".",
        show_progress: bool | None = None,
        local_crop: bool = True,
        keep_raw: bool = False,
    ) -> list[Path]:
        """Download data, optionally cropped to a region and/or time window.

        One file is written per date key, so results are ready to open directly
        rather than bundled into a ZIP.

        Cropping happens server-side, which keeps the transfer small (a Texas
        6-hour NOAA crop is ~240 KB instead of hundreds of MB).  When the server
        refuses a CONUS-scale HRRR archive request (HTTP 413), the SDK falls
        back to downloading the full file and cropping locally, unless
        *local_crop* is False.

        Args:
            source: ``"era5"``, ``"hrrr"``, ``"noaa"``, or a full API key.
            dates: One date key or a list of them — see :meth:`list`.
            type: Sub-type — see :meth:`types`.
            region: State postal code(s), e.g. ``"TX"`` or ``["TX", "OK"]``.
                Multiple states crop to their union bounding box.
            iso: ISO zone id(s) — see ``regions()["iso"]``.
            bbox: ``(lat_max, lon_min, lat_min, lon_max)``. Note the ordering:
                north, west, south, east.
            time_start: Start of the time window (ISO string or datetime).
                May be given without *time_end* to run to the end of the file.
            time_end: End of the time window, inclusive.
            dest: Destination directory (created if absent).
            show_progress: Show progress bars; defaults to the client setting.
            local_crop: Fall back to a local crop when the server returns 413.
            keep_raw: Keep the uncropped download after a local crop.

        Returns:
            Paths to the saved files, one per date key.

        Raises:
            ValueError: On an unknown source/type, an empty date list, or more
                than one of region/iso/bbox.
            RegionTooLargeError: Server refused the crop and *local_crop* is False.
            WeatherAPIError: Any other API failure.
        """
        api_key = registry.resolve(source, type)
        date_keys = [dates] if isinstance(dates, str) else list(dates)
        if not date_keys:
            raise ValueError("No dates given")
        show = self._show_progress if show_progress is None else show_progress

        layer, ids, box = self._resolve_region(region, iso, bbox)
        t_start = to_iso(time_start) if time_start is not None else None
        t_end = to_iso(time_end) if time_end is not None else None
        cropping = bool(layer or t_start or t_end)

        # A time crop still goes through the region endpoint, which requires a
        # spatial argument — a whole-globe box leaves the grid untouched.
        if cropping and not layer:
            layer, box = "custom", _WORLD_BBOX

        dest = Path(dest)
        out: list[Path] = []
        for key in date_keys:
            if not cropping:
                out.append(self._plain(api_key, key, dest, show))
                continue
            try:
                out.append(self._cropped(api_key, key, layer, ids, box,
                                         t_start, t_end, dest, show))
            except RegionTooLargeError:
                if not local_crop:
                    raise
                print(f"Server can't crop {api_key} {key} at this scale — "
                      f"downloading in full and cropping locally.")
                out.append(self._local(api_key, key, layer, ids, box, t_start,
                                       t_end, dest, show, keep_raw))
        return out

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_region(region, iso, bbox) -> tuple[str | None, list[str] | None, tuple | None]:
        """Normalise the three spatial arguments into (layer, ids, bbox)."""
        given = [x is not None for x in (region, iso, bbox)]
        if sum(given) > 1:
            raise ValueError("Provide at most one of region, iso, or bbox")
        if region is not None:
            ids = [region] if isinstance(region, str) else list(region)
            return "states", [str(i).strip().upper() for i in ids], None
        if iso is not None:
            ids = [iso] if isinstance(iso, str) else list(iso)
            return "iso", [str(i).strip() for i in ids], None
        if bbox is not None:
            box = tuple(float(x) for x in bbox)
            if len(box) != 4:
                raise ValueError("bbox must be (lat_max, lon_min, lat_min, lon_max)")
            if not (box[2] < box[0] and box[1] < box[3]):
                raise ValueError(
                    f"bbox {box} is inverted; expected "
                    f"(lat_max, lon_min, lat_min, lon_max) with lat_max > lat_min "
                    f"and lon_max > lon_min"
                )
            return "custom", None, box
        return None, None, None

    def _url(self, path: str, params: dict) -> str:
        clean = {k: v for k, v in params.items() if v is not None}
        return requests.Request("GET", self._base_url + path, params=clean).prepare().url

    def _json(self, path: str, **params) -> dict:
        resp = requests.get(self._base_url + path, params=params or None, timeout=120)
        if not resp.ok:
            detail, _ = server_detail(resp)
            raise WeatherAPIError(resp.status_code, detail)
        return resp.json()

    def _plain(self, api_key: str, key: str, dest: Path, show: bool) -> Path:
        """Download one uncropped file."""
        url = self._url("/api/download", {"source": api_key, "dates": key})
        return download_file(url, dest_dir=dest, show_progress=show)

    def _cropped(self, api_key, key, layer, ids, box, t_start, t_end, dest, show) -> Path:
        """Download one server-cropped file."""
        url = self._url("/api/download/region", {
            "source": api_key,
            "dates": key,
            "region_layer": layer,
            "region_ids": ",".join(ids) if ids else None,
            "bbox": ",".join(str(x) for x in box) if box else None,
            "time_start": t_start,
            "time_end": t_end,
        })
        return download_file(url, dest_dir=dest, show_progress=show)

    def _local(self, api_key, key, layer, ids, box, t_start, t_end, dest, show,
               keep_raw) -> Path:
        """Download one file in full and crop it on this machine."""
        if box is None:
            box = self._bbox_for_ids(layer, ids)

        if keep_raw:
            raw = self._plain(api_key, key, dest, show)
            cleanup = None
        else:
            tmp_dir = tempfile.mkdtemp(prefix="towx_raw_", dir=str(dest))
            raw = self._plain(api_key, key, Path(tmp_dir), show)
            cleanup = tmp_dir

        try:
            tag = "+".join(ids) if ids else "custom"
            out = dest / f"{api_key}_{key}_{tag}{self._time_tag(t_start, t_end)}.pww"
            return localcrop.crop_file(
                raw, out, box,
                to_epoch(t_start) if t_start else None,
                to_epoch(t_end) if t_end else None,
            )
        finally:
            if cleanup:
                import shutil
                shutil.rmtree(cleanup, ignore_errors=True)

    def _bbox_for_ids(self, layer: str, ids: list[str]) -> tuple:
        """Resolve region ids to their union bbox using the server's catalog.

        Only *layer* is searched — scanning both would silently widen the box if
        an id ever existed in each.
        """
        entries = {e["id"]: tuple(e["bbox"]) for e in self.regions().get(layer, [])}
        missing = [i for i in ids if i not in entries]
        if missing:
            raise ValueError(f"Unknown {layer} region ids: {missing}")
        found = [entries[i] for i in ids]
        return (
            max(b[0] for b in found), min(b[1] for b in found),
            min(b[2] for b in found), max(b[3] for b in found),
        )

    @staticmethod
    def _time_tag(t_start: str | None, t_end: str | None) -> str:
        """Match the server's filename time tag so local and remote agree.

        Minutes are included: without them two windows in the same hour collide
        on one filename and the second download silently overwrites the first —
        which is exactly the case that matters for 15-minute HRRR data.
        """
        if not (t_start or t_end):
            return ""
        import datetime as dt
        fmt = lambda s: dt.datetime.fromisoformat(s).strftime("%Y%m%dH%H%M") if s else ""
        s, e = fmt(t_start), fmt(t_end)
        return f"_T{s}to{e}" if s and e else f"_T{s or e}"

    # Kept for the back-compat source wrappers.
    def _download(self, path: str, dest_dir: str, filename: str,
                  show_progress: bool = True, **params) -> Path:
        url = self._url(path, params)
        return download_file(url, dest_path=Path(dest_dir) / filename,
                             show_progress=show_progress)
