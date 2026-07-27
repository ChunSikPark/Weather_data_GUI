# PWW I/O

Read, crop, and write PowerWorld `.pww` weather files. See {doc}`../guides/pww-files`
for a walkthrough; this page is the function-level reference.

```python
from TeamOverbyeWeather import pww_io, localcrop
```

## Conventions

- Arrays are `uint8`, shaped `(time, variable, latitude, longitude)`
- Latitude ascends; **longitude descends** (index 0 is `lon_max`)
- `255` marks missing data
- Bounding boxes are `(lat_max, lon_min, lat_min, lon_max)`
- `date_min` / `date_max` are OLE Automation days; `crop_to_timerange` takes
  Unix epoch seconds

## pww_io

```{eval-rst}
.. automodule:: TeamOverbyeWeather.pww_io
   :members: read_pww, read_pww_file, crop_to_bbox, crop_to_timerange, concat_time, write_pww
   :member-order: bysource
```

## localcrop

```{eval-rst}
.. automodule:: TeamOverbyeWeather.localcrop
   :members: crop_file
   :member-order: bysource
```
