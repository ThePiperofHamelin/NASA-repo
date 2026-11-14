import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import grid
import irsa
import render


def main():
	parser = argparse.ArgumentParser(description="Render tiles ahead of time so the viewer loads instantly.")
	parser.add_argument("--ra", type=float, default=304.693508808)
	parser.add_argument("--dec", type=float, default=42.4436872991)
	parser.add_argument("--fov", type=float, default=2.0)
	args = parser.parse_args()

	cells = grid.cells_in_view(args.ra, args.dec, min(args.fov, 2.0))
	print(f"{len(cells)} cells")
	with ThreadPoolExecutor(irsa.MAX_SEARCHES) as pool:
		exposures = dict(zip(cells, pool.map(lambda c: irsa.search(*c.center, c.id), cells)))

	jobs = {(cell, es[-1]["id"]): (cell, es[-1]) for cell, es in exposures.items() if es}
	print(f"{len(jobs)} tiles")

	start = time.time()
	with ThreadPoolExecutor(irsa.MAX_DOWNLOADS) as pool:
		futures = {pool.submit(render.render_tile, cell, exposure): key for key, (cell, exposure) in jobs.items()}
		for done, future in enumerate(as_completed(futures), 1):
			cell, exposure_id = futures[future]
			try:
				future.result()
				status = "ok"
			except Exception as e:
				status = f"failed: {e}"
			print(f"[{done}/{len(jobs)} {time.time() - start:.0f}s] {cell.id} {exposure_id} {status}", flush=True)


if __name__ == "__main__":
	main()
