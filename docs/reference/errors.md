# Exceptions

```python
from TeamOverbyeWeather import (
    WeatherAPIError,
    RegionTooLargeError,
    ServerBusyError,
)
```

All three inherit from {class}`~TeamOverbyeWeather.WeatherAPIError`, so a single
`except WeatherAPIError` catches every API failure.

```python
from TeamOverbyeWeather import WeatherAPIError

try:
    client.download("era5", dates="1999-Q1", dest="./data")
except WeatherAPIError as exc:
    print(exc.status, exc.detail)     # 404  No file ID for era5_na 1999-Q1
```

Argument mistakes — an unknown source, a malformed date, an inverted bounding
box — raise plain {class}`ValueError` before any request is made.

```{eval-rst}
.. autoclass:: TeamOverbyeWeather.WeatherAPIError
   :members:

.. autoclass:: TeamOverbyeWeather.RegionTooLargeError
   :members:

.. autoclass:: TeamOverbyeWeather.ServerBusyError
   :members:
```
