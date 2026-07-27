# Installation

## Requirements

- Python 3.10 or newer
- An internet connection (the package talks to a hosted API — there is nothing
  to run locally)

No credentials, API keys, or Google Drive access are needed. The server holds
the service-account credentials; you just make requests.

## Install from PyPI

```bash
pip install TeamOverbyeWeather
```

This pulls in `requests`, `tqdm`, and `numpy`.

### In a Jupyter notebook

```python
%pip install TeamOverbyeWeather --quiet
```

Restart the kernel afterwards so the import picks up the new package.

## Verify the install

```python
from TeamOverbyeWeather import WeatherClient

client = WeatherClient()
print(client.status())
```

You should see a dictionary of pipeline states:

```text
{'noaa': 'unknown', 'hrrr_forecast': 'unknown',
 'hrrr_history': 'unknown', 'era5': 'unknown'}
```

:::{note}
`unknown` is expected and harmless. The status file that reports pipeline health
is produced by the ingest machines and is not present on the hosted API, so
every source reports `unknown` there. Data downloads work regardless — use
{meth}`~TeamOverbyeWeather.WeatherClient.catalog` or
{meth}`~TeamOverbyeWeather.WeatherClient.list` to confirm data is actually
available.
:::

A better smoke test is to ask what data exists:

```python
print(client.list("noaa")[:5])
```

```text
['2026-07-22T12Z', '2026-07-22T06Z', '2026-07-22T00Z',
 '2026-07-21T18Z', '2026-07-21T12Z']
```

If that returns a non-empty list, you are ready to go.

## Install for development

If you are working on the package itself:

```bash
git clone https://github.com/ChunSikPark/Weather_data_GUI.git
cd Weather_data_GUI/package
pip install -e .
```

## Pointing at a different backend

The client defaults to the production API. Override it for local development:

```python
client = WeatherClient(base_url="http://localhost:8000")
```

## Upgrading

```bash
pip install --upgrade TeamOverbyeWeather
```

To install the unreleased state of `main` instead:

```bash
pip install --upgrade --force-reinstall \
  "git+https://github.com/ChunSikPark/Weather_data_GUI.git#subdirectory=package"
```

Version 0.3.0 added the unified {meth}`~TeamOverbyeWeather.WeatherClient.download`
method, time cropping, and access to the hourly HRRR archives. The older
per-source methods (`client.hrrr.download_history()` and friends) still work —
see {doc}`../reference/sources`.
