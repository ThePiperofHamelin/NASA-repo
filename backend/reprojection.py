"""Small WCS reprojection helpers built on astropy and numpy.

This module implements the subset of the ``reproject`` package that the backend
needs. Images are resampled with bilinear interpolation on the celestial grid,
and mosaics are built by averaging the resampled images.
"""

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from astropy.wcs.utils import (
	celestial_frame_to_wcs,
	pixel_to_pixel,
	pixel_to_skycoord,
	proj_plane_pixel_scales,
	skycoord_to_pixel,
	wcs_to_celestial_frame,
)

__all__ = [
	"find_optimal_celestial_wcs",
	"reproject_and_coadd",
	"reproject_interp",
]

# Transform output pixels in bounded chunks to keep temporary arrays small.
_CHUNK_SIZE = 1_000_000


def _as_wcs(projection) -> WCS:
	if isinstance(projection, WCS):
		return projection
	return WCS(projection)


def _bilinear_sample(data: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
	"""Sample a 2D array at fractional pixel coordinates."""
	height, width = data.shape
	values = np.full(x.shape, np.nan, dtype=float)
	# Pixels are defined at their centres, so the outer half of the first and
	# last pixels is still covered by the image.
	inside = (
		(x >= -0.5)
		& (x <= width - 0.5)
		& (y >= -0.5)
		& (y <= height - 0.5)
	)

	if not inside.any():
		return values

	# Clip coordinates in the outer half-pixel to the centre of the nearest
	# pixel, which is what the interpolation is defined for.
	xs = np.clip(x[inside], 0, width - 1)
	ys = np.clip(y[inside], 0, height - 1)

	if width < 2 or height < 2:
		# There is no pair of neighbouring pixels to interpolate between.
		xi = np.clip(np.rint(xs), 0, width - 1).astype(np.intp)
		yi = np.clip(np.rint(ys), 0, height - 1).astype(np.intp)
		values[inside] = data[yi, xi]
		return values

	x0 = np.floor(xs).astype(np.intp)
	y0 = np.floor(ys).astype(np.intp)

	# Pixels exactly on the right or bottom edge have their second neighbour
	# just outside the array. Clamping the index and letting the weight reach
	# one gives the same result as sampling the edge pixel directly.
	np.clip(x0, 0, width - 2, out=x0)
	np.clip(y0, 0, height - 2, out=y0)

	dx = xs - x0
	dy = ys - y0

	top = data[y0, x0] * (1 - dx) + data[y0, x0 + 1] * dx
	bottom = data[y0 + 1, x0] * (1 - dx) + data[y0 + 1, x0 + 1] * dx
	values[inside] = top * (1 - dy) + bottom * dy

	return values


def reproject_interp(input_data, output_projection, shape_out=None):
	"""Resample a 2D image onto another celestial WCS.

	Args:
		input_data: Tuple of ``(data, input_wcs)``.
		output_projection: Output WCS, header or dictionary.
		shape_out: Output array shape as ``(rows, columns)``.

	Returns:
		Tuple of ``(array, footprint)``. The array is NaN outside the input
		image and the footprint is 1 where the array has a valid value.
	"""
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
		ys, xs = np.mgrid[start:stop, 0:n_cols]
		x_in, y_in = pixel_to_pixel(
			output_wcs,
			input_wcs,
			xs.astype(float),
			ys.astype(float),
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
	"""Determine a celestial WCS that covers all the supplied images.

	Args:
		input_data: Iterable of ``(shape, wcs)`` pairs.
		projection: FITS projection code for the output WCS.

	Returns:
		Tuple of ``(wcs, shape)`` for the combined image.
	"""
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

	reference = SkyCoord(references.data.mean(), frame=references.frame)
	reference = reference.transform_to(frame)
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

	# Find where all the input corners fall, then shift the reference pixel so
	# that the mosaic starts at the bottom left.
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
	"""Resample several images onto a common WCS and combine them.

	Args:
		input_data: Iterable of ``(data, wcs)`` pairs.
		output_projection: Output WCS, header or dictionary.
		shape_out: Output array shape as ``(rows, columns)``.
		combine_function: One of ``mean``, ``sum``, ``first``, ``last``,
			``min`` or ``max``.
		blank_pixel_value: Value used where no input image has coverage.

	Returns:
		Tuple of ``(array, footprint)`` for the combined image.
	"""
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
