"""NOAA/GFS forecast client — thin wrapper over :meth:`WeatherClient.download`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .era5 import _spatial

if TYPE_CHECKING:
    from ..client import WeatherClient


class NOAAClient:
    """Access NOAA/GFS forecast datasets via :attr:`WeatherClient.noaa`.

    ``recent`` and ``archive`` are separate Drive folders, not a date split —
    a cycle in one will not appear in the other.
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    def list_forecast_cycles(self, type: str = "recent") -> list[str]:
        """List available cycles, newest first.

        Args:
            type: ``"recent"`` or ``"archive"``.
        """
        return self._client.list("noaa", type)

    def download_forecast(
        self,
        cycles: list[str],
        dest: str = ".",
        *,
        type: str = "recent",
        **kwargs,
    ) -> list[Path]:
        """Download NOAA/GFS forecast ``.pww`` files, one per cycle.

        Args:
            cycles: Cycle keys like ``["2026-07-22T12Z"]``.
            dest: Destination directory.
            type: ``"recent"`` or ``"archive"``.
            **kwargs: Passed to :meth:`WeatherClient.download`.
        """
        return self._client.download("noaa", cycles, type, dest=dest, **kwargs)

    def download_region(
        self,
        cycles: list[str],
        *,
        type: str = "recent",
        region_ids: list[str] | None = None,
        region_layer: str | None = None,
        bbox: tuple | None = None,
        dest: str = ".",
        **kwargs,
    ) -> list[Path]:
        """Download NOAA/GFS cycles cropped to a region or bbox.

        Args:
            cycles: Cycle keys.
            type: ``"recent"`` or ``"archive"``.
            region_ids: State postal codes or ISO zone ids.
            region_layer: ``"states"`` or ``"iso"``.
            bbox: ``(lat_max, lon_min, lat_min, lon_max)``.
            dest: Destination directory.
            **kwargs: Passed to :meth:`WeatherClient.download` (``time_start``, ...).
        """
        spatial = _spatial(region_ids, region_layer, bbox)
        return self._client.download("noaa", cycles, type, dest=dest, **spatial, **kwargs)

    def download_latest(self, dest: str = ".", **kwargs) -> Path:
        """Download the most recent NOAA/GFS forecast cycle.

        Raises:
            ValueError: If no forecast cycles are available.
        """
        cycles = self.list_forecast_cycles()
        if not cycles:
            raise ValueError("No NOAA/GFS forecast cycles are currently available.")
        return self.download_forecast([cycles[0]], dest=dest, **kwargs)[0]
