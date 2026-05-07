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
