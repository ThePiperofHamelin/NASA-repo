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

## API

The sky is divided into a grid of cells about 1° across.

- `GET /api/cells?ra=<deg>&dec=<deg>&fov=<deg>` lists the cells in view (`fov` is at most 2), with each cell's WCS and corners.
- `GET /api/cells/<cell>/exposures` lists the SPHEREx observations covering the centre of a cell.
- `GET /api/cells/<cell>/tiles/<exposure>.png` returns a colour tile for one observation. Blue is the short-wavelength detector, red is its paired long-wavelength detector, and green is the average of the two.
