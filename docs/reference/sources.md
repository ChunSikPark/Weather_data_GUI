# Source Clients

Each source has a namespace on the client — `client.era5`, `client.hrrr`,
`client.noaa`. These predate the unified
{meth}`~TeamOverbyeWeather.WeatherClient.download` method and are kept so
existing scripts keep working.

:::{note}
New code should use `client.download()`. These wrappers just translate their
arguments and call it. Everything they can do, it can do — usually with less
ceremony.
:::

All of them accept the same keyword arguments as `download()`, so `time_start`,
`time_end`, `show_progress`, and `local_crop` work here too:

```python
client.hrrr.download_region(
    days=["2026-07-21"],
    type="hourly_current",
    region_ids=["TX"],
    region_layer="states",
    time_start="2026-07-21T06:00",
    dest="./data",
)
```

## Argument mapping

The wrappers use the older `region_ids` + `region_layer` pair; `download()` uses
`region` and `iso`:

| Wrapper | Unified equivalent |
|---|---|
| `region_ids=["TX"], region_layer="states"` | `region=["TX"]` |
| `region_ids=["ERCOT"], region_layer="iso"` | `iso=["ERCOT"]` |
| `bbox=(...)` | `bbox=(...)` |

## ERA5

```{eval-rst}
.. autoclass:: TeamOverbyeWeather.sources.era5.ERA5Client
   :members:
   :member-order: bysource
```

## HRRR

```{eval-rst}
.. autoclass:: TeamOverbyeWeather.sources.hrrr.HRRRClient
   :members:
   :member-order: bysource
```

## NOAA / GFS

```{eval-rst}
.. autoclass:: TeamOverbyeWeather.sources.noaa.NOAAClient
   :members:
   :member-order: bysource
```

## Extreme events

Unlike the others, this namespace is not a legacy wrapper — event browsing,
animations and coverage maps have no equivalent on `download()`. See
{doc}`../guides/extreme-events`.

```{eval-rst}
.. autoclass:: TeamOverbyeWeather.sources.extreme.ExtremeClient
   :members:
   :member-order: bysource
```
