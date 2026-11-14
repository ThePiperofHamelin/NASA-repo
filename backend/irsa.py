import hashlib
import io
import json
import math
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request

import certifi
from astropy.io import fits
from astropy.utils.data import conf
from astroquery.ipac.irsa import Irsa

conf.remote_timeout = 120

COLLECTIONS = ("spherex_dr1", "spherex_qr3")
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


def _number(value, name: str) -> float:
	try:
		number = float(value)
	except (TypeError, ValueError):
		raise ValueError(f"{name} must be a number") from None
	if not math.isfinite(number):
		raise ValueError(f"{name} must be finite")
	return number


def _sql_string(value, name: str) -> str:
	value = str(value)
	if not re.fullmatch(r"[A-Za-z0-9_.+\-]+", value):
		raise ValueError(f"{name} contains invalid characters")
	return f"'{value}'"


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
	obs_id=None,
) -> str:
	"""Build the ADQL query used to find SPHEREx images.

	`start` and `end` are Modified Julian Dates. They select images whose
	observation time overlaps the requested interval; either bound may be
	omitted. `bands` and `collections` accept a single value or a sequence.
	"""
	ra = _number(ra, "ra")
	dec = _number(dec, "dec")
	clauses = [f"CONTAINS(POINT('ICRS', {ra}, {dec}), s_region) = 1"]

	start = None if start is None else _number(start, "start")
	end = None if end is None else _number(end, "end")
	if start is not None and end is not None and start > end:
		raise ValueError("start must not be after end")
	if start is not None:
		clauses.append(f"t_max >= {start}")
	if end is not None:
		clauses.append(f"t_min <= {end}")

	bands = _as_list(bands)
	if bands:
		clauses.append("energy_bandpassname IN (" + ", ".join(_sql_string(band, "band") for band in bands) + ")")

	collections = COLLECTIONS if collections is None else _as_list(collections)
	if collections:
		clauses.append("obs_collection IN (" + ", ".join(_sql_string(collection, "collection") for collection in collections) + ")")

	if obs_id is not None:
		clauses.append(f"obs_id = {_sql_string(obs_id, 'obs_id')}")

	return f"""
SELECT obs_id, energy_bandpassname, access_url, t_min, t_max, obs_collection
FROM spherex.obscore
WHERE {' AND '.join(clauses)}
ORDER BY t_min
""".strip()


def _query(sql: str, maxrec: int | None = None, attempts: int = 3):
	for attempt in range(attempts):
		try:
			with _search_slots:
				kwargs = {"async_job": True}
				if maxrec is not None:
					kwargs["maxrec"] = maxrec
				return Irsa.query_tap(sql, **kwargs)
		except Exception:
			if attempt == attempts - 1:
				raise
			time.sleep(3 * (attempt + 1))


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
	query = build_query(
		ra,
		dec,
		start=start,
		end=end,
		bands=bands,
		collections=collections,
		obs_id=obs_id,
	)
	return _query(query, maxrec=maxrec)


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
	"""Find SPHEREx exposures covering a position.

	Optional filters are forwarded to the TAP query. `start` and `end` are
	MJD bounds, `bands` selects one or more `energy_bandpassname` values, and
	`collections` selects one or more `obs_collection` values.
	"""
	filters = {
		"start": start,
		"end": end,
		"bands": _as_list(bands),
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

		with open(path, "w") as f:
			json.dump(exposures, f)
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

	ra = _number(ra, "ra")
	dec = _number(dec, "dec")
	size = _number(size, "size")
	return f"{rows[0]['access_url']}?center={ra},{dec}d&size={size}"


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
