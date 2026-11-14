import matplotlib.pyplot as plt
import numpy as np

from urllib.request import urlopen;

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table

# The time it takes to read SPHEREx files can exceed
# astropy's default timeout limit. Increase it.
from astropy.utils.data import conf
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa
from firefly_client import FireflyClient
from flask import Flask, abort, request, send_file
from PIL import Image
import os

import grid
import irsa
import render

conf.remote_timeout = 120
app = Flask(__name__);
cur_dir = os.path.dirname(__file__);
data_dir = os.path.join(cur_dir, "data");

os.chdir(cur_dir);
os.makedirs(data_dir, exist_ok=True);

def _fetch_image(x: float, y: float, r: float, bandpass: str):
	query = f"""
SELECT
	'https://irsa.ipac.caltech.edu/' || a.uri || '?center={x},{y}d&size={r}' AS uri,
	p.time_bounds_lower
FROM spherex.artifact a
JOIN spherex.plane p ON a.planeid = p.planeid
WHERE 1 = CONTAINS(POINT('ICRS', {x}, {y}), p.poly)
		AND p.energy_bandpassname = '{bandpass}'
ORDER BY p.time_bounds_lower
""";

	return Irsa.query_tap(query, async_job=True, maxrec=1)[0];


def load_pic(x: float, y: float, r: float, bandpass: str):
	img_path = f"{data_dir}/${bandpass}/img/{x}.{y}.{r}.png";

	if os.path.exists(img_path):
		with open(img_path, "rb") as f:
			return f.read()

	url = _fetch_image(x, y, r, bandpass)["access_url"][0];
	with urlopen(url) as res:
		data = res.read();

	img = Image.fromarray(data)
	img = img.convert("L")
	img.save(img_path, format="PNG")

	with open(img_path, "rb") as f:
		return f.read();


def soft_cast(T, x, fallback):
	try:
		if x is None:
			return fallback
		else:
			return T(x)
	except:
		return fallback

@app.get('/api/getPic')
def get_pic():
	# Fix 500 error
	x = soft_cast(float, request.args.get('ra'), 0)
	y = soft_cast(float, request.args.get('dec'), 0)
	r = soft_cast(float, request.args.get("radius"), 0.1);
	band = soft_cast(str, request.args.get("band"), "SPHEREx-D2")

	return load_pic(x, y, r, band), 200, { "Content-Type": "image/png" };

@app.after_request
def allow_cors(response):
	response.headers["Access-Control-Allow-Origin"] = "*"
	return response

def cell_or_404(cell_id):
	try:
		return grid.parse_cell(cell_id)
	except ValueError:
		abort(404)

@app.get('/api/cells')
def get_cells():
	ra = soft_cast(float, request.args.get('ra'), None)
	dec = soft_cast(float, request.args.get('dec'), None)
	fov = min(soft_cast(float, request.args.get('fov'), 2.0), 2.0)
	if ra is None or dec is None:
		return {"error": "ra and dec are required"}, 400
	return {"cells": [{"id": c.id, "wcs": c.wcs_header(), "corners": c.corners} for c in grid.cells_in_view(ra, dec, fov)]}

@app.get('/api/cells/<cell_id>/exposures')
def get_exposures(cell_id):
	cell = cell_or_404(cell_id)
	exposures = irsa.search(*cell.center, cell.id)
	return {"exposures": [
		{"id": e["id"], "mjd": e["mjd"], "ready": os.path.exists(render.tile_path(cell, e["id"]))}
		for e in exposures
	]}

@app.get('/api/cells/<cell_id>/tiles/<exposure_id>.png')
def get_tile(cell_id, exposure_id):
	cell = cell_or_404(cell_id)
	exposure = next((e for e in irsa.search(*cell.center, cell.id) if e["id"] == exposure_id), None)
	if exposure is None:
		abort(404)
	response = send_file(render.render_tile(cell, exposure), mimetype="image/png")
	response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
	return response

@app.get('/')
def hello_world():
	return 'hello world'

if __name__ == '__main__':
	app.run(port=8000)
