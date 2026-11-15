'use client';

import type { Aladin, Overlay } from 'aladin-lite';
import { useEffect, useRef } from 'react';
import {
  type Cell,
  type Exposure,
  type ObservationFilters,
  type RGBSettings,
  rgbKey,
  DEFAULT_TARGET,
  MAX_FOV,
  fetchCells,
  fetchExposures,
  tileUrl,
} from '@/lib/sky';

type AladinModule = typeof import('aladin-lite').default;

type Props = {
  target: { ra: number; dec: number; key: number };
  filters: ObservationFilters;
  rgb: RGBSettings;
  onLoadingChange: (count: number) => void;
  onMetadataChange?: (metadata: {
    ra: number;
    dec: number;
    observationMjd: number | null;
  }) => void;
};

const FADE_MS = 300;
const MAX_TILE_FETCHES = 3;

async function fetchBlob(url: string, signal: AbortSignal) {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(url, { signal });
      if (!res.ok) throw new Error(`tile ${res.status}`);
      return URL.createObjectURL(await res.blob());
    } catch (err) {
      if (signal.aborted || attempt >= 1) throw err;
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

export function SkyViewer({
  target,
  filters,
  rgb,
  onLoadingChange,
  onMetadataChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const engine = useRef<ReturnType<typeof createEngine> | null>(null);
  const filtersRef = useRef(filters);
  const rgbRef = useRef(rgb);
  const callbacks = useRef({ onLoadingChange, onMetadataChange });

  useEffect(() => {
    callbacks.current = { onLoadingChange, onMetadataChange };
  });

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  useEffect(() => {
    rgbRef.current = rgb;
  }, [rgb]);

  useEffect(() => {
    let disposed = false;

    import('aladin-lite').then(async ({ default: A }) => {
      await A.init;

      if (disposed || !containerRef.current) return;

      engine.current = createEngine(
        A,
        containerRef.current,
        callbacks,
        filtersRef.current,
        rgbRef.current,
      );
    });

    return () => {
      disposed = true;
      engine.current?.dispose();
      engine.current = null;
    };
  }, []);

  useEffect(() => {
    if (target.key > 0) {
      engine.current?.goto(target.ra, target.dec);
    }
  }, [target]);

  useEffect(() => {
    engine.current?.setFilters(filters);
  }, [filters]);

  useEffect(() => {
    engine.current?.setRgb(rgb);
  }, [rgb]);

  return (
    <div className="absolute inset-0 bg-black">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

function createEngine(
  A: AladinModule,
  container: HTMLElement,
  callbacks: {
    current: Pick<Props, 'onLoadingChange' | 'onMetadataChange'>;
  },
  initialFilters: ObservationFilters,
  initialRgb: RGBSettings,
) {
  const aladin: Aladin = A.aladin(container, {
    target: `${DEFAULT_TARGET.ra} ${DEFAULT_TARGET.dec}`,
    fov: 1.5,
    survey: [],
    backgroundColor: 'rgb(0, 0, 0)',
    showLayersControl: false,
    showProjectionControl: false,
    showFullscreenControl: false,
    showFrame: false,
    showCooLocation: false,
    showReticle: false,
    log: false,
  });

  aladin.setFoVRange(0.05, MAX_FOV);

  const outlines: Overlay = A.graphicOverlay({
    color: '#94a3b8',
    lineWidth: 1,
    lineDash: [4, 4],
  });

  aladin.addOverlay(outlines);

  let cells: Cell[] = [];

  const exposures = new Map<string, Exposure[]>();
  const exposureRequests = new Map<string, Promise<void>>();
  const blobs = new Map<string, string>();
  const shown = new Map<string, string>();
  const layers = new Map<string, string>();

  const queued = new Map<
    string,
    { cell: Cell; exposure: Exposure }
  >();

  const active = new Map<
    string,
    { exposureId: string; controller: AbortController }
  >();

  let viewAbort: AbortController | null = null;
  let viewTimer: ReturnType<typeof setTimeout> | undefined;
  let filters = initialFilters;
  let rgb = initialRgb;
  let disposed = false;
  let filtersVersion = 0;

  const variant = () =>
    `${filters.bands?.join(',') ?? 'auto'}|${rgbKey(rgb)}`;

  const cacheKey = (cellId: string, exposureId: string) =>
    `${cellId}/${exposureId}/${variant()}`;

  const publishMetadata = (includeExposure = true) => {
    if (disposed) return;

    const [ra, dec] = aladin.getRaDec();
    let observationMjd: number | null = null;
    let closestDistance = Infinity;

    if (includeExposure) {
      for (const cell of cells) {
        const exposure = exposures.get(cell.id)?.at(-1);
        if (!exposure) continue;

        const deltaRa =
          (((Number(cell.wcs.CRVAL1) - ra + 540) % 360) - 180) *
          Math.cos((dec * Math.PI) / 180);

        const deltaDec = Number(cell.wcs.CRVAL2) - dec;
        const distance = Math.hypot(deltaRa, deltaDec);

        if (distance < closestDistance) {
          closestDistance = distance;
          observationMjd = exposure.mjd;
        }
      }
    }

    callbacks.current.onMetadataChange?.({
      ra,
      dec,
      observationMjd,
    });
  };

  const drawOutlines = () => {
    if (disposed) return;

    outlines.removeAll();

    const loading = cells.filter(
      (c) => queued.has(c.id) || active.has(c.id),
    );

    outlines.addFootprints(
      loading.map((c) => A.polygon(c.corners)),
    );

    callbacks.current.onLoadingChange(loading.length);
  };

  const fadeIn = (
    cellId: string,
    name: string,
    layer: ReturnType<AladinModule['image']>,
  ) => {
    const start = performance.now();

    const step = (now: number) => {
      if (disposed || layers.get(cellId) !== name) return;

      const t = Math.min(1, (now - start) / FADE_MS);
      layer.setOpacity(t);

      if (t < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  };

  const show = (
    cell: Cell,
    exposure: Exposure,
    url: string,
  ) => {
    if (disposed) return;

    const name = `${cell.id}|${exposure.id}|${variant()}`;
    const previous = layers.get(cell.id);

    if (previous === name) return;

    layers.set(cell.id, name);

    const layer = A.image(url, {
      name,
      wcs: cell.wcs,
      imgFormat: 'png',
      opacity: 0,
      successCallback: () => {
        fadeIn(cell.id, name, layer);

        if (previous) {
          setTimeout(() => {
            if (!disposed && layers.get(cell.id) !== previous) {
              aladin.removeImageLayer(previous);
            }
          }, FADE_MS);
        }
      },
    });

    aladin.setOverlayImageLayer(layer, name);
  };

  const priority = ({
    cell,
    exposure,
  }: {
    cell: Cell;
    exposure: Exposure;
  }) => {
    const [ra, dec] = aladin.getRaDec();

    const dRa =
      (((Number(cell.wcs.CRVAL1) - ra + 540) % 360) - 180) *
      Math.cos((dec * Math.PI) / 180);

    const distance = Math.hypot(
      dRa,
      Number(cell.wcs.CRVAL2) - dec,
    );

    return (exposure.ready ? 0 : 1000) + distance;
  };

  const pump = () => {
    if (disposed) return;

    while (active.size < MAX_TILE_FETCHES && queued.size > 0) {
      const next = [...queued.values()].reduce((a, b) =>
        priority(b) < priority(a) ? b : a,
      );

      queued.delete(next.cell.id);
      fetchTile(next.cell, next.exposure);
    }

    drawOutlines();
  };

  const fetchTile = async (cell: Cell, exposure: Exposure) => {
    const controller = new AbortController();
    const version = filtersVersion;

    active.set(cell.id, {
      exposureId: exposure.id,
      controller,
    });

    const key = `${cell.id}/${exposure.id}`;

    try {
      const url = await fetchBlob(
        tileUrl(cell.id, exposure.id, filters, rgb),
        controller.signal,
      );

      if (
        disposed ||
        controller.signal.aborted ||
        version !== filtersVersion
      ) {
        URL.revokeObjectURL(url);
        return;
      }

      blobs.set(cacheKey(cell.id, exposure.id), url);
      exposure.ready = true;

      if (shown.get(cell.id) === exposure.id) {
        show(cell, exposure, url);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        console.warn(`tile ${key} failed`, err);
      }
    } finally {
      if (active.get(cell.id)?.controller === controller) {
        active.delete(cell.id);
      }

      pump();
    }
  };

  const cancel = (cellId: string) => {
    queued.delete(cellId);
    active.get(cellId)?.controller.abort();
    active.delete(cellId);
  };

  const resetTileState = () => {
    for (const name of layers.values()) {
      aladin.removeImageLayer(name);
    }

    layers.clear();
    shown.clear();
    queued.clear();

    active.forEach(({ controller }) => controller.abort());
    active.clear();

    blobs.forEach((url) => URL.revokeObjectURL(url));
    blobs.clear();

    exposures.clear();
    exposureRequests.clear();
  };

  const sameFilters = (
    a: ObservationFilters,
    b: ObservationFilters,
  ) =>
    a.start === b.start &&
    a.end === b.end &&
    (a.bands?.join(',') ?? '') === (b.bands?.join(',') ?? '');

  const sync = () => {
    if (disposed) return;

    const visible = new Set(cells.map((c) => c.id));

    const trackedCells = new Set([
      ...layers.keys(),
      ...queued.keys(),
      ...active.keys(),
    ]);

    for (const cellId of trackedCells) {
      if (visible.has(cellId)) continue;

      const name = layers.get(cellId);
      if (name) aladin.removeImageLayer(name);

      layers.delete(cellId);
      shown.delete(cellId);
      cancel(cellId);
    }

    for (const cell of cells) {
      const choice = exposures.get(cell.id)?.at(-1);

      if (!choice || shown.get(cell.id) === choice.id) {
        continue;
      }

      shown.set(cell.id, choice.id);
      cancel(cell.id);

      const blob = blobs.get(cacheKey(cell.id, choice.id));

      if (blob) {
        show(cell, choice, blob);
      } else {
        queued.set(cell.id, { cell, exposure: choice });
      }
    }

    pump();
  };

  const requestExposures = (cell: Cell) => {
    if (
      disposed ||
      exposures.has(cell.id) ||
      exposureRequests.has(cell.id)
    ) {
      return;
    }

    const version = filtersVersion;

    const request = fetchExposures(cell.id, filters)
      .then((list) => {
        if (disposed || version !== filtersVersion) return;

        exposures.set(cell.id, list);
        publishMetadata();
        sync();
      })
      .catch((err) => {
        console.warn(`exposures ${cell.id} failed`, err);
      })
      .finally(() => {
        if (exposureRequests.get(cell.id) === request) {
          exposureRequests.delete(cell.id);
        }
      });

    exposureRequests.set(cell.id, request);
  };

  const refreshView = async () => {
    if (disposed) return;

    viewAbort?.abort();

    const controller = new AbortController();
    viewAbort = controller;

    const [ra, dec] = aladin.getRaDec();
    const [fov] = aladin.getFov();

    publishMetadata(false);

    try {
      const nextCells = await fetchCells(
        ra,
        dec,
        Math.min(fov, MAX_FOV),
        controller.signal,
      );

      if (disposed || controller.signal.aborted) return;

      cells = nextCells;
    } catch (err) {
      if (!controller.signal.aborted) {
        console.warn('cells failed', err);
      }

      return;
    }

    cells.forEach(requestExposures);
    sync();
    publishMetadata();
  };

  const scheduleView = () => {
    if (disposed) return;

    clearTimeout(viewTimer);
    viewTimer = setTimeout(refreshView, 400);
  };

  aladin.on('positionChanged', scheduleView);
  aladin.on('zoomChanged', scheduleView);
  refreshView();

  return {
    goto(ra: number, dec: number) {
      aladin.gotoRaDec(ra, dec);
      scheduleView();
    },

    setFilters(next: ObservationFilters) {
      if (disposed || sameFilters(filters, next)) return;

      filters = next;
      filtersVersion += 1;
      resetTileState();
      refreshView();
    },

    setRgb(next: RGBSettings) {
      if (disposed || rgbKey(rgb) === rgbKey(next)) return;

      rgb = { ...next };
      filtersVersion += 1;
      resetTileState();
      refreshView();
    },

    dispose() {
      disposed = true;
      filtersVersion += 1;

      clearTimeout(viewTimer);
      viewAbort?.abort();
      resetTileState();
      container.replaceChildren();
    },
  };
}
