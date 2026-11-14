import io
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

import certifi
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.utils.data import conf
from astroquery.ipac.irsa import Irsa

conf.remote_timeout = 120

COLLECTIONS = ["spherex_dr1", "spherex_qr3"]
CACHE_DIR = os.getenv("CACHE_DIR", os.path.join(os.path.dirname(__file__), ".cache"))
MAX_DOWNLOADS = int(os.getenv("IRSA_DOWNLOADS", "3"))
MAX_SEARCHES = int(os.getenv("IRSA_SEARCHES", "3"))

_ssl = ssl.create_default_context(cafile=certifi.where())
_download_slots = threading.BoundedSemaphore(MAX_DOWNLOADS)
_search_slots = threading.BoundedSemaphore(MAX_SEARCHES)
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def cache_path(*parts: str) -> str:
	path = os.path.join(CACHE_DIR, *parts)
	os.makedirs(os.path.dirname(path), exist_ok=True)
	return path


def key_lock(key: str) -> threading.Lock:
	with _locks_guard:
		return _locks.setdefault(key, threading.Lock())


def _detector(bandpass: str) -> int:
	return int(bandpass.rsplit("D", 1)[1])


def _query(ra: float, dec: float, attempts: int = 3):
	for attempt in range(attempts):
		try:
			with _search_slots:
				return Irsa.query_sia(pos=(SkyCoord(ra, dec, unit="deg"), 1 * u.arcsec), collection=COLLECTIONS)
		except Exception:
			if attempt == attempts - 1:
				raise
			time.sleep(3 * (attempt + 1))


def search(ra: float, dec: float, key: str) -> list[dict]:
	path = cache_path("search", f"{key}.json")
	with key_lock(path):
		if os.path.exists(path):
			with open(path) as f:
				return json.load(f)

		rows = _query(ra, dec)

		files: dict[str, dict[int, str]] = {}
		times: dict[str, float] = {}
		for row in rows:
			obs = str(row["obs_id"])
			files.setdefault(obs, {})[_detector(str(row["energy_bandpassname"]))] = str(row["access_url"])
			times[obs] = float(row["t_min"])

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

		with open(path, "w") as f:
			json.dump(exposures, f)
		return exposures


def _download(url: str, attempts: int = 5) -> bytes:
	for attempt in range(attempts):
		try:
			with _download_slots:
				with urllib.request.urlopen(url, context=_ssl, timeout=180) as response:
					return response.read()
		except urllib.error.HTTPError as e:
			if e.code not in (429, 502, 503, 504) or attempt == attempts - 1:
				raise
			time.sleep(float(e.headers.get("Retry-After") or 5) * (attempt + 1))
		except (urllib.error.URLError, TimeoutError):
			if attempt == attempts - 1:
				raise
			time.sleep(5 * (attempt + 1))
	raise RuntimeError("unreachable")


def cutout(url: str, ra: float, dec: float, size: float, key: str) -> fits.HDUList:
	path = cache_path("cutouts", f"{key}.fits")
	with key_lock(path):
		if not os.path.exists(path):
			raw = _download(f"{url}?center={ra},{dec}&size={size}")
			with fits.open(io.BytesIO(raw)) as h:
				slim = fits.HDUList([fits.PrimaryHDU(), h["IMAGE"].copy(), h["ZODI"].copy()])
				slim.writeto(path + ".tmp", overwrite=True)
			os.replace(path + ".tmp", path)
	return fits.open(path)
