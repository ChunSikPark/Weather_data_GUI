# Cropping to a Region

There are three ways to say "only this area". Use exactly one of `region`,
`iso`, or `bbox`.

## By state

```python
client.download("noaa", dates="2026-07-22T12Z", region="TX", dest="./data")
```

All 51 entries (50 states plus DC) are available by two-letter postal code:

```python
client.region_ids("states")
```

```text
['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', ...]
```

### Several states

```python
client.download("noaa", dates="2026-07-22T12Z",
                region=["TX", "OK", "NM"], dest="./data")
```

:::{important}
Multiple states crop to the **union bounding box**, not to the state outlines.
Asking for Texas, Oklahoma and New Mexico gives you one rectangle containing all
three — including the corners that belong to none of them. Bounding boxes are
rectangles; they cannot follow a border.
:::

The effect on grid size:

| Request | Grid |
|---|---|
| `region="TX"` | 44 × 53 |
| `region=["TX", "OK", "NM"]` | 46 × 63 |
| `iso="ERCOT"` | 39 × 51 |

## By ISO zone

```python
client.download("noaa", dates="2026-07-22T12Z", iso="ERCOT", dest="./data")
```

```python
client.region_ids("iso")
```

```text
['CAISO', 'ERCOT', 'ISO-NE', 'MISO', 'Northwest',
 'NYISO', 'PJM', 'Southeast', 'Southwest', 'SPP']
```

ISO zones come from a shapefile on the server. If that file is missing or in the
wrong projection the list comes back empty — see {doc}`troubleshooting`.

## By bounding box

For anything the presets do not cover:

```python
client.download("noaa", dates="2026-07-22T12Z",
                bbox=(33.0, -100.0, 30.0, -96.0), dest="./data")
```

:::{warning}
The order is **`(lat_max, lon_min, lat_min, lon_max)`** — north, west, south,
east. This is the CDS convention, and it is *not* the `(min, min, max, max)`
ordering many GIS tools use. Longitudes west of the meridian are negative.
:::

Mnemonic: **top, left, bottom, right** — the same order you would read the edges
of a box on a map.

The client rejects an inverted box before making a request:

```python
client.download("noaa", dates="...", bbox=(30.0, -96.0, 33.0, -100.0))
```

```text
ValueError: bbox (30.0, -96.0, 33.0, -100.0) is inverted; expected
(lat_max, lon_min, lat_min, lon_max) with lat_max > lat_min and lon_max > lon_min
```

## Looking up the boxes

To see the exact box behind a preset:

```python
regions = client.regions()
for entry in regions["states"]:
    if entry["id"] == "TX":
        print(entry)
```

```text
{'id': 'TX', 'name': 'Texas', 'layer': 'states', 'bbox': [36.5, -106.6, 25.8, -93.5]}
```

Useful when you want to start from a state and widen it:

```python
lat_max, lon_min, lat_min, lon_max = entry["bbox"]
padded = (lat_max + 1, lon_min - 1, lat_min - 1, lon_max + 1)
client.download("noaa", dates="...", bbox=padded, dest="./data")
```

## How cropping works

The server slices the grid to the smallest rectangle covering your box, snapped
to the 0.25° grid. Requests are clamped to what the file actually contains, so a
box larger than the dataset simply returns the whole dataset instead of failing.

Because cropping happens before transfer, a smaller region means a smaller
download — this is the main reason to use the API rather than pulling raw files.

## Size limits

Large-area requests against **HRRR monthly archives** are refused with HTTP 413,
because cropping a month of CONUS data server-side would exhaust its memory. The
threshold is 2380 square degrees. Above it, the client downloads the file whole
and crops locally instead (see {doc}`downloading`).

Everything else — NOAA, ERA5, HRRR forecasts, and all the per-day HRRR files —
crops server-side at any size.
