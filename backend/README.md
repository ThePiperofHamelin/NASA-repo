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

## API

`GET /api/getPic?ra=<deg>&dec=<deg>&n=<hdu>` returns a PNG image.

- `ra`, `dec`: sky coordinates in degrees
- `n`: the HDU index in the FITS file

Example: `http://localhost:8000/api/getPic?ra=304.693508&dec=42.448194&n=1`
