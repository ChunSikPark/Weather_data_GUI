"""HRRR forecast and history client — thin wrapper over :meth:`WeatherClient.download`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .era5 import _spatial

if TYPE_CHECKING:
    from ..client import WeatherClient


class HRRRClient:
    """Access HRRR historical and forecast datasets via :attr:`WeatherClient.hrrr`.

    HRRR history comes in four flavours; pass *type* to pick one:

    ==================  ==============  ==================================
    type                date keys       contents
    ==================  ==============  ==================================
    ``current``         ``YYYY-MM-DD``  this year, 15-minute steps
    ``archive``         ``YYYY-MM``     past years, 15-minute steps
    ``hourly_current``  ``YYYY-MM-DD``  this year, hourly steps
    ``hourly_archive``  ``YYYY-MM``     past years, hourly steps
    ==================  ==============  ==================================
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_months(self, type: str = "archive") -> list[str]:
        """List available ``YYYY-MM`` archive months, newest first.

        Args:
            type: ``"archive"`` (15-min) or ``"hourly_archive"``.
        """
        return self._client.list("hrrr", type)

    def list_days(self, type: str = "current") -> list[str]:
        """List available ``YYYY-MM-DD`` days, newest first.

        Args:
            type: ``"current"`` (15-min) or ``"hourly_current"``.
        """
        return self._client.list("hrrr", type)

    def list_forecast_cycles(self) -> list[str]:
        """List available forecast cycles like ``["2026-07-22T12Z"]``, newest first."""
        return self._client.list("hrrr", "forecast")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_history(
        self,
        months: list[str] | None = None,
        dest: str = ".",
        *,
        days: list[str] | None = None,
        type: str | None = None,
        **kwargs,
    ) -> list[Path]:
        """Download HRRR history files, one per date key.

        Args:
            months: ``YYYY-MM`` keys (archive).
            dest: Destination directory.
            days: ``YYYY-MM-DD`` keys (current year) — use instead of *months*.
            type: Explicit sub-type; inferred from months/days when omitted.
            **kwargs: Passed to :meth:`WeatherClient.download`.

        Raises:
            ValueError: If both or neither of *months* and *days* are given.
        """
        dates, inferred = _history_dates(months, days)
        return self._client.download("hrrr", dates, type or inferred,
                                     dest=dest, **kwargs)

    def download_forecast(self, cycles: list[str], dest: str = ".", **kwargs) -> list[Path]:
        """Download HRRR forecast files, one ZIP per cycle."""
        return self._client.download("hrrr", cycles, "forecast", dest=dest, **kwargs)

    def download_region(
        self,
        *,
        months: list[str] | None = None,
        days: list[str] | None = None,
        cycles: list[str] | None = None,
        type: str | None = None,
        region_ids: list[str] | None = None,
        region_layer: str | None = None,
        bbox: tuple | None = None,
        dest: str = ".",
        **kwargs,
    ) -> list[Path]:
        """Download HRRR data cropped to a region or bbox.

        CONUS-scale archive requests are cropped locally, since the server
        refuses them to protect its memory budget.

        Args:
            months: ``YYYY-MM`` archive keys.
            days: ``YYYY-MM-DD`` current-year keys.
            cycles: Forecast cycle keys.
            type: Explicit sub-type; inferred from the date argument when omitted.
            region_ids: State postal codes or ISO zone ids.
            region_layer: ``"states"`` or ``"iso"``.
            bbox: ``(lat_max, lon_min, lat_min, lon_max)``.
            dest: Destination directory.
            **kwargs: Passed to :meth:`WeatherClient.download` (``time_start``, ...).

        Raises:
            ValueError: If not exactly one of months/days/cycles is given.
        """
        spatial = _spatial(region_ids, region_layer, bbox)
        if cycles is not None:
            if months is not None or days is not None:
                raise ValueError("Provide exactly one of months, days, or cycles")
            return self._client.download("hrrr", cycles, type or "forecast",
                                         dest=dest, **spatial, **kwargs)
        dates, inferred = _history_dates(months, days)
        return self._client.download("hrrr", dates, type or inferred,
                                     dest=dest, **spatial, **kwargs)

    def download_latest_forecast(self, dest: str = ".", **kwargs) -> Path:
        """Download the most recent HRRR forecast cycle.

        Raises:
            ValueError: If no forecast cycles are available.
        """
        cycles = self.list_forecast_cycles()
        if not cycles:
            raise ValueError("No HRRR forecast cycles are currently available.")
        return self.download_forecast([cycles[0]], dest=dest, **kwargs)[0]


def _history_dates(months, days) -> tuple[list[str], str]:
    """Pick the date list and infer the matching history sub-type."""
    if (months is None) == (days is None):
        raise ValueError("Provide exactly one of months (YYYY-MM) or days (YYYY-MM-DD)")
    return (list(months), "archive") if months is not None else (list(days), "current")
