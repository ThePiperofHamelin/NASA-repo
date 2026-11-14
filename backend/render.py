import math
import os

import numpy as np
from scipy.ndimage import binary_dilation, gaussian_filter, median_filter
from astropy.visualization import make_lupton_rgb
from astropy.wcs import WCS
from PIL import Image
from reproject import reproject_interp

import irsa
from grid import CELL_DEG, Cell

STRETCH = float(os.getenv("RGB_STRETCH", "1.5"))
Q = float(os.getenv("RGB_Q", "8"))
MINIMUM = float(os.getenv("RGB_MIN", "0"))


def _fill_holes(data: np.ndarray) -> np.ndarray:
	mask = np.isfinite(data)
	if mask.all():
		return data
	filled = np.where(mask, data, 0)
	weight = gaussian_filter(mask.astype(np.float32), 3)
	smooth = gaussian_filter(filled, 3) / np.maximum(weight, 1e-6)
	return np.where(mask, data, np.where(weight > 0.05, smooth, np.nan))


def _clip_cold(data: np.ndarray) -> np.ndarray:
	local = median_filter(np.nan_to_num(data), size=5)
	resid = data - local
	mad = np.nanmedian(np.abs(resid)) * 1.4826
	return np.where(resid < -5 * mad, local, data)


def _band(url: str, cell: Cell, exposure_id: str, detector: int, target: WCS, shape) -> np.ndarray:
	ra, dec = cell.center
	size = math.hypot(cell.ra_width * math.cos(math.radians(dec)), CELL_DEG) * 1.1
	with irsa.cutout(url, ra, dec, size, f"{exposure_id}_D{detector}_{cell.id}") as h:
		data = _clip_cold(_fill_holes(h["IMAGE"].data.astype(np.float32) - h["ZODI"].data.astype(np.float32)))
		projected, footprint = reproject_interp((data, WCS(h["IMAGE"].header)), target, shape_out=shape)
	return np.nan_to_num(projected), footprint > 0.5


def tile_path(cell: Cell, exposure_id: str) -> str:
	return irsa.cache_path("tiles", f"{exposure_id}_{cell.id}.png")


def render_tile(cell: Cell, exposure: dict) -> str:
	path = tile_path(cell, exposure["id"])
	with irsa.key_lock(path):
		if os.path.exists(path):
			return path

		header = cell.wcs_header()
		target = WCS(header)
		shape = (header["NAXIS2"], header["NAXIS1"])
		short_det, long_det = exposure["detectors"]
		blue, blue_ok = _band(exposure["short"], cell, exposure["id"], short_det, target, shape)
		red, red_ok = _band(exposure["long"], cell, exposure["id"], long_det, target, shape)

		valid = blue_ok & red_ok
		green = (blue + red) / 2
		rgb = make_lupton_rgb(red, green, blue, minimum=MINIMUM, stretch=STRETCH, Q=Q)

		ys, xs = np.mgrid[0:shape[0], 0:shape[1]]
		ra, dec = target.pixel_to_world_values(xs, ys)
		inside = binary_dilation(cell.contains(ra, dec), iterations=2)
		alpha = (valid & inside).astype(np.uint8) * 255

		image = Image.fromarray(np.dstack([rgb, alpha]), "RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
		image.save(path + ".tmp", format="PNG")
		os.replace(path + ".tmp", path)
		return path
