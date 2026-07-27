# Browsing the Catalog

Before downloading anything you need to know two things: which **source and
type** you want, and which **date keys** exist for it.

## Sources and types

Three sources, each with sub-types that map to a different collection of files:

```python
client.sources()          # ['era5', 'hrrr', 'noaa']
client.types("hrrr")      # ['archive', 'current', 'forecast', ...]
```

### ERA5 — reanalysis

| `type` | Coverage | Date key |
|---|---|---|
| `historical` (default) | North America | `YYYY-Qn` |
| `texas` | Texas only | `YYYY-Qn` |

Aliases: `na` / `north_america` for the default, `tx` for Texas.

### HRRR — high-resolution CONUS

| `type` | Steps | Period per file | Date key |
|---|---|---|---|
| `current` | 15-minute | one day | `YYYY-MM-DD` |
| `archive` | 15-minute | one month | `YYYY-MM` |
| `hourly_current` | hourly | one day | `YYYY-MM-DD` |
| `hourly_archive` | hourly | one month | `YYYY-MM` |
| `forecast` (default) | hourly, 48 h out | one cycle | `YYYY-MM-DDTHHZ` |

"Current" means the current calendar year, stored as individual days.
"Archive" means previous years, bundled by month. The hourly archives reach back
furthest — as of writing, to 2014.

### NOAA / GFS — forecasts

| `type` | Source folder | Date key |
|---|---|---|
| `recent` (default) | main folder | `YYYY-MM-DDTHHZ` |
| `archive` | archive folder | `YYYY-MM-DDTHHZ` |

### Extreme — curated historical events

| `type` | Coverage | Key |
|---|---|---|
| `events` (default) | 62 events, 1899–2023, by ISO zone | `YYYY-MM-DD_Title_Zone` |

Named historical extremes — the three hottest and three coldest per ISO zone,
plus notable scenarios — each with an animation. These are browsed rather than
sliced by date; see {doc}`extreme-events`.

:::{warning}
`recent` and `archive` are **separate folders**, not a date split. A cycle in one
will not appear in the other, and "recent" does not necessarily mean
"chronologically newer". Always list the type you intend to download from.
:::

## Listing dates

{meth}`~TeamOverbyeWeather.WeatherClient.list` returns date keys newest first:

```python
client.list("hrrr", "hourly_archive")
```

```text
['2026-06', '2014-12', '2014-11', '2014-10', '2014-09', ...]
```

Feed those straight back into
{meth}`~TeamOverbyeWeather.WeatherClient.download`, so you never have to hand-format a
date:

```python
recent_days = client.list("hrrr", "current")[:5]
client.download("hrrr", type="current", dates=recent_days, region="TX", dest="./data")
```

## Checking a specific date exists

```python
"2026-07-21" in client.list("hrrr", "current")
```

Asking for a missing date raises
{class}`~TeamOverbyeWeather.WeatherAPIError` with HTTP 404 rather than writing an
empty file.

## The raw catalog

{meth}`~TeamOverbyeWeather.WeatherClient.catalog` returns everything at once,
keyed by the internal API source name:

```python
catalog = client.catalog()
print(catalog.keys())
```

```text
dict_keys(['hrrr_forecast', 'hrrr_history', 'hrrr_history_current',
           'hrrr_history_archive', 'hrrr_history_hourly_current',
           'hrrr_history_hourly_archive', 'noaa_forecast',
           'noaa_forecast_recent', 'noaa_forecast_archive',
           'era5_na', 'era5_tx'])
```

Each entry holds a list of date keys plus the underlying file ids. You can pass
these internal names directly to `download()` if you prefer them to the
source/type pair:

```python
client.download("hrrr_history_hourly_archive", dates="2014-11", region="TX")
```

## Caching

The server caches its catalog for 30 minutes, and the client caches the response
for the life of the `WeatherClient` object. If data was just uploaded and you do
not see it:

```python
client.catalog(refresh=True)
```

That forces a server-side rebuild and clears the local cache.
