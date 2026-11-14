import matplotlib.pyplot as plt
import numpy as np
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
from flask import Flask, request
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

def load_pic(ra, dec):
    url = get_fits_url(ra, dec)
    fits_path = f"{tmpdir}/fits/{coord_to_path(ra, dec)}.fits"
    urllib.request.urlretrieve(url, fits_path)
    
    with fits.open(fits_path) as h:
        data = h[1].data

    img_path = f"{tmpdir}/img/{coord_to_path(ra, dec)}.png"
    img = Image.fromarray(data)
    img = img.convert('L')
    img.save(img_path)

@app.get('/api/getPic')
def get_pic():
    ra = float(request.args.get('ra'))
    dec = float(request.args.get('dec'))
    img_path = f"{tmpdir}/img/{coord_to_path(ra, dec)}.png"

    if os.path.exists(img_path):
        with open(img_path, 'rb') as h:
            return h.read()
    else:
        load_pic(ra, dec)
        with open(img_path) as h:
            return h.read()

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
