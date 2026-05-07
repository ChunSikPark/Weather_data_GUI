"""ERA5 reanalysis data client."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils import parse_quarter, quarter_to_source_key

if TYPE_CHECKING:
    from ..client import WeatherClient


class ERA5Client:
    """Provides access to ERA5 quarterly reanalysis datasets.

    Access via :attr:`WeatherClient.era5`.
    """

    def __init__(self, client: "WeatherClient") -> None:
        self._client = client

    def list_quarters(self, region: str = "north_america") -> list[str]:
        """List available ERA5 quarters for a region.

        Args:
            region: ``"north_america"`` or ``"texas"``.

        Returns:
            List of quarter strings like ``["2025-Q1", "2024-Q4"]``,
            sorted newest first.

        Raises:
            ValueError: If *region* is not recognised.
            requests.HTTPError: If the catalog request fails.
        """
        source_key = quarter_to_source_key(region)
        catalog = self._client.catalog()
        source_data = catalog.get(source_key, {})
        # Catalog is expected to contain a list of available quarter strings
        # under the source key, or a dict with an "available" list.
        if isinstance(source_data, list):
            quarters = source_data
        elif isinstance(source_data, dict):
            quarters = source_data.get("quarters", [])
        else:
            quarters = []
        return sorted(quarters, reverse=True)

    def download(
        self,
        quarters: list[str],
        region: str = "north_america",
        dest: str = ".",
    ) -> list[Path]:
        """Download ERA5 quarterly ZIP files.

        For a single quarter the API redirects to the actual file; for
        multiple quarters the API returns a combined ZIP stream.  Both cases
        are handled transparently.

        Args:
            quarters: Quarter strings like ``["2025-Q1", "2024-Q4"]``.
            region: ``"north_america"`` or ``"texas"``.
            dest: Destination directory (created if absent).

        Returns:
            List of :class:`pathlib.Path` objects for the saved files.

        Raises:
            ValueError: If *region* is invalid or any quarter string is
                malformed.
            requests.HTTPError: If any download request fails.
        """
        if not quarters:
            return []

        source_key = quarter_to_source_key(region)

        # Validate all quarter strings up-front.
        for q in quarters:
            parse_quarter(q)

        paths: list[Path] = []

        if len(quarters) == 1:
            q = quarters[0]
            filename = f"ERA5_{source_key}_{q}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source=source_key,
                dates=q,
            )
            paths.append(path)
        else:
            timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            filename = f"TeamOverbye_{source_key}_{timestamp}.zip"
            path = self._client._download(
                "/api/download",
                dest_dir=dest,
                filename=filename,
                source=source_key,
                dates=",".join(quarters),
            )
            paths.append(path)

        return paths
