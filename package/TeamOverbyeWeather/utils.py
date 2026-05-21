"""Utility helpers for TeamOverbyeWeather."""

from __future__ import annotations

import re
from pathlib import Path

import requests
from tqdm import tqdm


def download_file(url: str, dest_path: Path, show_progress: bool = True) -> Path:
    """Downloads a file from URL to dest_path with optional tqdm progress bar.

    Args:
        url: The URL to download from.
        dest_path: Full path (including filename) where the file will be saved.
        show_progress: Whether to display a tqdm progress bar.

    Returns:
        The path to the downloaded file.

    Raises:
        requests.HTTPError: If the server returns an error status.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, allow_redirects=True, stream=True, timeout=300) as resp:
        resp.raise_for_status()

        total = int(resp.headers.get("content-length", 0)) or None
        chunk_size = 8192

        with open(dest_path, "wb") as fh:
            if show_progress:
                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=dest_path.name,
                ) as bar:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            fh.write(chunk)
                            bar.update(len(chunk))
            else:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        fh.write(chunk)

    return dest_path


def parse_quarter(q: str) -> tuple[int, int]:
    """Parses a quarter string into (year, quarter_number).

    Args:
        q: Quarter string in format "YYYY-QN", e.g. "2025-Q1".

    Returns:
        Tuple of (year, quarter) as integers, e.g. (2025, 1).

    Raises:
        ValueError: If the string does not match the expected format.
    """
    match = re.fullmatch(r"(\d{4})-Q([1-4])", q.strip())
    if not match:
        raise ValueError(
            f"Invalid quarter format {q!r}. Expected format: 'YYYY-QN' (e.g. '2025-Q1')."
        )
    return int(match.group(1)), int(match.group(2))


def quarter_to_source_key(region: str) -> str:
    """Maps a region name to its ERA5 catalog source key.

    Args:
        region: "north_america" or "texas".

    Returns:
        Source key string: "era5_na" or "era5_tx".

    Raises:
        ValueError: If region is not recognized.
    """
    mapping = {
        "north_america": "era5_na",
        "texas": "era5_tx",
    }
    if region not in mapping:
        raise ValueError(
            f"Unknown region {region!r}. Valid options: {list(mapping.keys())}."
        )
    return mapping[region]


def validate_region_args(region_ids, region_layer, bbox):
    """Validate that exactly one of (region_ids, bbox) is provided and layer is valid."""
    have_ids = region_ids is not None
    have_bbox = bbox is not None
    if have_ids and have_bbox:
        raise ValueError("Provide exactly one of region_ids or bbox, not both")
    if not have_ids and not have_bbox:
        raise ValueError("Provide region_ids or bbox")
    if have_ids and region_layer not in ("states", "iso"):
        raise ValueError("region_layer must be 'states' or 'iso' when region_ids is given")
