# Backend

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```sh
python main.py
```

## Pre-warm tiles

Tiles are slow to load the first time. This loads them in advance:

```sh
python prewarm.py --ra 304.69 --dec 42.44
```

Use `--start`/`--end` (MJD) and `--band` to pre-warm a filtered set of observations.

## API

The sky is divided into a grid of cells about 1° across.

- `GET /api/cells?ra=<deg>&dec=<deg>&fov=<deg>` lists the cells in view (`fov` is at most 2), with each cell's WCS and corners.
- `GET /api/cells/<cell>/exposures` lists the SPHEREx observations covering the centre of a cell.
- `GET /api/cells/<cell>/tiles/<exposure>.png` returns a colour tile for one observation. Blue is the short-wavelength detector, red is its paired long-wavelength detector, and green is the average of the two.
- `GET /api/getPic?ra=<deg>&dec=<deg>&radius=<deg>&band=<bandpass>` returns a cutout image.

### Filters

Exposure and cutout searches are backed by SIA2 queries against the IRSA SIA
service, so they accept optional filters:

- `start=<mjd>` and `end=<mjd>` select observations overlapping the requested
  Modified Julian Date range. Either bound may be omitted.
- `band=<bandpass>` restricts the result to one or more bandpasses, for example
  `SPHEREx-D1`. Repeat the parameter or separate values with commas.
- `collection=<name>` restricts the result to one or more collections. The
  default is `spherex_dr1,spherex_qr3`.
- `obs_id=<id>` returns a single observation.

For example:

```sh
curl 'http://localhost:8000/api/cells/219_133/exposures?start=60790&end=60800&band=SPHEREx-D1'
```
