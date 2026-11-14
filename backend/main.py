import os

from flask import Flask, abort, request, send_file

import grid
import irsa
import render

app = Flask(__name__)


def soft_cast(T, x, fallback):
	try:
		return fallback if x is None else T(x)
	except (TypeError, ValueError):
		return fallback


def cell_or_404(cell_id):
	try:
		return grid.parse_cell(cell_id)
	except ValueError:
		abort(404)


@app.after_request
def allow_cors(response):
	response.headers["Access-Control-Allow-Origin"] = "*"
	return response


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


if __name__ == '__main__':
	app.run(port=int(os.getenv("PORT", "8000")), threaded=True)
