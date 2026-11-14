import matplotlib.pyplot as plt
import numpy as np
import ssl
import certifi
import shutil
import urllib.request
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
from flask import Flask, request, send_file
from PIL import Image
import tempfile
import urllib
import os

conf.remote_timeout = 120

app = Flask(__name__)

if os.getenv('TMPDIR') != None:
	tmpdir = os.getenv('TMPDIR')
else:
	tmpdir = tempfile.mkdtemp()

def get_fits_url(ra_deg, dec_deg):
	coord = SkyCoord(ra_deg, dec_deg, unit='deg')
	search_radius = 1 * u.arcsec
	results = Irsa.query_sia(pos=(coord, search_radius), collection=['spherex_dr1', 'spherex_qr3'])
	return results['access_url'][0]

def coord_to_path(ra_deg, dec_deg):
	return f"{ra_deg}-{dec_deg}".replace('.', '-')

def load_pic(ra: float, dec: float, n: int):
    url = get_fits_url(ra, dec)
    coord = coord_to_path(ra, dec)
    img_path = f"{tmpdir}/img/{coord}.png"

    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            return f.read()

    fits_path = f"{tmpdir}/fits/{coord}.fits"

    if not os.path.exists(fits_path):
        # download FITS using certifi
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(
            url, context=context, timeout=120
        ) as response:
            with open(fits_path, "wb") as output:
                shutil.copyfileobj(response, output)

    with fits.open(fits_path) as h:
        data = h[n].data

    img = Image.fromarray(data)
    img = img.convert("L")
    img.save(img_path, format="PNG")

    with open(img_path, "rb") as f:
        return f.read()


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
	n = soft_cast(int, request.args.get("n"), 0)
	ra = soft_cast(float, request.args.get('ra'), 0)
	dec = soft_cast(float, request.args.get('dec'), 0)

	return load_pic(ra, dec, n), 200, { "Content-Type": "image/png" }

@app.get('/')
def hello_world():
	return 'hello world'

if __name__ == '__main__':
	print(f"tmp directory is {tmpdir}")
	if not os.path.exists(f"{tmpdir}/fits"):
		os.mkdir(f"{tmpdir}/fits")
	if not os.path.exists(f"{tmpdir}/img"):
		os.mkdir(f"{tmpdir}/img")

	app.run(port=8000)
