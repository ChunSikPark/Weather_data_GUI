"""Single source of truth mapping (source, type) -> API source key.

Mirrors ``_SOURCE_LOOKUP`` / ``_FILENAME_PATTERNS`` in ``backend/download.py``
and ``getApiSourceKey()`` in ``frontend/main.js``.  Keep all three in sync.
"""

from __future__ import annotations

# api_key -> (list_key, filename_pattern)
_API_KEYS: dict[str, tuple[str, str]] = {
    "era5_na":                     ("quarters", "ERA5_NorthAmerica_{key}.pww"),
    "era5_tx":                     ("quarters", "ERA5_Texas_{key}.pww"),
    "hrrr_forecast":               ("cycles",   "{key}_sfc_48_CONUS.zip"),
    "hrrr_history":                ("months",   "{key}_subh_15min_CONUS.zip"),
    "hrrr_history_current":        ("days",     "{key}_subh_15min_CONUS.zip"),
    "hrrr_history_archive":        ("months",   "{key}_subh_15min_CONUS.zip"),
    "hrrr_history_hourly_current": ("days",     "{key}_hourly_CONUS.pww"),
    "hrrr_history_hourly_archive": ("months",   "{key}_hourly_CONUS.zip"),
    "noaa_forecast":               ("cycles",   "Forecast_NorthAmerica_Run{key}.pww"),
    "noaa_forecast_recent":        ("cycles",   "Forecast_NorthAmerica_Run{key}.pww"),
    "noaa_forecast_archive":       ("cycles",   "Forecast_NorthAmerica_Run{key}.pww"),
    # The event key already carries date, title and zone.
    "extreme_events":              ("keys",     "{key}.pww"),
}

# (source, type) -> api_key.  ``None`` is the default type for that source.
_TYPES: dict[str, dict[str | None, str]] = {
    "era5": {
        None:             "era5_na",
        "historical":     "era5_na",
        "north_america":  "era5_na",
        "na":             "era5_na",
        "texas":          "era5_tx",
        "tx":             "era5_tx",
    },
    "hrrr": {
        None:             "hrrr_forecast",
        "forecast":       "hrrr_forecast",
        "current":        "hrrr_history_current",
        "archive":        "hrrr_history_archive",
        "hourly_current": "hrrr_history_hourly_current",
        "hourly_archive": "hrrr_history_hourly_archive",
        "history":        "hrrr_history",
    },
    "noaa": {
        None:             "noaa_forecast_recent",
        "recent":         "noaa_forecast_recent",
        "forecast":       "noaa_forecast_recent",
        "archive":        "noaa_forecast_archive",
    },
    "extreme": {
        None:             "extreme_events",
        "events":         "extreme_events",
    },
}

# API keys the server refuses to crop at CONUS scale (see backend/main.py).
LOCAL_CROP_SOURCES = frozenset({
    "hrrr_history",
    "hrrr_history_archive",
    "hrrr_history_hourly_archive",
})


def resolve(source: str, type: str | None = None) -> str:
    """Resolve a (source, type) pair to the API source key.

    A full API key (e.g. ``"hrrr_history_hourly_archive"``) is accepted
    directly and returned unchanged.
    """
    key = str(source).strip().lower()
    if key in _API_KEYS:
        return key

    types = _TYPES.get(key)
    if types is None:
        raise ValueError(
            f"Unknown source {source!r}. Valid: {sorted(_TYPES)} "
            f"(or a full API key: {sorted(_API_KEYS)})."
        )

    t = type.strip().lower() if isinstance(type, str) else type
    if t not in types:
        valid = sorted(x for x in types if x is not None)
        raise ValueError(f"Unknown type {type!r} for source {source!r}. Valid: {valid}.")
    return types[t]


def list_key(api_key: str) -> str:
    """Return the catalog list key (``quarters``/``months``/``days``/``cycles``)."""
    return _API_KEYS[api_key][0]


def filename_for(api_key: str, date_key: str) -> str:
    """Fallback filename when the server sends no Content-Disposition."""
    return _API_KEYS[api_key][1].format(key=date_key)


def types_for(source: str) -> list[str]:
    """List the canonical type names for a source."""
    types = _TYPES.get(str(source).strip().lower())
    if types is None:
        raise ValueError(f"Unknown source {source!r}. Valid: {sorted(_TYPES)}.")
    return sorted(t for t in types if t is not None)


def all_sources() -> list[str]:
    return sorted(_TYPES)
