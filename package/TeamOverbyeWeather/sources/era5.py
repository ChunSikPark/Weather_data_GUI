"""ERA5 reanalysis data client — thin wrapper over :meth:`WeatherClient.download`."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..utils import parse_quarter, quarter_to_source_key

if TYPE_CHECKING:
    from ..client import WeatherClient


class ERA5Client:
    """Access ERA5 quarterly reanalysis datasets via :attr:`WeatherClient.era5`."""

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    def list_quarters(self, region: str = "north_america") -> list[str]:
        """List available quarters like ``["2026-Q3", "2026-Q2"]``, newest first.

        Args:
            region: ``"north_america"`` or ``"texas"``.
        """
        return self._client.list(quarter_to_source_key(region))

    def download(
        self,
        quarters: list[str],
        region: str = "north_america",
        dest: str = ".",
        **kwargs,
    ) -> list[Path]:
        """Download ERA5 quarterly ``.pww`` files, one per quarter.

        Args:
            quarters: Quarter strings like ``["2026-Q1"]``.
            region: ``"north_america"`` or ``"texas"``.
            dest: Destination directory.
            **kwargs: Passed to :meth:`WeatherClient.download` (``time_start``,
                ``time_end``, ``show_progress``, ...).
        """
        for q in quarters:
            parse_quarter(q)
        return self._client.download(quarter_to_source_key(region), quarters,
                                     dest=dest, **kwargs)

    def download_region(
        self,
        quarters: list[str],
        *,
        region: str = "north_america",
        region_ids: list[str] | None = None,
        region_layer: str | None = None,
        bbox: tuple | None = None,
        dest: str = ".",
        **kwargs,
    ) -> list[Path]:
        """Download ERA5 quarters cropped to a region or bbox.

        Args:
            quarters: Quarter strings.
            region: Which ERA5 dataset — ``"north_america"`` or ``"texas"``.
            region_ids: State postal codes or ISO zone ids to crop to.
            region_layer: ``"states"`` or ``"iso"`` (required with *region_ids*).
            bbox: ``(lat_max, lon_min, lat_min, lon_max)``.
            dest: Destination directory.
            **kwargs: Passed to :meth:`WeatherClient.download`.
        """
        for q in quarters:
            parse_quarter(q)
        spatial = _spatial(region_ids, region_layer, bbox)
        return self._client.download(quarter_to_source_key(region), quarters,
                                     dest=dest, **spatial, **kwargs)


def _spatial(region_ids, region_layer, bbox) -> dict:
    """Translate the legacy region_ids/region_layer/bbox trio into download() kwargs."""
    if bbox is not None:
        if region_ids is not None:
            raise ValueError("Provide exactly one of region_ids or bbox, not both")
        return {"bbox": bbox}
    if region_ids is None:
        raise ValueError("Provide region_ids or bbox")
    if region_layer not in ("states", "iso"):
        raise ValueError("region_layer must be 'states' or 'iso' when region_ids is given")
    return {"region": region_ids} if region_layer == "states" else {"iso": region_ids}
