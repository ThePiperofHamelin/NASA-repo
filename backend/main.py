import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import functools
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

import certifi
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, gaussian_filter, median_filter

from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.utils.data import conf
from astropy.visualization import make_lupton_rgb
from astropy.wcs import WCS
from astropy.wcs.utils import (
	celestial_frame_to_wcs,
	pixel_to_pixel,
	pixel_to_skycoord,
	proj_plane_pixel_scales,
	skycoord_to_pixel,
	wcs_to_celestial_frame,
)
from astroquery.ipac.irsa import Irsa
from flask import Flask, abort, request, send_file

# Increase Astropy's default timeout for large SPHEREx remote reads
conf.remote_timeout = 120

# ---------------------------------------------------------------------------
# Configuration & Global Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path(os.getenv("CACHE_DIR", str(BASE_DIR / ".cache")))
DATA_DIR = Path(os.getenv("DATA_DIR", str(CACHE_DIR / "data")))

COLLECTIONS = ("spherex_dr1", "spherex_qr3")
MAX_DOWNLOADS = int(os.getenv("IRSA_DOWNLOADS", "3"))
MAX_SEARCHES = int(os.getenv("IRSA_SEARCHES", "3"))

RGB_STRETCH = float(os.getenv("RGB_STRETCH", "1.5"))
RGB_Q = float(os.getenv("RGB_Q", "8.0"))
RGB_MIN = float(os.getenv("RGB_MIN", "0.0"))

SEARCH_RADIUS = 1 * u.arcsec
MJD_MIN = 0.0
MJD_MAX = 100000.0

BANDPASS_WAVELENGTHS = {
	"SPHEREx-D1": (0.75, 1.09),
	"SPHEREx-D2": (1.10, 1.62),
	"SPHEREx-D3": (1.63, 2.41),
	"SPHEREx-D4": (2.42, 3.82),
	"SPHEREx-D5": (3.83, 4.41),
	"SPHEREx-D6": (4.42, 5.00),
}

CELL_DEG = 1.0
PIXEL_DEG = 6.15 / 3600.0
ROWS = round(180 / CELL_DEG)
_CHUNK_SIZE = 1_000_000

# Concurrency controls
_ssl_context = ssl.create_default_context(cafile=certifi.where())
_download_slots = threading.BoundedSemaphore(MAX_DOWNLOADS)
_search_slots = threading.BoundedSemaphore(MAX_SEARCHES)


class KeyedLock:
	"""Reentrant key-level lock pool that automatically removes unused locks."""

	def __init__(self):
		self._locks: dict[str, threading.Lock] = {}
		self._counts: dict[str, int] = {}
		self._guard = threading.Lock()

	@contextmanager
	def __call__(self, key: str):
		with self._guard:
			lock = self._locks.setdefault(key, threading.Lock())
			self._counts[key] = self._counts.get(key, 0) + 1
		lock.acquire()
		try:
			yield
		finally:
			lock.release()
			with self._guard:
				self._counts[key] -= 1
				if self._counts[key] <= 0:
					self._locks.pop(key, None)
					self._counts.pop(key, None)


key_lock = KeyedLock()


def cache_path(*parts: str) -> str:
	path = CACHE_DIR.joinpath(*parts)
	path.parent.mkdir(parents=True, exist_ok=True)
	return str(path)


# ---------------------------------------------------------------------------
# Grid & Cell Geometry
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=256)
def row_count(j: int) -> int:
	"""Number of cells along RA for row j."""
	dec_c = -90.0 + (j + 0.5) * CELL_DEG
	return max(1, math.floor(360.0 * math.cos(math.radians(dec_c)) / CELL_DEG))


class Cell:
	"""A ~1 deg cell on the celestial sphere."""

	__slots__ = ("i", "j", "id", "ra_width", "dec0", "ra0", "center", "corners")

	def __init__(self, i: int, j: int):
		self.i = int(i)
		self.j = int(j)
		self.id = f"{self.i}_{self.j}"
		self.ra_width = 360.0 / row_count(self.j)
		self.dec0 = -90.0 + self.j * CELL_DEG
		self.ra0 = self.i * self.ra_width
		self.center = (self.ra0 + self.ra_width / 2.0, self.dec0 + CELL_DEG / 2.0)
		ra1, dec1 = self.ra0 + self.ra_width, self.dec0 + CELL_DEG
		self.corners = [(self.ra0, self.dec0), (ra1, self.dec0), (ra1, dec1), (self.ra0, dec1)]

	def __eq__(self, other: object) -> bool:
		if not isinstance(other, Cell):
			return False
		return self.i == other.i and self.j == other.j

	def __hash__(self) -> int:
		return hash((self.i, self.j))

	def __repr__(self) -> str:
		return f"Cell({self.id})"

	def contains(self, ra, dec):
		"""Check whether coordinates fall inside this cell."""
		return ((ra - self.ra0) % 360.0 < self.ra_width) & (dec >= self.dec0) & (dec < self.dec0 + CELL_DEG)

	def wcs_header(self) -> dict:
		"""Generate FITS WCS header for this cell's projection."""
		dec1 = self.dec0 + CELL_DEG
		widest_dec = 0.0 if self.dec0 <= 0 <= dec1 else min(abs(self.dec0), abs(dec1))
		side = max(self.ra_width * math.cos(math.radians(widest_dec)), CELL_DEG) * 1.05
		n = math.ceil(side / PIXEL_DEG)
		ra, dec = self.center
		return {
			"NAXIS": 2,
			"NAXIS1": n,
			"NAXIS2": n,
			"CTYPE1": "RA---TAN",
			"CTYPE2": "DEC--TAN",
			"CUNIT1": "deg",
			"CUNIT2": "deg",
			"CRVAL1": ra,
			"CRVAL2": dec,
			"CRPIX1": (n + 1) / 2.0,
			"CRPIX2": (n + 1) / 2.0,
			"CDELT1": -PIXEL_DEG,
			"CDELT2": PIXEL_DEG,
		}


