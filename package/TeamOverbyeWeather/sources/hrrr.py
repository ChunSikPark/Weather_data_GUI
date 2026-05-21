"""HRRR forecast and history data client."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import WeatherClient


class HRRRClient:
    """Provides access to HRRR historical and forecast datasets.

    Access via :attr:`WeatherClient.hrrr`.
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Listing helpers
    # ------------------------------------------------------------------

    def list_months(self) -> list[str]:
        """List available HRRR historical months.

        Returns:
            List of month strings like ``["2025-01", "2024-12"]``,
            sorted newest first.

        Raises:
            requests.HTTPError: If the catalog request fails.
        """
        catalog = self._client.catalog()
        source_data = catalog.get("hrrr_history", {})
        if isinstance(source_data, list):
            months = source_data
        elif isinstance(source_data, dict):
            months = source_data.get("months", [])
        else:
            months = []
        return sorted(months, reverse=True)

    def list_forecast_cycles(self) -> list[str]:
        """List available HRRR forecast initialisation cycles.

        Returns:
            List of cycle strings like ``["2026-04-21T06Z", "2026-04-21T00Z"]``,
            sorted newest first.

        Raises:
            requests.HTTPError: If the catalog request fails.
        """
        catalog = self._client.catalog()
        source_data = catalog.get("hrrr_forecast", {})
        if isinstance(source_data, list):
            cycles = source_data
        elif isinstance(source_data, dict):
            cycles = source_data.get("cycles", [])
        else:
            cycles = []
        return sorted(cycles, reverse=True)

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    def download_history(
        self,
        months: list[str],
        dest: str = ".",
    ) -> list[Path]:
        """Download HRRR historical monthly ZIP files.

        Args:
            months: Month strings like ``["2025-01", "2024-12"]``.
            dest: Destination directory (created if absent).

        Returns:
            List of :class:`pathlib.Path` objects for the saved files.

        Raises:
            requests.HTTPError: If any download request fails.
        """
        if not months:
            return []

        paths: list[Path] = []

        if len(months) == 1:
            m = months[0]
            filename = f"HRRR_history_{m}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="hrrr_history",
                dates=m,
            )
            paths.append(path)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"TeamOverbye_hrrr_history_{timestamp}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="hrrr_history",
                dates=",".join(months),
            )
            paths.append(path)

        return paths

    def download_forecast(
        self,
        cycles: list[str],
        dest: str = ".",
    ) -> list[Path]:
        """Download HRRR forecast files (one ZIP per cycle).

        Args:
            cycles: Cycle strings like ``["2026-04-21T06Z"]``.
            dest: Destination directory (created if absent).

        Returns:
            List of :class:`pathlib.Path` objects for the saved files.

        Raises:
            requests.HTTPError: If any download request fails.
        """
        if not cycles:
            return []

        paths: list[Path] = []

        if len(cycles) == 1:
            c = cycles[0]
            safe = c.replace(":", "").replace(" ", "_")
            filename = f"HRRR_forecast_{safe}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="hrrr_forecast",
                dates=c,
            )
            paths.append(path)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"TeamOverbye_hrrr_forecast_{timestamp}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="hrrr_forecast",
                dates=",".join(cycles),
            )
            paths.append(path)

        return paths

    def download_region(
        self,
        *,
        months: "list[str] | None" = None,
        cycles: "list[str] | None" = None,
        region_ids: "list[str] | None" = None,
        region_layer: "str | None" = None,
        bbox: "tuple | None" = None,
        dest: str = ".",
    ) -> "list[Path]":
        """Download HRRR data cropped to a region (states/iso) or bbox.

        Exactly one of months/cycles must be provided; exactly one of region_ids/bbox.
        Large HRRR-archive + bbox requests are cropped locally (SDK-side) to avoid 413.
        """
        from ..utils import validate_region_args
        validate_region_args(region_ids, region_layer, bbox)
        if months is not None and cycles is not None:
            raise ValueError("Provide exactly one of months or cycles, not both")
        if months is None and cycles is None:
            raise ValueError("Provide months (history) or cycles (forecast)")

        is_history = months is not None
        source = "hrrr_history" if is_history else "hrrr_forecast"
        date_list = months if is_history else cycles

        if not date_list:
            return []

        # Large bbox + HRRR history: SDK local crop
        if is_history and bbox is not None:
            lat_max, lon_min, lat_min, lon_max = bbox
            area = (lat_max - lat_min) * (lon_max - lon_min)
            if area >= 2380:
                return self._local_crop(months, bbox, dest)

        dates_param = ",".join(date_list)
        if bbox is not None:
            bbox_str = ",".join(str(x) for x in bbox)
            filename = f"{source}_region_bundle.zip" if len(date_list) > 1 else f"{source}_{date_list[0]}_region.pww"
            return [self._client._download("/api/download/region", dest_dir=dest,
                                           filename=filename, source=source,
                                           dates=dates_param, bbox=bbox_str)]
        else:
            ids_str = ",".join(region_ids)
            filename = f"{source}_region_bundle.zip" if len(date_list) > 1 else f"{source}_{date_list[0]}_region.pww"
            return [self._client._download("/api/download/region", dest_dir=dest,
                                           filename=filename, source=source,
                                           dates=dates_param,
                                           region_layer=region_layer,
                                           region_ids=ids_str)]

    def _local_crop(self, months: "list[str]", bbox: tuple, dest: str) -> "list[Path]":
        """Fallback: download full HRRR monthly archives and crop locally."""
        import io as _io
        import zipfile
        from .. import pww_io
        out = []
        for m in months:
            paths = self.download_history([m], dest=dest)
            for p in paths:
                raw = p.read_bytes()
                if p.suffix.lower() == ".zip":
                    with zipfile.ZipFile(_io.BytesIO(raw)) as zf:
                        pww_names = [n for n in zf.namelist() if n.lower().endswith(".pww")]
                        if not pww_names:
                            continue
                        raw = zf.read(pww_names[0])
                h, s, a = pww_io.read_pww(raw)
                h, s, a = pww_io.crop_to_bbox(h, s, a, bbox)
                cropped_path = p.with_name(p.stem + "_region.pww")
                cropped_path.write_bytes(pww_io.write_pww(h, s, a))
                out.append(cropped_path)
        return out

    def download_latest_forecast(self, dest: str = ".") -> Path:
        """Download the most recent HRRR forecast cycle.

        Args:
            dest: Destination directory (created if absent).

        Returns:
            :class:`pathlib.Path` to the saved file.

        Raises:
            ValueError: If no forecast cycles are available.
            requests.HTTPError: If the download request fails.
        """
        cycles = self.list_forecast_cycles()
        if not cycles:
            raise ValueError("No HRRR forecast cycles are currently available.")
        latest = cycles[0]
        paths = self.download_forecast([latest], dest=dest)
        return paths[0]
