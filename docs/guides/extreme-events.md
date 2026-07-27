# Extreme Temperature Events

A curated set of **62 historical extreme-weather events** spanning 1899 to 2023,
selected for power system studies. Unlike the other sources — which are
continuous archives you slice by date — these are named events with a story:
Winter Storm Uri, the 2023 Texas Heat Dome, the Great Arctic Outbreak of 1899.

Every event has weather data (`.pww`) and an **animation** (`.mp4`) showing the
event developing.

## How events were selected

For each ISO zone: the **three hottest and three coldest events on record**,
plus additional notable scenarios where they matter — for example ERCOT's
February 2011 rolling outages, which is an operational event rather than a
temperature record.

| Zone | Events | Hot | Cold | Range |
|---|---|---|---|---|
| `CAISO` | 6 | 3 | 3 | 1942–2023 |
| `MISO` | 8 | 5 | 3 | 1962–2023 |
| `NYISO_ISONE` | 6 | 3 | 3 | 1982–2011 |
| `Northwest` | 8 | 5 | 3 | 1954–2021 |
| `PJM` | 6 | 3 | 3 | 1980–2012 |
| `SPP` | 7 | 4 | 3 | 1954–2011 |
| `Southeast` | 6 | 3 | 3 | 1952–1989 |
| `Southwest` | 6 | 3 | 3 | 1963–2022 |
| `Texas` | 8 | 4 | 4 | 1954–2023 |
| `NorthAmerica` | 1 | 0 | 1 | 1899 |

`NorthAmerica` holds the Great Arctic Outbreak of 1899, which was
continent-wide rather than confined to one zone.

:::{important}
Events are selected **per zone**, so one weather system can appear several
times. 11 of the 62 do. Each copy is cropped and named for its own zone, and
**the date reflects when the system reached that zone** — so the same event can
carry different dates:

```text
1983-12-23  North American Cold Wave   SPP, Texas
1983-12-24  North American Cold Wave   MISO, PJM, Southeast
```

Two entries, one storm, a day apart as it moved east. Match on title and
approximate date rather than exact date if you are deduplicating across zones.
:::

## Finding an event

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

client.extreme.zones()
```

```text
['CAISO', 'MISO', 'NYISO_ISONE', 'NorthAmerica', 'Northwest',
 'PJM', 'SPP', 'Southeast', 'Southwest', 'Texas']
```

```python
for event in client.extreme.events("Texas"):
    print(event["date"], event["title"])
```

```text
2023-06-25 Texas Heat Dome
2021-02-14 Winter Storm Uri
2011-08-01 Texas Drought and Heat
2011-02-01 ERCOT Rolling Outages
1989-12-22 Cold Wave
1983-12-23 North American Cold Wave
1980-07-14 US Heat Wave
1954-07-13 Central US Heat Wave
```

Search by title when you know the name but not the zone:

```python
client.extreme.find("uri")
```

```text
[{'key': '2021-02-14_Winter_Storm_Uri_Texas', 'date': '2021-02-14',
  'title': 'Winter Storm Uri', 'zone': 'Texas', 'has_video': True}]
```

### Event keys

Each event is identified by a key carrying its date, title and zone:

```text
2021-02-14_Winter_Storm_Uri_Texas
^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^^^^
date       title            zone
```

Pass keys straight from `events()` or `find()` rather than typing them.

## Downloading event data

Same arguments as every other source — region and time cropping both apply:

```python
event = client.extreme.find("uri")[0]

path = client.extreme.download(
    event["key"],
    region_ids=["TX"],
    region_layer="states",
    dest="./data",
)[0]
```

```text
extreme_events_2021-02-14_Winter_Storm_Uri_Texas_TX.pww    168 steps
```

168 hourly steps — the event covers a week. Narrow it to the worst of the
crisis:

```python
path = client.extreme.download(
    event["key"],
    region_ids=["TX"], region_layer="states",
    time_start="2021-02-15T00:00",
    time_end="2021-02-15T12:00",
    dest="./data",
)[0]
```

```text
..._TX_T20210215H0000to20210215H1200.pww                    13 steps
```

The unified call works too, if you prefer one entry point:

```python
client.download("extreme", dates=event["key"], region="TX", dest="./data")
```

### Several events at once

```python
keys = [e["key"] for e in client.extreme.events("Texas")]
paths = client.extreme.download(keys, region_ids=["TX"], region_layer="states",
                                dest="./data")
```

One file per event, as everywhere else in this package.

## Animations

Each event has an MP4 showing the event unfolding — typically 20–30 MB.

```python
client.extreme.video(event["key"], dest="./data")
```

```text
data/2021-02-14_Winter_Storm_Uri_Texas.mp4
```

These are also what the [web portal](https://weather-data-gui.pages.dev) plays
inline in the event gallery. The server honours HTTP range requests, so a
browser fetches only the part it plays rather than the whole file on each seek.

## Coverage maps

Each zone has a PNG showing its geographic extent:

```python
client.extreme.coverage("Texas", dest="./data")
```

```text
data/coverage_Texas.png
```

Useful for figures, and for checking a zone covers what you assume before
cropping to it.

## Reading the data

Identical to every other `.pww` — see {doc}`pww-files`:

```python
from TeamOverbyeWeather import pww_io

header, stations, arr = pww_io.read_pww(open(path, "rb").read())
print(arr.shape)        # (time, variable, latitude, longitude)
```

## A worked example

Every Texas cold event, cropped to ERCOT, ready for a resilience study:

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()

cold = [e for e in client.extreme.events("Texas")
        if any(w in e["title"].lower() for w in ("cold", "winter", "freeze"))]

for event in cold:
    print(event["date"], event["title"])
    client.extreme.download(event["key"], region_ids=["ERCOT"],
                            region_layer="iso", dest="./cold_events")
    client.extreme.video(event["key"], dest="./cold_events")
```

```text
2021-02-14 Winter Storm Uri
1989-12-22 Cold Wave
1983-12-23 North American Cold Wave
```

## REST API

For non-Python callers:

| Path | Purpose |
|---|---|
| `/api/catalog` | `extreme_events` section: zones, events, keys |
| `/api/download?source=extreme_events&dates=<key>` | event data |
| `/api/download/region?source=extreme_events&...` | cropped event data |
| `/api/extreme/video?key=<key>` | animation, supports range requests |
| `/api/extreme/coverage?zone=<zone>` | zone coverage map |

See {doc}`../reference/rest-api`.
