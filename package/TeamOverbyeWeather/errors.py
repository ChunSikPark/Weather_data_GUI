"""Exception types raised by the TeamOverbyeWeather client."""

from __future__ import annotations


class WeatherAPIError(RuntimeError):
    """The API returned an error.

    Attributes:
        status: HTTP status code.
        detail: Server-supplied message, or the raw body if it was not JSON.
    """

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"[HTTP {status}] {detail}")
        self.status = status
        self.detail = detail


class RegionTooLargeError(WeatherAPIError):
    """The server refused to crop a CONUS-scale request (HTTP 413).

    The SDK normally handles this by falling back to a local crop; this is only
    raised when ``local_crop=False`` was requested explicitly.
    """

    def __init__(self, detail: str, hint: str = "") -> None:
        super().__init__(413, detail if not hint else f"{detail} {hint}")
        self.hint = hint


class ServerBusyError(WeatherAPIError):
    """The download queue was full and stayed full across every retry (HTTP 503)."""

    def __init__(self, detail: str) -> None:
        super().__init__(503, detail)
