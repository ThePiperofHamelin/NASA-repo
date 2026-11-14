import math

CELL_DEG = 1.0
PIXEL_DEG = 6.15 / 3600
ROWS = round(180 / CELL_DEG)


def row_count(j: int) -> int:
	dec_c = -90 + (j + 0.5) * CELL_DEG
	return max(1, math.floor(360 * math.cos(math.radians(dec_c)) / CELL_DEG))


class Cell:
	def __init__(self, i: int, j: int):
		self.i = i
		self.j = j
		self.id = f"{i}_{j}"
		self.ra_width = 360 / row_count(j)
		self.dec0 = -90 + j * CELL_DEG
		self.ra0 = i * self.ra_width
		self.center = (self.ra0 + self.ra_width / 2, self.dec0 + CELL_DEG / 2)
		ra1, dec1 = self.ra0 + self.ra_width, self.dec0 + CELL_DEG
		self.corners = [(self.ra0, self.dec0), (ra1, self.dec0), (ra1, dec1), (self.ra0, dec1)]

	def contains(self, ra, dec):
		return ((ra - self.ra0) % 360 < self.ra_width) & (dec >= self.dec0) & (dec < self.dec0 + CELL_DEG)

	def wcs_header(self) -> dict:
		dec1 = self.dec0 + CELL_DEG
		widest_dec = 0 if self.dec0 <= 0 <= dec1 else min(abs(self.dec0), abs(dec1))
		side = max(self.ra_width * math.cos(math.radians(widest_dec)), CELL_DEG) * 1.05
		n = math.ceil(side / PIXEL_DEG)
		ra, dec = self.center
		return {
			"NAXIS": 2,
			"NAXIS1": n,
			"NAXIS2": n,
			"CTYPE1": "RA---TAN",
			"CTYPE2": "DEC--TAN",
			"CUNIT1": "deg",
			"CUNIT2": "deg",
			"CRVAL1": ra,
			"CRVAL2": dec,
			"CRPIX1": (n + 1) / 2,
			"CRPIX2": (n + 1) / 2,
			"CDELT1": -PIXEL_DEG,
			"CDELT2": PIXEL_DEG,
		}


def parse_cell(cell_id: str) -> Cell:
	i, j = (int(x) for x in cell_id.split("_"))
	if not 0 <= j < ROWS or not 0 <= i < row_count(j):
		raise ValueError(cell_id)
	return Cell(i, j)


def cell_at(ra: float, dec: float) -> Cell:
	j = min(ROWS - 1, max(0, math.floor((dec + 90) / CELL_DEG)))
	n = row_count(j)
	return Cell(math.floor((ra % 360) / (360 / n)) % n, j)


def angular_sep(ra1, dec1, ra2, dec2) -> float:
	r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
	c = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
	return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def cells_in_view(ra: float, dec: float, fov: float) -> list[Cell]:
	radius = fov * 0.75
	reach = radius + CELL_DEG
	j_lo = max(0, math.floor((dec - reach + 90) / CELL_DEG))
	j_hi = min(ROWS - 1, math.floor((dec + reach + 90) / CELL_DEG))
	cells = []
	for j in range(j_lo, j_hi + 1):
		n = row_count(j)
		w = 360 / n
		dec_c = -90 + (j + 0.5) * CELL_DEG
		cos_d = max(math.cos(math.radians(dec_c)), 1e-6)
		span = min(180, reach / cos_d + w)
		i_lo = math.floor((ra - span) / w)
		i_hi = math.floor((ra + span) / w)
		seen = set()
		for k in range(i_lo, i_hi + 1):
			i = k % n
			if i in seen:
				continue
			seen.add(i)
			cell = Cell(i, j)
			cra, cdec = cell.center
			half_diag = math.hypot(w * cos_d, CELL_DEG) / 2
			if angular_sep(ra, dec, cra, cdec) <= radius + half_diag:
				cells.append(cell)
	return cells
