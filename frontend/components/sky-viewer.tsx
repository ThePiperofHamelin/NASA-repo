'use client';

import type { Aladin, Overlay } from 'aladin-lite';
import { useEffect, useRef } from 'react';
import {
  type Cell,
  type Exposure,
  DEFAULT_TARGET,
  MAX_FOV,
  fetchCells,
  fetchExposures,
  tileUrl,
} from '@/lib/sky';

type AladinModule = typeof import('aladin-lite').default;

type Props = {
  target: { ra: number; dec: number; key: number };
  onLoadingChange: (count: number) => void;
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

export function SkyViewer({ target, onLoadingChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const engine = useRef<ReturnType<typeof createEngine> | null>(null);
  const callbacks = useRef({ onLoadingChange });

  useEffect(() => {
    callbacks.current = { onLoadingChange };
  });

  useEffect(() => {
    let disposed = false;
    import('aladin-lite').then(async ({ default: A }) => {
      await A.init;
      if (disposed || !containerRef.current) return;
      engine.current = createEngine(A, containerRef.current, callbacks);
    });
    return () => {
      disposed = true;
      engine.current?.dispose();
      engine.current = null;
    };
  }, []);

  useEffect(() => {
    if (target.key > 0) engine.current?.goto(target.ra, target.dec);
  }, [target]);

  return (
    <div className="absolute inset-0 bg-black">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}

function createEngine(
  A: AladinModule,
  container: HTMLElement,
  callbacks: { current: Pick<Props, 'onLoadingChange'> }
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

  const outlines: Overlay = A.graphicOverlay({ color: '#94a3b8', lineWidth: 1, lineDash: [4, 4] });
  aladin.addOverlay(outlines);

  let cells: Cell[] = [];
  const exposures = new Map<string, Exposure[]>();
  const exposureRequests = new Map<string, Promise<void>>();
  const blobs = new Map<string, string>();
  const shown = new Map<string, string>();
  const layers = new Map<string, string>();
  const queued = new Map<string, { cell: Cell; exposure: Exposure }>();
  const active = new Map<string, { exposureId: string; controller: AbortController }>();
  let viewAbort: AbortController | null = null;
  let viewTimer: ReturnType<typeof setTimeout> | undefined;

  const drawOutlines = () => {
    outlines.removeAll();
    const loading = cells.filter((c) => queued.has(c.id) || active.has(c.id));
    outlines.addFootprints(loading.map((c) => A.polygon(c.corners)));
    callbacks.current.onLoadingChange(loading.length);
  };

  const fadeIn = (cellId: string, name: string, layer: ReturnType<AladinModule['image']>) => {
    const start = performance.now();
    const step = (now: number) => {
      if (layers.get(cellId) !== name) return;
      const t = Math.min(1, (now - start) / FADE_MS);
      layer.setOpacity(t);
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const show = (cell: Cell, exposure: Exposure, url: string) => {
    const name = `${cell.id}|${exposure.id}`;
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
        if (previous) setTimeout(() => aladin.removeImageLayer(previous), FADE_MS);
      },
    });
    aladin.setOverlayImageLayer(layer, name);
  };

  const priority = ({ cell, exposure }: { cell: Cell; exposure: Exposure }) => {
    const [ra, dec] = aladin.getRaDec();
    const dRa = (((Number(cell.wcs.CRVAL1) - ra + 540) % 360) - 180) * Math.cos((dec * Math.PI) / 180);
    const distance = Math.hypot(dRa, Number(cell.wcs.CRVAL2) - dec);
    return (exposure.ready ? 0 : 1000) + distance;
  };

  const pump = () => {
    while (active.size < MAX_TILE_FETCHES && queued.size > 0) {
      const next = [...queued.values()].reduce((a, b) => (priority(b) < priority(a) ? b : a));
      queued.delete(next.cell.id);
      fetchTile(next.cell, next.exposure);
    }
    drawOutlines();
  };

  const fetchTile = async (cell: Cell, exposure: Exposure) => {
    const controller = new AbortController();
    active.set(cell.id, { exposureId: exposure.id, controller });
    const key = `${cell.id}/${exposure.id}`;
    try {
      const url = await fetchBlob(tileUrl(cell.id, exposure.id), controller.signal);
      blobs.set(key, url);
      exposure.ready = true;
      if (shown.get(cell.id) === exposure.id) show(cell, exposure, url);
    } catch (err) {
      if (!controller.signal.aborted) console.warn(`tile ${key} failed`, err);
    } finally {
      if (active.get(cell.id)?.controller === controller) active.delete(cell.id);
      pump();
    }
  };

  const cancel = (cellId: string) => {
    queued.delete(cellId);
    active.get(cellId)?.controller.abort();
    active.delete(cellId);
  };

  const sync = () => {
    const visible = new Set(cells.map((c) => c.id));
    for (const cellId of new Set([...layers.keys(), ...queued.keys(), ...active.keys()])) {
      if (visible.has(cellId)) continue;
      const name = layers.get(cellId);
      if (name) aladin.removeImageLayer(name);
      layers.delete(cellId);
      shown.delete(cellId);
      cancel(cellId);
    }
    for (const cell of cells) {
      const choice = exposures.get(cell.id)?.at(-1);
      if (!choice || shown.get(cell.id) === choice.id) continue;
      shown.set(cell.id, choice.id);
      cancel(cell.id);
      const blob = blobs.get(`${cell.id}/${choice.id}`);
      if (blob) show(cell, choice, blob);
      else queued.set(cell.id, { cell, exposure: choice });
    }
    pump();
  };

  const requestExposures = (cell: Cell) => {
    if (exposures.has(cell.id) || exposureRequests.has(cell.id)) return;
    const request = fetchExposures(cell.id)
      .then((list) => {
        exposures.set(cell.id, list);
        sync();
      })
      .catch((err) => console.warn(`exposures ${cell.id} failed`, err))
      .finally(() => exposureRequests.delete(cell.id));
    exposureRequests.set(cell.id, request);
  };

  const refreshView = async () => {
    viewAbort?.abort();
    const controller = new AbortController();
    viewAbort = controller;
    const [ra, dec] = aladin.getRaDec();
    const [fov] = aladin.getFov();
    try {
      cells = await fetchCells(ra, dec, Math.min(fov, MAX_FOV), controller.signal);
    } catch (err) {
      if (!controller.signal.aborted) console.warn('cells failed', err);
      return;
    }
    cells.forEach(requestExposures);
    sync();
  };

  const scheduleView = () => {
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
    dispose() {
      clearTimeout(viewTimer);
      viewAbort?.abort();
      active.forEach(({ controller }) => controller.abort());
      blobs.forEach((url) => URL.revokeObjectURL(url));
      container.replaceChildren();
    },
  };
}
