"""Pipeline health status reader.

Reads the alert_state.json file produced by the upstream weather-auto pipelines
and converts it into a simple per-source status mapping consumed by the frontend.
"""
from __future__ import annotations

import json
import os
import sys

# Mapping from alert_state.json keys to public source identifiers.
_SOURCE_MAP: dict[str, str] = {
    "weather-auto-noaa": "noaa",
    "weather-auto-hrrr-forecast": "hrrr_forecast",
    "weather-auto-hrrr-history": "hrrr_history",
    "weather-auto-cds": "era5",
}

_DEFAULT_PATH = "config/alert_state.json"


def _alert_state_path() -> str:
    return os.environ.get("ALERT_STATE_PATH", _DEFAULT_PATH)


def _unknown_status() -> dict[str, str]:
    return {public: "unknown" for public in _SOURCE_MAP.values()}


def get_pipeline_status() -> dict[str, str]:
    """Return per-source pipeline status.

    Each value is one of "ok", "error", or "unknown". If the alert state file
    is missing or unreadable, every source is reported as "unknown".
    """
    path = _alert_state_path()
    statuses = _unknown_status()

    if not os.path.exists(path):
        return statuses

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[status] Failed to read alert state at {path}: {exc}", file=sys.stderr)
        return statuses

    if not isinstance(data, dict):
        print(f"[status] Unexpected alert state structure at {path}", file=sys.stderr)
        return statuses

    for raw_key, public_key in _SOURCE_MAP.items():
        entry = data.get(raw_key)
        if not isinstance(entry, dict):
            statuses[public_key] = "unknown"
            continue
        alert_active = entry.get("alert_active")
        if alert_active is True:
            statuses[public_key] = "error"
        elif alert_active is False:
            statuses[public_key] = "ok"
        else:
            statuses[public_key] = "unknown"

    return statuses
