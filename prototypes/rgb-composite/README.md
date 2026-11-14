# Manual RGB Composite – Synthetic Prototype

A minimal RGB image composition demo for the team's NASA Space Apps SPHEREx browser concept.

**Important:** All images in this folder are **synthetic mock data**, not actual NASA/SPHEREx observations. No scientific inference should be made from them.

## Quick start

```bash
python3 -m pip install numpy pillow
python3 rgb_prototype_demo.py
```

The script writes the following files to `rgb_demo_output/`:

- `red_mock.png`, `green_mock.png`, `blue_mock.png`: three simulated image bands with aligned source positions.
- `rgb_composite_mock.png`: a false-colour composite made from those three bands.

Change `red_weight`, `green_weight`, and `blue_weight` in the script to adjust the relative brightness of each channel, then rerun the script.

## Next integration steps

Replace synthetic data with three real, astrometrically aligned wavelength-band images. Validate the FITS extensions, units, WCS and any reprojection before composing a real RGB image; shape matching alone is insufficient. Record waveband choices and processing settings. Any synthetic result must remain labelled as mock data.

Official SPHEREx data access: https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/
