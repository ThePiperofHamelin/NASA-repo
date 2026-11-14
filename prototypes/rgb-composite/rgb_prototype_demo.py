"""Synthetic/manual RGB composite demo for the NASA Space Apps project.

No SPHEREx data is included or implied. Run:
    python3 -m pip install numpy pillow
    python3 rgb_prototype_demo.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

OUTPUT = Path('rgb_demo_output')
OUTPUT.mkdir(exist_ok=True)

rng = np.random.default_rng(42)
size = 320
y, x = np.mgrid[0:size, 0:size]
channels = np.zeros((3, size, size), dtype=float)

# All channels share one set of star positions, but the intensity of each
# source is different in the three simulated wavelength bands.
for _ in range(65):
    cx, cy = rng.uniform(8, size - 8, size=2)
    sigma = rng.uniform(0.8, 2.0)
    star = np.exp(-((x - cx)**2 + (y - cy)**2) / (2 * sigma**2))
    brightness = rng.uniform(0.2, 1.2)
    band_strength = rng.uniform(0.2, 1.0, size=3)
    channels += brightness * band_strength[:, None, None] * star

# A diffuse, differently coloured feature makes channel mapping easier to see.
cloud = np.exp(-(((x - 205) / 63)**2 + ((y - 130) / 36)**2) / 2)
channels += np.array([0.14, 0.07, 0.23])[:, None, None] * cloud
channels += rng.normal(0, 0.003, size=channels.shape)


def stretch(data):
    """Simple visualization stretch; NOT a scientific flux calibration."""
    low, high = np.percentile(data, [1, 99.9])
    if high <= low:
        return np.zeros_like(data)
    return np.clip((data - low) / (high - low), 0, 1)


red, green, blue = (stretch(band) for band in channels)
for name, band in [('red', red), ('green', green), ('blue', blue)]:
    Image.fromarray((band * 255).astype(np.uint8)).save(OUTPUT / f'{name}_mock.png')

# Change these three values to manually adjust the RGB composition.
red_weight, green_weight, blue_weight = 1.0, 1.0, 1.0
rgb = np.stack([
    np.clip(red * red_weight, 0, 1),
    np.clip(green * green_weight, 0, 1),
    np.clip(blue * blue_weight, 0, 1),
], axis=-1)
Image.fromarray((rgb * 255).astype(np.uint8)).save(OUTPUT / 'rgb_composite_mock.png')

print(f'Done! Four demonstration images saved in: {OUTPUT.resolve()}')
print('NOTE: These are synthetic mock images, not actual SPHEREx observations.')
