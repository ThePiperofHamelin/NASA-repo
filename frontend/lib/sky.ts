export const DEFAULT_TARGET = { ra: 304.693508808, dec: 42.4436872991 };
export const MAX_FOV = 2;

export type Wcs = Record<string, string | number>;
export type Cell = { id: string; wcs: Wcs; corners: [number, number][] };
export type Exposure = { id: string; mjd: number; ready: boolean };

export async function fetchCells(ra: number, dec: number, fov: number, signal?: AbortSignal) {
  const res = await fetch(`/api/cells?ra=${ra}&dec=${dec}&fov=${fov}`, { signal });
  if (!res.ok) throw new Error(`cells ${res.status}`);
  return ((await res.json()) as { cells: Cell[] }).cells;
}

export async function fetchExposures(cellId: string) {
  const res = await fetch(`/api/cells/${cellId}/exposures`);
  if (!res.ok) throw new Error(`exposures ${res.status}`);
  return ((await res.json()) as { exposures: Exposure[] }).exposures;
}

export const tileUrl = (cellId: string, exposureId: string) =>
  `/api/cells/${cellId}/tiles/${exposureId}.png`;