def parse_cell(cell_id: str) -> Cell:
	"""Parse a cell id string like '226_131' into a Cell object."""
	try:
		parts = cell_id.split("_")
		if len(parts) != 2:
			raise ValueError(cell_id)
		i, j = int(parts[0]), int(parts[1])
	except (ValueError, TypeError):
		raise ValueError(f"Invalid cell ID: {cell_id}") from None
	if not (0 <= j < ROWS and 0 <= i < row_count(j)):
		raise ValueError(f"Cell ID out of bounds: {cell_id}")
	return Cell(i, j)


def cell_at(ra: float, dec: float) -> Cell:
	"""Find the cell containing a given RA and Dec."""
	j = min(ROWS - 1, max(0, math.floor((dec + 90.0) / CELL_DEG)))
	n = row_count(j)
	return Cell(math.floor((ra % 360.0) / (360.0 / n)) % n, j)


def angular_sep(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
	"""Calculate angular separation between two points in degrees using Haversine formula."""
	r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
	dlon = r2 - r1
	dlat = d2 - d1
	a = math.sin(dlat / 2.0) ** 2 + math.cos(d1) * math.cos(d2) * math.sin(dlon / 2.0) ** 2
	return math.degrees(2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a))))


def cells_in_view(ra: float, dec: float, fov: float) -> list[Cell]:
	"""Find all cells overlapping the field of view."""
	radius = fov * 0.75
	reach = radius + CELL_DEG
	j_lo = max(0, math.floor((dec - reach + 90.0) / CELL_DEG))
	j_hi = min(ROWS - 1, math.floor((dec + reach + 90.0) / CELL_DEG))
	cells = []
	for j in range(j_lo, j_hi + 1):
		n = row_count(j)
		w = 360.0 / n
		dec_c = -90.0 + (j + 0.5) * CELL_DEG
		cos_d = max(math.cos(math.radians(dec_c)), 1e-6)
		span = min(180.0, reach / cos_d + w)
		i_lo = math.floor((ra - span) / w)
		i_hi = math.floor((ra + span) / w)
		seen = set()
		for k in range(i_lo, i_hi + 1):
			i = k % n
			if i in seen:
				continue
			seen.add(i)
			cell = Cell(i, j)
			cra, cdec = cell.center
			half_diag = math.hypot(w * cos_d, CELL_DEG) / 2.0
			if angular_sep(ra, dec, cra, cdec) <= radius + half_diag:
				cells.append(cell)
	return cells


# ---------------------------------------------------------------------------
# WCS Reprojection & Mosaic Helpers
# ---------------------------------------------------------------------------

def _as_wcs(projection) -> WCS:
	if isinstance(projection, WCS):
		return projection
	return WCS(projection)


