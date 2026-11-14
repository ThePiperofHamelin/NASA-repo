from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

from reprojection import find_optimal_celestial_wcs, reproject_and_coadd


def stitch_images(fits_paths, output_path, hdu_index=1):
    """
    Create a PNG mosaic from local FITS files.

    Args:
        fits_paths: List of paths to downloaded FITS files.
        output_path: Path for the output PNG.
        hdu_index: Index of the image HDU to read. Defaults to 1.

    Returns:
        The path to the saved PNG.
    """
    if len(fits_paths) < 2:
        raise ValueError("At least two FITS files are required")

    images = []

    # 1. Read each image and its celestial coordinate information.
    for path in fits_paths:
        with fits.open(path) as hdul:
            hdu = hdul[hdu_index]

            if hdu.data is None or hdu.data.ndim != 2:
                raise ValueError(
                    f"The selected HDU in {path} is not a 2D image"
                )

            data = np.array(hdu.data, dtype=float, copy=True)
            wcs = WCS(hdu.header, fobj=hdul)

            if not wcs.has_celestial:
                raise ValueError(
                    f"{path} has no usable celestial coordinate information"
                )

            images.append((data, wcs.celestial))

    # 2. Define a common coordinate grid covering all input images.
    output_wcs, output_shape = find_optimal_celestial_wcs(
        [(data.shape, wcs) for data, wcs in images]
    )

    # Limit the output size for this prototype.
    if output_shape[0] * output_shape[1] > 16_000_000:
        raise ValueError(
            "The mosaic is too large. Use fewer or closer images."
        )

    # 3. Reproject and combine the images, averaging overlapping pixels.
    mosaic, footprint = reproject_and_coadd(
        images,
        output_wcs,
        shape_out=output_shape,
        combine_function="mean",
    )

    # 4. Identify finite pixels with observation coverage.
    valid = (footprint > 0) & np.isfinite(mosaic)

    if not valid.any():
        raise ValueError("The mosaic contains no valid pixels")

    # 5. Map the measured values to the 0–255 grayscale range.
    low, high = np.percentile(mosaic[valid], [1, 99])

    if high <= low:
        raise ValueError(
            "The valid pixels have insufficient variation for a preview"
        )

    pixels = np.zeros(mosaic.shape, dtype=np.uint8)
    scaled = np.clip(
        (mosaic[valid] - low) / (high - low),
        0,
        1,
    )
    pixels[valid] = (scaled * 255).astype(np.uint8)

    # 6. Flip vertically so that low FITS y coordinates appear at the bottom.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    Image.fromarray(np.flipud(pixels)).save(
        output_path,
        format="PNG",
    )

    return str(output_path)