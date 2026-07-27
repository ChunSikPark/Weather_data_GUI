# Contributing

## Local setup

```bash
git clone https://github.com/ChunSikPark/Weather_data_GUI.git
cd Weather_data_GUI

pip install -e package/          # the SDK, editable
pip install -r docs/requirements.txt
```

Run the backend locally if you are changing it:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Point the client at it:

```python
client = WeatherClient(base_url="http://localhost:8000")
```

The backend needs `GDRIVE_CREDENTIALS_JSON_CONTENT` set to a service-account JSON
with Viewer access on the data folders. Without it the catalog will be empty but
the app still starts.

## Building the docs

```bash
sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. Read the Docs builds the same tree from
`.readthedocs.yaml`.

## Adding a data source

Five places, in this order:

1. `backend/catalog.py` — add the folder id to `_DEFAULT_FOLDERS`, write a
   `_build_<source>()`, call it from `build_catalog()`, add the key to
   `_empty_catalog()`
2. `backend/download.py` — add `_SOURCE_LOOKUP` and `_FILENAME_PATTERNS` entries
3. `package/TeamOverbyeWeather/registry.py` — add to `_API_KEYS` and `_TYPES`
4. `frontend/main.js` — add to `TYPE_DEFS` and `getApiSourceKey()`
5. `docs/guides/catalog.md` — document the new type and its date-key format

Check the real filenames before writing a regex:

```bash
curl "<backend>/api/debug/folder?folder_id=<id>&limit=50"
```

Filename conventions vary between folders more than you would expect. Guessing
wastes time; the debug endpoint takes seconds.

## Things that will bite you

**`pww_io.py` exists twice.** `backend/pww_io.py` is the original;
`package/TeamOverbyeWeather/pww_io.py` is a copy. Change one, copy to the other.

**Bounding box ordering is `(lat_max, lon_min, lat_min, lon_max)`** everywhere —
north, west, south, east. Not the ordering most GIS libraries use.

**The longitude axis descends.** Index 0 is `lon_max`. Latitude ascends.

**Always `.copy()` after slicing** before writing a PWW. Numpy slices are views.

**`255` is the missing-data sentinel**, not a value.

**Times are OLE Automation days in the file, Unix epoch seconds in the API.**
`crop_to_timerange` takes epoch seconds; `header["date_min"]` is OLE days. Do not
pass one where the other is expected — they are both floats, so nothing will stop
you, and the result is a nonsensical date rather than an error.

**HRRR history regexes are loose on the extension** on purpose. Older archives
are `.pww.gz`; do not tighten to `\.zip$`.

**Do not reintroduce `get_file_url`** in `download.py`. Fetching large Drive
files by URL hits a virus-scan interstitial and silently returns HTML instead of
data. Everything goes through the service account.

## Testing a change to the crop path

Compare server output against local output — they should agree exactly:

```python
from TeamOverbyeWeather import WeatherClient, pww_io, localcrop

client = WeatherClient(show_progress=False)
bbox = (36.5, -106.6, 25.8, -93.5)

server = client.download("hrrr", type="current", dates="2026-07-21",
                         region="TX", dest="./tmp")[0]
raw    = client._plain("hrrr_history_current", "2026-07-21",
                       __import__("pathlib").Path("./tmp"), False)
local  = localcrop.crop_file(raw, "./tmp/local.pww", bbox=bbox)

for p in (server, local):
    _, _, arr = pww_io.read_pww(open(p, "rb").read())
    print(p.name, arr.shape)
```

Both must report 96 time steps for a 15-minute day. A result of 24 means the
four quarter files were not stitched.

## Publishing

**Package** — bump `version` in `package/pyproject.toml` and `__version__` in
`__init__.py` (keep them equal), then build and upload:

```bash
cd package
rm -rf dist build
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

A version number on PyPI can never be reused, so run `twine check` first and
confirm the metadata (especially `[project.urls]`) is right before uploading.
Verify afterwards in a clean environment:

```bash
python -m venv /tmp/check && /tmp/check/bin/pip install TeamOverbyeWeather
```

**Backend and frontend** — push to `main`; both auto-deploy. Refresh the catalog
afterwards:

```bash
curl <backend>/api/catalog/refresh
```

## Style

Match the surrounding code. Google-style docstrings — they are what the API
reference is generated from, so a function without one shows up bare in the docs.
