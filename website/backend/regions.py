"""Region catalog: US states and ISO zones — all bboxes hardcoded, no shapefile loading."""
from __future__ import annotations

# (lat_max, lon_min, lat_min, lon_max) — same as PWW crop convention (N, W, S, E)
_STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "AL": (35.0, -88.5, 30.1, -84.9),
    "AK": (71.4, -180.0, 51.2, -129.9),  # clipped at antimeridian — Aleutian tail excluded
    "AZ": (37.0, -114.8, 31.3, -109.0),
    "AR": (36.5, -94.6, 33.0, -89.6),
    "CA": (42.0, -124.5, 32.5, -114.1),
    "CO": (41.0, -109.1, 36.9, -102.0),
    "CT": (42.1, -73.7, 40.9, -71.8),
    "DE": (39.8, -75.8, 38.4, -75.0),
    "DC": (38.99, -77.12, 38.79, -76.91),
    "FL": (31.0, -87.6, 24.4, -79.9),
    "GA": (35.0, -85.6, 30.3, -80.8),
    "HI": (22.2, -160.3, 18.9, -154.8),
    "ID": (49.0, -117.2, 41.9, -111.0),
    "IL": (42.5, -91.5, 36.9, -87.0),
    "IN": (41.8, -88.1, 37.7, -84.8),
    "IA": (43.5, -96.6, 40.4, -90.1),
    "KS": (40.0, -102.1, 36.9, -94.6),
    "KY": (39.1, -89.6, 36.5, -81.9),
    "LA": (33.0, -94.0, 28.9, -88.8),
    "ME": (47.5, -71.1, 43.0, -66.9),
    "MD": (39.7, -79.5, 37.9, -75.0),
    "MA": (42.9, -73.5, 41.2, -69.9),
    "MI": (48.3, -90.4, 41.7, -82.4),
    "MN": (49.4, -97.2, 43.5, -89.5),
    "MS": (35.0, -91.7, 30.2, -88.1),
    "MO": (40.6, -95.8, 35.9, -89.1),
    "MT": (49.0, -116.1, 44.4, -104.0),
    "NE": (43.0, -104.1, 40.0, -95.3),
    "NV": (42.0, -120.0, 35.0, -114.0),
    "NH": (45.3, -72.6, 42.7, -70.6),
    "NJ": (41.4, -75.6, 38.9, -73.9),
    "NM": (37.0, -109.1, 31.3, -103.0),
    "NY": (45.0, -79.8, 40.5, -71.8),
    "NC": (36.6, -84.3, 33.8, -75.5),
    "ND": (49.0, -104.1, 45.9, -96.6),
    "OH": (42.3, -84.8, 38.4, -80.5),
    "OK": (37.0, -103.0, 33.6, -94.4),
    "OR": (46.2, -124.6, 42.0, -116.5),
    "PA": (42.3, -80.5, 39.7, -74.7),
    "RI": (42.0, -71.9, 41.1, -71.1),
    "SC": (35.2, -83.4, 32.0, -78.5),
    "SD": (45.9, -104.1, 42.5, -96.4),
    "TN": (36.7, -90.3, 34.9, -81.6),
    "TX": (36.5, -106.6, 25.8, -93.5),
    "UT": (42.0, -114.1, 36.9, -109.0),
    "VT": (45.0, -73.4, 42.7, -71.5),
    "VA": (39.5, -83.7, 36.5, -75.2),
    "WA": (49.0, -124.7, 45.5, -116.9),
    "WV": (40.6, -82.6, 37.2, -77.7),
    "WI": (47.1, -92.9, 42.5, -86.2),
    "WY": (45.0, -111.1, 41.0, -104.1),
}

_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "Washington D.C.", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

# ISO/RTO zones — bboxes extracted from ISO_Regions_cleaned.shp and reprojected
# from Web Mercator (EPSG:3857) to WGS84 (EPSG:4326) on 2026-05-21.
_ISO_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "CAISO":     (41.2391, -124.3636, 32.5348, -114.1383),
    "ERCOT":     (35.1258, -106.1710, 25.8379,  -93.6435),
    "ISO-NE":    (47.4598,  -73.5253, 41.0410,  -66.9513),
    "MISO":      (49.3666, -106.7718, 29.0422,  -82.4196),
    "Northwest": (48.9998, -124.7619, 37.2517, -104.0560),
    "NYISO":     (45.0107,  -79.7957, 40.5770,  -71.8603),
    "PJM":       (42.5280,  -89.9731, 35.4977,  -73.9234),
    "Southeast": (38.4412,  -93.3174, 24.5480,  -75.5246),
    "Southwest": (44.0807, -115.5100, 30.9243, -102.0420),
    "SPP":       (49.0000, -112.3933, 32.0003,  -92.4759),
}

_ISO_NAMES: dict[str, str] = {
    "CAISO":     "CAISO",
    "ERCOT":     "ERCOT",
    "ISO-NE":    "ISO New England",
    "MISO":      "MISO",
    "Northwest": "Northwest",
    "NYISO":     "NYISO",
    "PJM":       "PJM",
    "Southeast": "Southeast",
    "Southwest": "Southwest",
    "SPP":       "SPP",
}


def list_regions(layer: str) -> list[dict]:
    if layer == "states":
        return [
            {"id": code, "name": _STATE_NAMES[code], "layer": "states", "bbox": list(bbox)}
            for code, bbox in _STATE_BBOXES.items()
        ]
    if layer == "iso":
        return [
            {"id": zone_id, "name": _ISO_NAMES[zone_id], "layer": "iso", "bbox": list(bbox)}
            for zone_id, bbox in _ISO_BBOXES.items()
        ]
    raise ValueError(f"Unknown layer {layer!r}. Valid: 'states', 'iso'")


def get_bbox(layer: str, region_id: str) -> tuple:
    if layer == "states":
        rid = region_id.strip().upper()
        if rid not in _STATE_BBOXES:
            raise ValueError(f"Unknown state '{region_id}'. Valid codes: {sorted(_STATE_BBOXES)}")
        return _STATE_BBOXES[rid]
    if layer == "iso":
        rid = region_id.strip()
        if rid in _ISO_BBOXES:
            return _ISO_BBOXES[rid]
        # case-insensitive fallback
        rid_upper = rid.upper()
        for key in _ISO_BBOXES:
            if key.upper() == rid_upper:
                return _ISO_BBOXES[key]
        raise ValueError(f"Unknown ISO region '{region_id}'. Valid: {sorted(_ISO_BBOXES)}")
    raise ValueError(f"Unknown layer {layer!r}")


def union_bbox(bboxes: list[tuple]) -> tuple:
    if not bboxes:
        raise ValueError("union_bbox requires at least one bbox")
    return (
        max(b[0] for b in bboxes),
        min(b[1] for b in bboxes),
        min(b[2] for b in bboxes),
        max(b[3] for b in bboxes),
    )


def _build_payload() -> dict:
    return {
        "states": list_regions("states"),
        "iso": list_regions("iso"),
    }
