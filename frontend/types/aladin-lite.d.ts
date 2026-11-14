declare module 'aladin-lite' {
  type Listener = (event: never) => void;

  export interface ImageLayer {
    setOpacity(opacity: number): void;
  }

  export interface Overlay {
    addFootprints(footprints: unknown[]): void;
    removeAll(): void;
  }

  export interface Aladin {
    on(event: string, callback: Listener): void;
    gotoRaDec(ra: number, dec: number): void;
    getRaDec(): [number, number];
    getFov(): [number, number];
    setFoVRange(min: number | null, max: number | null): void;
    setOverlayImageLayer(layer: ImageLayer, name: string): ImageLayer;
    removeImageLayer(name: string): void;
    getBaseImageLayer(): ImageLayer | undefined;
    addOverlay(overlay: Overlay): void;
  }

  const A: {
    init: Promise<void>;
    aladin(element: HTMLElement, options: Record<string, unknown>): Aladin;
    image(url: string, options: Record<string, unknown>): ImageLayer;
    graphicOverlay(options: Record<string, unknown>): Overlay;
    polygon(vertices: [number, number][], options?: Record<string, unknown>): unknown;
  };

  export default A;
}
