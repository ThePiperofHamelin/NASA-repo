from flask import Flask
import http.client
import time
import urllib.error

import numpy as np
import matplotlib.pyplot as plt

from astropy.io import fits
from astropy.wcs import WCS
from astropy.table import Table
from astropy import units as u
from astropy.coordinates import SkyCoord

from astroquery.ipac.irsa import Irsa

#from firefly_client import FireflyClient

import matplotlib.pyplot as plt
import numpy as np

# The time it takes to read SPHEREx files can exceed
# astropy's default timeout limit. Increase it.
from astropy.utils.data import conf
conf.remote_timeout = 120

# ra_deg = 304.693508808
# dec_deg = 42.4436872991

# coord = SkyCoord(ra_deg, dec_deg, unit='deg')
# search_radius = 1 * u.arcsec
# results = Irsa.query_sia(pos=(coord, search_radius), collection=['spherex_dr1', 'spherex_qr3'])


ra_deg = 304.693508808
dec_deg = 42.4436872991

coord = SkyCoord(ra_deg, dec_deg, unit="deg")
search_radius = 1 * u.arcsec

# search for all images covering this location
results = Irsa.query_sia(
    pos=(coord, search_radius),
    collection=["spherex_dr1", "spherex_qr3"],
)

print("number of found images", len(results))

if len(results) == 0:
    print("nothing found at this location")
else:
    # fetch the url
    url = results["access_url"][0]
    print("reading:", url)

    # fetch FITS from website
    with fits.open(url) as h:
        data = h[1].data.copy()

    plt.imsave("test.png", data, cmap="gray")
    print("saved test.png")
# app = Flask(__name__)

# @app.get('/')
# def hello_world():
    # return 'hello world'

# app.run(port=8000)
