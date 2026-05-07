"""WeatherClient — top-level entry point for the Team Overbye Weather Data API."""

from __future__ import annotations

from pathlib import Path

import requests

from .sources.era5 import ERA5Client
from .sources.hrrr import HRRRClient
from .sources.noaa import NOAAClient
from .utils import download_file


class WeatherClient:
    """Client for the Team Overbye Weather Data API.

    Args:
        base_url: Base URL of the weather data API.
    """

    def __init__(self, base_url: str = "https://api.teamoverbye.tamu.edu") -> None:
        self._base_url = base_url.rstrip("/")
        self.era5 = ERA5Client(self)
        self.hrrr = HRRRClient(self)
        self.noaa = NOAAClient(self)

    # ------------------------------------------------------------------
    # Public high-level methods
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Returns pipeline health status for all data sources.

        Returns:
            Dict with keys ``noaa``, ``hrrr_forecast``, ``hrrr_history``,
            ``era5``.  Each value is one of ``"ok"``, ``"error"``, or
            ``"unknown"``.

        Raises:
            requests.HTTPError: If the API returns a non-2xx response.
        """
        resp = self._get("/api/status")
        resp.raise_for_status()
        return resp.json()

    def catalog(self) -> dict:
        """Returns the full data catalog describing available files.

        Returns:
            Catalog dictionary keyed by source (e.g. ``"era5_na"``,
            ``"hrrr_history"``, ``"noaa_forecast"``).

        Raises:
            requests.HTTPError: If the API returns a non-2xx response.
        """
        resp = self._get("/api/catalog")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, **params) -> requests.Response:
        """Send a GET request to the API.

        Args:
            path: URL path (must start with ``/``).
            **params: Query-string parameters.

        Returns:
            The :class:`requests.Response` object (not yet raise-checked).
        """
        url = self._base_url + path
        return requests.get(url, params=params or None, timeout=60)

    def _download(
        self,
        path: str,
        dest_dir: str,
        filename: str,
        show_progress: bool = True,
        **params,
    ) -> Path:
        """Downloads a file from the API to *dest_dir/filename*.

        The request follows redirects and streams the response body so that
        large ZIP files do not require loading everything into memory.

        Args:
            path: API path (e.g. ``"/api/download"``).
            dest_dir: Destination directory (created if absent).
            filename: Name of the file to write inside *dest_dir*.
            show_progress: Show tqdm progress bar.
            **params: Additional query-string parameters forwarded to the API.

        Returns:
            :class:`pathlib.Path` to the saved file.

        Raises:
            requests.HTTPError: If the API returns a non-2xx response.
        """
        url = self._base_url + path
        if params:
            req = requests.Request("GET", url, params=params).prepare()
            effective_url = req.url
        else:
            effective_url = url

        dest_path = Path(dest_dir) / filename
        return download_file(effective_url, dest_path, show_progress=show_progress)
