"""NOAA/GFS forecast data client."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import WeatherClient


class NOAAClient:
    """Provides access to NOAA/GFS forecast datasets (PWW files).

    Access via :attr:`WeatherClient.noaa`.
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    def list_forecast_cycles(self) -> list[str]:
        """List available NOAA/GFS forecast initialisation cycles.

        Returns:
            List of cycle strings sorted newest first.

        Raises:
            requests.HTTPError: If the catalog request fails.
        """
        catalog = self._client.catalog()
        source_data = catalog.get("noaa_forecast", {})
        if isinstance(source_data, list):
            cycles = source_data
        elif isinstance(source_data, dict):
            cycles = source_data.get("cycles", [])
        else:
            cycles = []
        return sorted(cycles, reverse=True)

    def download_forecast(
        self,
        cycles: list[str],
        dest: str = ".",
    ) -> list[Path]:
        """Download NOAA/GFS forecast PWW files.

        NOAA/GFS files in Drive are bare ``.pww``. For a single cycle the
        API streams the ``.pww`` directly; for multiple cycles the API
        streams a ZIP bundle containing the ``.pww`` files inside.

        Args:
            cycles: Cycle identifier strings.
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
            filename = f"NOAA_forecast_{safe}.pww"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="noaa_forecast",
                dates=c,
            )
            paths.append(path)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"TeamOverbye_noaa_{timestamp}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source="noaa_forecast",
                dates=",".join(cycles),
            )
            paths.append(path)

        return paths

    def download_region(
        self,
        cycles: "list[str]",
        *,
        region_ids: "list[str] | None" = None,
        region_layer: "str | None" = None,
        bbox: "tuple | None" = None,
        dest: str = ".",
    ) -> "list[Path]":
        """Download NOAA/GFS forecast PWW files cropped to a region or bbox."""
        from ..utils import validate_region_args
        validate_region_args(region_ids, region_layer, bbox)
        if not cycles:
            return []
        dates_param = ",".join(cycles)
        source = "noaa_forecast_recent"
        filename = "noaa_region_bundle.zip" if len(cycles) > 1 else f"noaa_{cycles[0]}_region.pww"
        if bbox is not None:
            bbox_str = ",".join(str(x) for x in bbox)
            return [self._client._download("/api/download/region", dest_dir=dest,
                                           filename=filename, source=source,
                                           dates=dates_param, bbox=bbox_str)]
        else:
            return [self._client._download("/api/download/region", dest_dir=dest,
                                           filename=filename, source=source,
                                           dates=dates_param,
                                           region_layer=region_layer,
                                           region_ids=",".join(region_ids))]

    def download_latest(self, dest: str = ".") -> Path:
        """Download the most recent NOAA/GFS forecast cycle.

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
            raise ValueError("No NOAA/GFS forecast cycles are currently available.")
        latest = cycles[0]
        paths = self.download_forecast([latest], dest=dest)
        return paths[0]