def _bilinear_sample(data: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
	"""Sample a 2D array at fractional pixel coordinates with bilinear interpolation."""
	height, width = data.shape
	values = np.full(x.shape, np.nan, dtype=float)
	inside = (
		(x >= -0.5)
		& (x <= width - 0.5)
		& (y >= -0.5)
		& (y <= height - 0.5)
	)

	if not inside.any():
		return values

	xs = np.clip(x[inside], 0, width - 1)
	ys = np.clip(y[inside], 0, height - 1)

	if width < 2 or height < 2:
		xi = np.clip(np.rint(xs), 0, width - 1).astype(np.intp)
		yi = np.clip(np.rint(ys), 0, height - 1).astype(np.intp)
		values[inside] = data[yi, xi]
		return values

	x0 = np.floor(xs).astype(np.intp)
	y0 = np.floor(ys).astype(np.intp)

	np.clip(x0, 0, width - 2, out=x0)
	np.clip(y0, 0, height - 2, out=y0)

	dx = xs - x0
	dy = ys - y0

	top = data[y0, x0] * (1.0 - dx) + data[y0, x0 + 1] * dx
	bottom = data[y0 + 1, x0] * (1.0 - dx) + data[y0 + 1, x0 + 1] * dx
	values[inside] = top * (1.0 - dy) + bottom * dy

	return values


def reproject_interp(input_data, output_projection, shape_out=None):
	"""Resample a 2D image onto another celestial WCS using bilinear interpolation."""
	data, input_wcs = input_data
	data = np.asarray(data, dtype=float)
	if data.ndim != 2:
		raise ValueError("Only 2-dimensional images can be reprojected")

	input_wcs = _as_wcs(input_wcs)
	output_wcs = _as_wcs(output_projection)

	if shape_out is None:
		shape_out = output_wcs.array_shape
		if shape_out is None:
			raise ValueError("shape_out is required when the output WCS has no array shape")
	shape_out = tuple(int(size) for size in shape_out)
	if len(shape_out) != 2:
		raise ValueError("shape_out must contain two dimensions")

	n_rows, n_cols = shape_out
	projected = np.full(shape_out, np.nan, dtype=float)

	rows_per_chunk = max(1, _CHUNK_SIZE // max(n_cols, 1))
	for start in range(0, n_rows, rows_per_chunk):
		stop = min(n_rows, start + rows_per_chunk)
		xs, ys = np.meshgrid(
			np.arange(0, n_cols, dtype=float),
			np.arange(start, stop, dtype=float),
		)
		x_in, y_in = pixel_to_pixel(
			output_wcs,
			input_wcs,
			xs,
			ys,
		)
		projected[start:stop] = _bilinear_sample(data, x_in, y_in)

	footprint = (~np.isnan(projected)).astype(float)
	return projected, footprint


def _pixel_scale(wcs: WCS) -> u.Quantity:
	celestial = wcs.celestial
	scales = [
		abs(scale) * unit
		for scale, unit in zip(
			proj_plane_pixel_scales(celestial),
			celestial.wcs.cunit,
		)
	]
	return min(scales)


def find_optimal_celestial_wcs(input_data, projection="TAN"):
	"""Determine a celestial WCS covering all supplied images."""
	entries = list(input_data)
	if not entries:
		raise ValueError("At least one image is required")

	frame = None
	corners = []
	references = []
	resolutions = []

	for shape, wcs in entries:
		shape = tuple(shape)
		if len(shape) != 2:
			raise ValueError(f"Input data is not 2-dimensional (got shape {shape!r})")

		wcs = _as_wcs(wcs)
		if not wcs.has_celestial:
			raise ValueError("Input WCS has no celestial components")

		if frame is None:
			frame = wcs_to_celestial_frame(wcs)

		ny, nx = shape
		xc = np.array([-0.5, nx - 0.5, nx - 0.5, -0.5])
		yc = np.array([-0.5, -0.5, ny - 0.5, ny - 0.5])
		corners.append(wcs.pixel_to_world(xc, yc).transform_to(frame).frame)

		xp, yp = wcs.wcs.crpix
		references.append(
			pixel_to_skycoord(xp, yp, wcs, origin=1).transform_to(frame).frame
		)
		resolutions.append(_pixel_scale(wcs))

	corners = SkyCoord(corners)
	references = SkyCoord(references)

	reference = SkyCoord(references.data.mean(), frame=references.frame).transform_to(frame)
	resolution = min(resolutions)

	wcs_final = celestial_frame_to_wcs(frame, projection=projection)
	if wcs_final.wcs.cunit[0] == "":
		wcs_final.wcs.cunit[0] = "deg"
	if wcs_final.wcs.cunit[1] == "":
		wcs_final.wcs.cunit[1] = "deg"

	rep = reference.represent_as("unitspherical")
	wcs_final.wcs.crval = (
		rep.lon.to_value(wcs_final.wcs.cunit[0]),
		rep.lat.to_value(wcs_final.wcs.cunit[1]),
	)
	wcs_final.wcs.cdelt = (
		-resolution.to_value(wcs_final.wcs.cunit[0]),
		resolution.to_value(wcs_final.wcs.cunit[1]),
	)

	wcs_final.wcs.crpix = (1, 1)
	xp, yp = skycoord_to_pixel(corners, wcs_final, origin=1)

	xmin, xmax = xp.min(), xp.max()
	ymin, ymax = yp.min(), yp.max()
	wcs_final.wcs.crpix = ((1 - xmin) + 0.5, (1 - ymin) + 0.5)

	shape_out = (
		int(round(ymax - ymin)),
		int(round(xmax - xmin)),
	)
	return wcs_final, shape_out


def reproject_and_coadd(
	input_data,
	output_projection,
	shape_out=None,
	combine_function="mean",
	blank_pixel_value=0,
):
	"""Resample several images onto a common WCS and combine them."""
	if combine_function not in ("mean", "sum", "first", "last", "min", "max"):
		raise ValueError(f"Unsupported combine function: {combine_function}")

	output_wcs = _as_wcs(output_projection)
	if shape_out is None:
		shape_out = output_wcs.array_shape
		if shape_out is None:
			raise ValueError("shape_out is required when the output WCS has no array shape")
	shape_out = tuple(int(size) for size in shape_out)

	if combine_function == "min":
		combined = np.full(shape_out, np.inf, dtype=float)
	elif combine_function == "max":
		combined = np.full(shape_out, -np.inf, dtype=float)
	else:
		combined = np.zeros(shape_out, dtype=float)
	footprint = np.zeros(shape_out, dtype=float)

	for data, wcs in input_data:
		array, coverage = reproject_interp((data, wcs), output_wcs, shape_out=shape_out)

		if combine_function in ("mean", "sum"):
			valid = coverage > 0
			combined[valid] += array[valid] * coverage[valid]
			footprint[valid] += coverage[valid]
		elif combine_function == "first":
			selected = (coverage > 0) & (footprint == 0)
			combined[selected] = array[selected]
			footprint[selected] = coverage[selected]
		elif combine_function == "last":
			selected = coverage > 0
			combined[selected] = array[selected]
			footprint[selected] = coverage[selected]
		else:
			selected = coverage > 0
			values = array[selected]
			if combine_function == "min":
				combined[selected] = np.minimum(combined[selected], values)
			else:
				combined[selected] = np.maximum(combined[selected], values)
			footprint[selected] += coverage[selected]

	if combine_function == "mean":
		np.divide(combined, footprint, out=combined, where=footprint != 0)

	combined[footprint == 0] = blank_pixel_value
	return combined, footprint


def stitch_images(fits_paths, output_path, hdu_index: int = 1) -> str:
	"""Create a PNG mosaic from local FITS files."""
	if len(fits_paths) < 2:
		raise ValueError("At least two FITS files are required")

	images = []
	for path in fits_paths:
		with fits.open(path) as hdul:
			hdu = hdul[hdu_index]
			if hdu.data is None or hdu.data.ndim != 2:
				raise ValueError(f"The selected HDU in {path} is not a 2D image")
			data = np.array(hdu.data, dtype=float, copy=True)
			wcs = WCS(hdu.header, fobj=hdul)
			if not wcs.has_celestial:
				raise ValueError(f"{path} has no usable celestial coordinate information")
			images.append((data, wcs.celestial))

	output_wcs, output_shape = find_optimal_celestial_wcs([(data.shape, wcs) for data, wcs in images])

	if output_shape[0] * output_shape[1] > 16_000_000:
		raise ValueError("The mosaic is too large. Use fewer or closer images.")

	mosaic, footprint = reproject_and_coadd(
		images,
		output_wcs,
		shape_out=output_shape,
		combine_function="mean",
	)

	valid = (footprint > 0) & np.isfinite(mosaic)
	if not valid.any():
		raise ValueError("The mosaic contains no valid pixels")

	low, high = np.percentile(mosaic[valid], [1, 99])
	if high <= low:
		raise ValueError("The valid pixels have insufficient variation for a preview")

	pixels = np.zeros(mosaic.shape, dtype=np.uint8)
	scaled = np.clip((mosaic[valid] - low) / (high - low), 0.0, 1.0)
	pixels[valid] = (scaled * 255).astype(np.uint8)

	out_path = Path(output_path)
	out_path.parent.mkdir(parents=True, exist_ok=True)
	Image.fromarray(np.flipud(pixels)).save(out_path, format="PNG")
	return str(out_path)


# ---------------------------------------------------------------------------
# IRSA SIA2 Client & Image Downloading
# ---------------------------------------------------------------------------

def _detector(bandpass: str) -> int:
	return int(bandpass.rsplit("D", 1)[1])


def _pair_bands(bands):
	"""Expand requested bandpass names to the short/long detector pairs they belong to.

	A colour tile always needs both a short- and a long-wavelength detector, so
	selecting a single bandpass (for example SPHEREx-D2) implicitly selects its
	partner (SPHEREx-D5) as well.
	"""
	bands = _as_list(bands)
	if not bands:
		return None
	names: list[str] = []
	for band in bands:
		band = _name(band, "band")
		if band not in BANDPASS_WAVELENGTHS:
			raise ValueError(f"unknown band {band}")
		detector = _detector(band)
		short = detector if detector <= 3 else detector - 3
		for wavelength_band in (f"SPHEREx-D{short}", f"SPHEREx-D{short + 3}"):
			if wavelength_band not in names:
				names.append(wavelength_band)
	return names


def _band_detectors(bands) -> tuple[int, int] | None:
	names = _pair_bands(bands)
	if not names:
		return None
	shorts = {
		detector if detector <= 3 else detector - 3
		for detector in (_detector(name) for name in names)
	}
	if len(shorts) != 1:
		raise ValueError("band must select a single short/long detector pair")
	short = shorts.pop()
	return short, short + 3


def _number(value, name: str) -> float:
	try:
		number = float(value)
	except (TypeError, ValueError):
		raise ValueError(f"{name} must be a number") from None
	if not math.isfinite(number):
		raise ValueError(f"{name} must be finite")
	return number


def _name(value, name: str) -> str:
	val_str = str(value)
	if not re.fullmatch(r"[A-Za-z0-9_.+\-]+", val_str):
		raise ValueError(f"{name} contains invalid characters")
	return val_str


def _as_list(value):
	if value is None:
		return None
	if isinstance(value, str):
		return [value]
	return list(value)


def build_query(
	ra: float,
	dec: float,
	*,
	start=None,
	end=None,
	bands=None,
	collections=None,
) -> dict:
	"""Build the SIA2 parameters used to find SPHEREx images."""
	params = {"pos": (_number(ra, "ra"), _number(dec, "dec"), SEARCH_RADIUS)}

	if start is not None or end is not None:
		start = None if start is None else _number(start, "start")
		end = None if end is None else _number(end, "end")
		if start is not None and end is not None and start > end:
			raise ValueError("start must not be after end")
		params["time"] = (
			Time(MJD_MIN if start is None else start, format="mjd"),
			Time(MJD_MAX if end is None else end, format="mjd"),
		)

	bands = _as_list(bands)
	if bands:
		bands = [_name(band, "band") for band in bands]
		if all(band in BANDPASS_WAVELENGTHS for band in bands):
			params["band"] = [
				tuple(value * u.micrometer for value in BANDPASS_WAVELENGTHS[band])
				for band in bands
			]

	collections = COLLECTIONS if collections is None else _as_list(collections)
	if collections:
		params["collection"] = [_name(col, "collection") for col in collections]

	return params


def _query(params: dict, *, bands=None, obs_id=None, maxrec: int | None = None, attempts: int = 3):
	for attempt in range(attempts):
		try:
			with _search_slots:
				rows = Irsa.query_sia(**params)
			break
		except Exception:
			if attempt == attempts - 1:
				raise
			time.sleep(3 * (attempt + 1))

	if bands:
		wanted = set(bands)
		rows = rows[[str(val) in wanted for val in rows["energy_bandpassname"]]]
	if obs_id is not None:
		obs_id = _name(obs_id, "obs_id")
		rows = rows[[str(val) == obs_id for val in rows["obs_id"]]]

	rows.sort("t_min")
	if maxrec is not None:
		rows = rows[:maxrec]
	return rows


def search_rows(
	ra: float,
	dec: float,
	*,
	start=None,
	end=None,
	bands=None,
	collections=None,
	obs_id=None,
	maxrec: int | None = None,
):
	params = build_query(
		ra,
		dec,
		start=start,
		end=end,
		bands=bands,
		collections=collections,
	)
	return _query(
		params,
		bands=_as_list(bands),
		obs_id=obs_id,
		maxrec=maxrec,
	)


def _cache_name(key: str, filters: dict) -> str:
	active = {k: v for k, v in filters.items() if v not in (None, [], ())}
	if not active:
		return f"{key}.json"
	digest = hashlib.sha1(json.dumps(active, sort_keys=True).encode()).hexdigest()[:12]
	return f"{key}-{digest}.json"


def _group_rows(rows) -> list[dict]:
	files: dict[str, dict[int, str]] = {}
	times: dict[str, float] = {}
	for row in rows:
		obs = str(row["obs_id"])
		try:
			detector = _detector(str(row["energy_bandpassname"]))
			mjd = float(row["t_min"])
		except (IndexError, TypeError, ValueError):
			continue
		url = str(row["access_url"])
		if not url or url == "--":
			continue

		files.setdefault(obs, {})[detector] = url
		times[obs] = mjd

	exposures = []
	for obs, dets in files.items():
		short = next((d for d in (1, 2, 3) if d in dets and d + 3 in dets), None)
		if short is None:
			continue
		exposures.append({
			"id": obs,
			"mjd": times[obs],
			"short": dets[short],
			"long": dets[short + 3],
			"detectors": [short, short + 3],
		})
	exposures.sort(key=lambda e: e["mjd"])
	return exposures


def search(
	ra: float,
	dec: float,
	key: str,
	*,
	start=None,
	end=None,
	bands=None,
	collections=None,
	obs_id=None,
) -> list[dict]:
	"""Find SPHEREx exposures covering a position, caching results to disk."""
	bands = _pair_bands(bands)
	filters = {
		"start": start,
		"end": end,
		"bands": bands,
		"collections": _as_list(collections),
		"obs_id": obs_id,
	}
	path = cache_path("search", _cache_name(key, filters))
	with key_lock(path):
		if os.path.exists(path):
			with open(path) as f:
				return json.load(f)

		rows = search_rows(
			ra,
			dec,
			start=start,
			end=end,
			bands=bands,
			collections=collections,
			obs_id=obs_id,
		)
		exposures = _group_rows(rows)

		tmp_path = f"{path}.tmp.{threading.get_ident()}"
		with open(tmp_path, "w") as f:
			json.dump(exposures, f)
		os.replace(tmp_path, path)
		return exposures


def cutout_url(
	ra: float,
	dec: float,
	size: float,
	bandpass: str,
	*,
	start=None,
	end=None,
	collections=None,
) -> str | None:
	rows = search_rows(
		ra,
		dec,
		start=start,
		end=end,
		bands=[bandpass],
		collections=collections,
		maxrec=1,
	)
	if len(rows) == 0:
		return None

	ra_num = _number(ra, "ra")
	dec_num = _number(dec, "dec")
	size_num = _number(size, "size")
	return f"{rows[0]['access_url']}?center={ra_num},{dec_num}d&size={size_num}"


def _download(url: str, attempts: int = 5) -> bytes:
	"""Download data from a URL with retries, backoff, and concurrency throttling."""
	for attempt in range(attempts):
		try:
			with _download_slots:
				with urllib.request.urlopen(url, context=_ssl_context, timeout=180) as response:
					return response.read()
		except urllib.error.HTTPError as e:
			if e.code not in (429, 502, 503, 504) or attempt == attempts - 1:
				raise
			retry_header = e.headers.get("Retry-After")
			try:
				delay = float(retry_header) if retry_header else 5.0
			except (ValueError, TypeError):
				delay = 5.0
			time.sleep(delay * (attempt + 1))
		except (urllib.error.URLError, TimeoutError):
			if attempt == attempts - 1:
				raise
			time.sleep(5 * (attempt + 1))
	raise RuntimeError("Download failed after maximum retries")


def cutout(url: str, ra: float, dec: float, size: float, key: str) -> fits.HDUList:
	"""Download and cache a slim FITS cutout containing only IMAGE and ZODI extensions."""
	path = cache_path("cutouts", f"{key}.fits")
	with key_lock(path):
		if not os.path.exists(path):
			raw = _download(f"{url}?center={ra},{dec}&size={size}")
			with fits.open(io.BytesIO(raw)) as h:
				slim = fits.HDUList([fits.PrimaryHDU(), h["IMAGE"].copy(), h["ZODI"].copy()])
				tmp_path = f"{path}.tmp.{threading.get_ident()}"
				slim.writeto(tmp_path, overwrite=True)
			os.replace(tmp_path, path)
	return fits.open(path)


# ---------------------------------------------------------------------------
# Tile Rendering
# ---------------------------------------------------------------------------

def _fill_holes(data: np.ndarray) -> np.ndarray:
	mask = np.isfinite(data)
	if mask.all():
		return data
	filled = np.where(mask, data, 0.0)
	weight = gaussian_filter(mask.astype(np.float32), 3)
	smooth = gaussian_filter(filled, 3) / np.maximum(weight, 1e-6)
	return np.where(mask, data, np.where(weight > 0.05, smooth, np.nan))


def _clip_cold(data: np.ndarray) -> np.ndarray:
	local = median_filter(np.nan_to_num(data), size=5)
	resid = data - local
	mad = np.nanmedian(np.abs(resid)) * 1.4826
	return np.where(resid < -5.0 * mad, local, data)


# Mask cache to avoid recalculating static cell geometry for every exposure
_cell_mask_cache: dict[str, np.ndarray] = {}
_cell_mask_guard = threading.Lock()


def get_cell_inside_mask(cell: Cell, target: WCS, shape: tuple[int, int]) -> np.ndarray:
	"""Retrieve or compute the dilated cell-boundary mask."""
	with _cell_mask_guard:
		mask = _cell_mask_cache.get(cell.id)
		if mask is not None:
			return mask

	ys, xs = np.indices(shape, dtype=float)
	ra, dec = target.pixel_to_world_values(xs, ys)
	inside = binary_dilation(cell.contains(ra, dec), iterations=2)

	with _cell_mask_guard:
		if len(_cell_mask_cache) > 512:
			_cell_mask_cache.pop(next(iter(_cell_mask_cache)))
		_cell_mask_cache[cell.id] = inside

	return inside


def _band(url: str, cell: Cell, exposure_id: str, detector: int, target: WCS, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
	ra, dec = cell.center
	size = math.hypot(cell.ra_width * math.cos(math.radians(dec)), CELL_DEG) * 1.1
	cache_key = f"{exposure_id}_D{detector}_{cell.id}"
	with cutout(url, ra, dec, size, cache_key) as h:
		image_data = h["IMAGE"].data.astype(np.float32)
		zodi_data = h["ZODI"].data.astype(np.float32)
		diff = image_data - zodi_data
		data = _clip_cold(_fill_holes(diff))
		projected, footprint = reproject_interp((data, WCS(h["IMAGE"].header)), target, shape_out=shape)
	return np.nan_to_num(projected), footprint > 0.5


def tile_path(cell: Cell, exposure_id: str, bands=None) -> str:
	"""Path to a rendered tile, including the detector pair when one is chosen."""
	detectors = _band_detectors(bands)
	suffix = f"_D{detectors[0]}D{detectors[1]}" if detectors else ""
	return cache_path("tiles", f"{exposure_id}_{cell.id}{suffix}.png")


def render_tile(cell: Cell, exposure: dict, bands=None) -> str:
	"""Render a colour tile for an observation and save as PNG."""
	path = tile_path(cell, exposure["id"], bands)
	with key_lock(path):
		if os.path.exists(path):
			return path

		header = cell.wcs_header()
		target = WCS(header)
		shape = (header["NAXIS2"], header["NAXIS1"])
		short_det, long_det = _band_detectors(bands) or exposure["detectors"]

		# Concurrently fetch and reproject both detectors
		with ThreadPoolExecutor(max_workers=2) as executor:
			fut_blue = executor.submit(_band, exposure["short"], cell, exposure["id"], short_det, target, shape)
			fut_red = executor.submit(_band, exposure["long"], cell, exposure["id"], long_det, target, shape)
			blue, blue_ok = fut_blue.result()
			red, red_ok = fut_red.result()

		valid = blue_ok & red_ok
		green = (blue + red) * 0.5
		rgb = make_lupton_rgb(red, green, blue, minimum=RGB_MIN, stretch=RGB_STRETCH, Q=RGB_Q)

		inside = get_cell_inside_mask(cell, target, shape)
		alpha = (valid & inside).astype(np.uint8) * 255

		image = Image.fromarray(np.dstack([rgb, alpha]), "RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
		tmp_path = f"{path}.tmp.{threading.get_ident()}"
		image.save(tmp_path, format="PNG")
		os.replace(tmp_path, path)
		return path


# ---------------------------------------------------------------------------
# Prewarming
# ---------------------------------------------------------------------------

def prewarm_tiles(
	ra: float = 304.693508808,
	dec: float = 42.4436872991,
	fov: float = 2.0,
	start: float | None = None,
	end: float | None = None,
	bands: list[str] | None = None,
	max_searches: int | None = None,
	max_downloads: int | None = None,
) -> None:
	"""Pre-render tiles in advance so the sky viewer loads instantly."""
	searches_limit = max_searches or MAX_SEARCHES
	downloads_limit = max_downloads or MAX_DOWNLOADS

	cells = cells_in_view(ra, dec, min(fov, 2.0))
	print(f"{len(cells)} cells")

	with ThreadPoolExecutor(max_workers=searches_limit) as pool:
		exposures_list = list(pool.map(
			lambda c: search(*c.center, c.id, start=start, end=end, bands=bands),
			cells,
		))
	exposures = dict(zip(cells, exposures_list))

	jobs = {(cell, es[-1]["id"]): (cell, es[-1]) for cell, es in exposures.items() if es}
	print(f"{len(jobs)} tiles")

	start_time = time.time()
	with ThreadPoolExecutor(max_workers=downloads_limit) as pool:
		futures = {pool.submit(render_tile, cell, exp, bands): (cell, exp["id"]) for cell, exp in jobs.values()}
		for done, future in enumerate(as_completed(futures), 1):
			cell, exposure_id = futures[future]
			try:
				future.result()
				status = "ok"
			except Exception as e:
				status = f"failed: {e}"
			elapsed = time.time() - start_time
			print(f"[{done}/{len(jobs)} {elapsed:.0f}s] {cell.id} {exposure_id} {status}", flush=True)


# ---------------------------------------------------------------------------
# Cutout Image Generation (load_pic)
# ---------------------------------------------------------------------------

def load_pic(
	x: float,
	y: float,
	r: float,
	bandpass: str,
	start: float | None = None,
	end: float | None = None,
) -> bytes:
	"""Fetch, render, cache and return a grayscale cutout image."""
	name = f"{x}.{y}.{r}"
	if start is not None or end is not None:
		name = f"{name}.{start}.{end}"

	safe_band = re.sub(r"[^A-Za-z0-9_.-]", "_", bandpass)
	img_dir = DATA_DIR / safe_band / "img"
	img_path = str(img_dir / f"{name}.png")

	with key_lock(img_path):
		if os.path.exists(img_path):
			with open(img_path, "rb") as f:
				return f.read()

		url = cutout_url(x, y, r, bandpass, start=start, end=end)
		if url is None:
			abort(404)

		raw = _download(url)
		with fits.open(io.BytesIO(raw)) as h:
			image = h["IMAGE"].data.astype(np.float32) - h["ZODI"].data.astype(np.float32)

		low, high = np.nanpercentile(image, [1, 99])
		scaled = np.clip((image - low) / max(high - low, 1e-6), 0.0, 1.0)
		img = Image.fromarray((scaled * 255).astype(np.uint8), "L")

		buf = io.BytesIO()
		img.save(buf, format="PNG")
		png_bytes = buf.getvalue()

		img_dir.mkdir(parents=True, exist_ok=True)
		tmp_path = f"{img_path}.tmp.{threading.get_ident()}"
		with open(tmp_path, "wb") as f:
			f.write(png_bytes)
		os.replace(tmp_path, img_path)

		return png_bytes


# ---------------------------------------------------------------------------
# Flask Application & Endpoints
# ---------------------------------------------------------------------------

app = Flask(__name__)


def soft_cast(cast_type, value, fallback):
	"""Safely cast value to cast_type, returning fallback on failure."""
	if value is None:
		return fallback
	try:
		return cast_type(value)
	except (ValueError, TypeError):
		return fallback


def list_arg(name: str) -> list[str] | None:
	"""Extract list argument values split by commas."""
	values = [v for raw in request.args.getlist(name) for v in raw.split(",") if v]
	return values or None


def cell_or_404(cell_id: str) -> Cell:
	try:
		return parse_cell(cell_id)
	except ValueError:
		abort(404)


@app.after_request
def allow_cors(response):
	response.headers["Access-Control-Allow-Origin"] = "*"
	return response


@app.get('/')
def hello_world():
	return 'hello world'


@app.get('/api/cells')
def get_cells():
	ra = soft_cast(float, request.args.get('ra'), None)
	dec = soft_cast(float, request.args.get('dec'), None)
	fov = min(soft_cast(float, request.args.get('fov'), 2.0), 2.0)
	if ra is None or dec is None:
		return {"error": "ra and dec are required"}, 400
	return {"cells": [{"id": c.id, "wcs": c.wcs_header(), "corners": c.corners} for c in cells_in_view(ra, dec, fov)]}


@app.get('/api/cells/<cell_id>/exposures')
def get_exposures(cell_id: str):
	cell = cell_or_404(cell_id)
	start = soft_cast(float, request.args.get('start'), None)
	end = soft_cast(float, request.args.get('end'), None)
	bands = list_arg('band')
	try:
		exposures = search(
			*cell.center,
			cell.id,
			start=start,
			end=end,
			bands=bands,
			collections=list_arg('collection'),
			obs_id=request.args.get('obs_id') or None,
		)
		result = [
			{"id": e["id"], "mjd": e["mjd"], "ready": os.path.exists(tile_path(cell, e["id"], bands))}
			for e in exposures
		]
	except ValueError as e:
		return {"error": str(e)}, 400
	return {"exposures": result}


@app.get('/api/cells/<cell_id>/tiles/<exposure_id>.png')
def get_tile(cell_id: str, exposure_id: str):
	cell = cell_or_404(cell_id)
	if not re.fullmatch(r"[A-Za-z0-9_.+\-]+", exposure_id):
		abort(404)

	bands = list_arg('band')
	try:
		# Fast path: check if tile is already rendered on disk
		cached_tile = tile_path(cell, exposure_id, bands)
		if os.path.exists(cached_tile):
			response = send_file(cached_tile, mimetype="image/png")
			response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
			return response

		# Slow path: find exposure and render on demand
		exposures = search(*cell.center, cell.id, bands=bands)
		exposure = next((e for e in exposures if e["id"] == exposure_id), None)
		if exposure is None:
			abort(404)
		rendered_tile = render_tile(cell, exposure, bands)
	except ValueError as e:
		return {"error": str(e)}, 400

	response = send_file(rendered_tile, mimetype="image/png")
	response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
	return response


@app.get('/api/getPic')
def get_pic():
	x = soft_cast(float, request.args.get('ra'), 0.0)
	y = soft_cast(float, request.args.get('dec'), 0.0)
	r = soft_cast(float, request.args.get("radius"), 0.1)
	band = soft_cast(str, request.args.get("band"), "SPHEREx-D2")
	start = soft_cast(float, request.args.get("start"), None)
	end = soft_cast(float, request.args.get("end"), None)

	try:
		png_bytes = load_pic(x, y, r, band, start=start, end=end)
		return png_bytes, 200, {"Content-Type": "image/png"}
	except ValueError as e:
		return {"error": str(e)}, 400


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main():
	parser = argparse.ArgumentParser(description="SPHEREx WebViewer Backend")
	parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="Host to bind server to")
	parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to bind server to")
	parser.add_argument("--prewarm", action="store_true", help="Prewarm tiles for faster initial load")
	parser.add_argument("--ra", type=float, default=304.693508808, help="Central RA in degrees for prewarming")
	parser.add_argument("--dec", type=float, default=42.4436872991, help="Central Dec in degrees for prewarming")
	parser.add_argument("--fov", type=float, default=2.0, help="Field of view in degrees for prewarming")
	parser.add_argument("--start", type=float, help="Earliest observation MJD")
	parser.add_argument("--end", type=float, help="Latest observation MJD")
	parser.add_argument("--band", action="append", help="Bandpass to include (repeatable)")
	parser.add_argument("--stitch", nargs="+", help="FITS file paths to stitch into a mosaic")
	parser.add_argument("-o", "--output", help="Output PNG path for stitched mosaic")
	parser.add_argument("--hdu-index", type=int, default=1, help="Image HDU index for stitching")

	# Support subcommands like 'prewarm' or 'stitch'
	raw_args = list(sys.argv[1:])
	if raw_args and raw_args[0] == "prewarm":
		raw_args.pop(0)
		raw_args.append("--prewarm")
	elif raw_args and raw_args[0] == "stitch":
		raw_args.pop(0)
		raw_args.insert(0, "--stitch")

	args = parser.parse_args(raw_args)

	if args.stitch:
		if not args.output:
			parser.error("--output (-o) is required when using --stitch")
		out = stitch_images(args.stitch, args.output, hdu_index=args.hdu_index)
		print(f"Mosaic created at: {out}")
		return

	is_prewarm = args.prewarm or any(
		a in sys.argv for a in ("--prewarm", "prewarm", "--start", "--end", "--band")
	)
	if is_prewarm and not any(a in sys.argv for a in ("--host", "--port")):
		prewarm_tiles(
			ra=args.ra,
			dec=args.dec,
			fov=args.fov,
			start=args.start,
			end=args.end,
			bands=args.band,
		)
		return

	app.run(host=args.host, port=args.port)


if __name__ == "__main__":
	main()
