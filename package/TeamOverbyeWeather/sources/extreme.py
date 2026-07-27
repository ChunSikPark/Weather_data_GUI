"""Curated historical extreme-temperature events."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .era5 import _spatial

if TYPE_CHECKING:
    from ..client import WeatherClient


class ExtremeClient:
    """Access curated extreme-weather events via :attr:`WeatherClient.extreme`.

    62 historical events spanning 1899-2023, selected per ISO zone as the three
    hottest and three coldest on record, plus additional notable scenarios such
    as ERCOT's February 2011 rolling outages. Each event has weather data and a
    matching animation.

    Events are identified by a key that carries the date, title and zone::

        2021-02-14_Winter_Storm_Uri_Texas
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _section(self) -> dict:
        return self._client.catalog().get("extreme_events") or {}

    def zones(self) -> list[str]:
        """List the ISO zones that have events, e.g. ``["CAISO", ..., "Texas"]``."""
        return list(self._section().get("zones", []))

    def events(self, zone: str | None = None) -> list[dict]:
        """List events, newest first.

        Args:
            zone: Restrict to one ISO zone; omit for every zone.

        Returns:
            Dicts with ``key``, ``date``, ``title``, ``zone`` and ``has_video``.

        Raises:
            ValueError: If *zone* is not a known zone.
        """
        by_zone = self._section().get("events", {})
        if zone is not None:
            if zone not in by_zone:
                raise ValueError(f"Unknown zone {zone!r}. Valid: {self.zones()}")
            found = list(by_zone[zone])
        else:
            found = [e for evs in by_zone.values() for e in evs]
        return sorted(found, key=lambda e: e["date"], reverse=True)

    def find(self, text: str) -> list[dict]:
        """Search events by title, case-insensitively.

        ``client.extreme.find("uri")`` finds Winter Storm Uri.
        """
        needle = text.strip().lower()
        return [e for e in self.events() if needle in e["title"].lower()]

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        keys,
        *,
        region_ids: list[str] | None = None,
        region_layer: str | None = None,
        bbox: tuple | None = None,
        dest: str = ".",
        **kwargs,
    ) -> list[Path]:
        """Download event weather data as ``.pww``, one file per event.

        Args:
            keys: One event key or a list of them.
            region_ids: State postal codes or ISO zone ids to crop to.
            region_layer: ``"states"`` or ``"iso"`` (required with *region_ids*).
            bbox: ``(lat_max, lon_min, lat_min, lon_max)``.
            dest: Destination directory.
            **kwargs: Passed to :meth:`WeatherClient.download` (``time_start``, ...).
        """
        spatial = {}
        if region_ids is not None or bbox is not None:
            spatial = _spatial(region_ids, region_layer, bbox)
        return self._client.download("extreme", keys, dest=dest, **spatial, **kwargs)

    def video(self, key: str, dest: str = ".", show_progress: bool | None = None) -> Path:
        """Download an event's animation as ``.mp4``.

        Raises:
            WeatherAPIError: If the event has no animation.
        """
        from ..utils import download_file
        show = self._client._show_progress if show_progress is None else show_progress
        url = self._client._url("/api/extreme/video", {"key": key})
        return download_file(url, dest_path=Path(dest) / f"{key}.mp4", show_progress=show)

    def coverage(self, zone: str, dest: str = ".", show_progress: bool | None = None) -> Path:
        """Download a zone's coverage map as ``.png``."""
        from ..utils import download_file
        show = self._client._show_progress if show_progress is None else show_progress
        url = self._client._url("/api/extreme/coverage", {"zone": zone})
        return download_file(url, dest_path=Path(dest) / f"coverage_{zone}.png",
                             show_progress=show)
