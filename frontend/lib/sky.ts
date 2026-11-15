export const DEFAULT_TARGET = { ra: 304.693508808, dec: 42.4436872991 };
export const MAX_FOV = 2;

export type RGBSettings = {
  r_weight: number;
  g_weight: number;
  b_weight: number;
  brightness: number;
};

export const DEFAULT_RGB: RGBSettings = {
  r_weight: 1,
  g_weight: 1,
  b_weight: 1,
  brightness: 1,
};

export const rgbKey = (rgb: RGBSettings) =>
  [rgb.r_weight, rgb.g_weight, rgb.b_weight, rgb.brightness].join(',');

const MJD_EPOCH = 40587;

export type Wcs = Record<string, string | number>;
export type Cell = { id: string; wcs: Wcs; corners: [number, number][] };
export type Exposure = { id: string; mjd: number; ready: boolean };

export type ObservationFilters = {
  /** Earliest observation time in Modified Julian Date. */
  start: number | null;
  /** Latest observation time in Modified Julian Date. */
  end: number | null;
  /** Bandpasses used to select the short/long detector pair. */
  bands: string[] | null;
};

export const DEFAULT_FILTERS: ObservationFilters = {
  start: null,
  end: null,
  bands: null,
};

export const BAND_OPTIONS = [
  {
    value: 'auto',
    label: 'Any available pair',
    detail: 'Automatic detector pairing',
    bands: null,
  },
  {
    value: 'D1+D4',
    label: 'D1 + D4',
    detail: '0.75 – 3.82 µm',
    bands: ['SPHEREx-D1', 'SPHEREx-D4'],
  },
  {
    value: 'D2+D5',
    label: 'D2 + D5',
    detail: '1.10 – 4.41 µm',
    bands: ['SPHEREx-D2', 'SPHEREx-D5'],
  },
  {
    value: 'D3+D6',
    label: 'D3 + D6',
    detail: '1.63 – 5.00 µm',
    bands: ['SPHEREx-D3', 'SPHEREx-D6'],
  },
] as const;

export const dateToMjd = (date: Date) =>
  date.getTime() / 86400000 + MJD_EPOCH;

export const mjdToDate = (mjd: number) =>
  new Date((mjd - MJD_EPOCH) * 86400000);

/** Format an MJD as a value accepted by datetime-local. */
export const mjdToInputValue = (mjd: number) =>
  mjdToDate(mjd).toISOString().slice(0, 16);

/** Parse a datetime-local value as UTC and return its MJD. */
export const inputValueToMjd = (value: string): number | null => {
  if (!value) return null;
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : dateToMjd(date);
};

const filtersToParams = (filters: ObservationFilters) => {
  const params = new URLSearchParams();
  if (filters.start != null) params.set('start', String(filters.start));
  if (filters.end != null) params.set('end', String(filters.end));
  if (filters.bands?.length) params.set('band', filters.bands.join(','));
  return params;
};

export async function fetchCells(
  ra: number,
  dec: number,
  fov: number,
  signal?: AbortSignal,
) {
  const res = await fetch(
    `/api/cells?ra=${ra}&dec=${dec}&fov=${fov}`,
    { signal },
  );
  if (!res.ok) throw new Error(`cells ${res.status}`);
  return ((await res.json()) as { cells: Cell[] }).cells;
}

export async function fetchExposures(
  cellId: string,
  filters: ObservationFilters = DEFAULT_FILTERS,
  signal?: AbortSignal,
) {
  const query = filtersToParams(filters).toString();
  const res = await fetch(
    `/api/cells/${cellId}/exposures${query ? `?${query}` : ''}`,
    { signal },
  );
  if (!res.ok) throw new Error(`exposures ${res.status}`);
  return ((await res.json()) as { exposures: Exposure[] }).exposures;
}

export const tileUrl = (
  cellId: string,
  exposureId: string,
  filters: ObservationFilters = DEFAULT_FILTERS,
  rgb: RGBSettings = DEFAULT_RGB,
) => {
  const params = new URLSearchParams();

  if (filters.bands?.length) {
    params.set('band', filters.bands.join(','));
  }

  params.set('r_weight', String(rgb.r_weight));
  params.set('g_weight', String(rgb.g_weight));
  params.set('b_weight', String(rgb.b_weight));
  params.set('brightness', String(rgb.brightness));
  params.set('render_version', 'rgb-v2');

  const query = params.toString();
  return `/api/cells/${cellId}/tiles/${exposureId}.png${query ? `?${query}` : ''}`;
};