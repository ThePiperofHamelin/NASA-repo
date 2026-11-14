'use client';

import { useState } from 'react';

import { GotoBox } from '@/components/goto-box';
import { ModeToggle } from '@/components/mode-toggle';
import { SkyViewer } from '@/components/sky-viewer';
import { MetadataPanel } from '@/components/metadata-panel';
import { DiscoveryTools } from '@/components/discovery-tools';
import { DEFAULT_TARGET } from '@/lib/sky';

type ViewMetadata = {
  ra: number;
  dec: number;
  observationMjd: number | null;
};

export default function Home() {
  const [target, setTarget] = useState({ ...DEFAULT_TARGET, key: 0 });
  const [loading, setLoading] = useState(0);
  const [inverted, setInverted] = useState(false);
  const [metadata, setMetadata] = useState<ViewMetadata>({
    ...DEFAULT_TARGET,
    observationMjd: null,
  });

  const goTo = (ra: number, dec: number) => {
    setTarget((previous) => ({ ra, dec, key: previous.key + 1 }));
    setMetadata({ ra, dec, observationMjd: null });
  };

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-black">
      {/* Visual inversion only. Original image data is unchanged. */}
      <div
        className="absolute inset-0"
        style={{ filter: inverted ? 'invert(1)' : 'none' }}
      >
        <SkyViewer
          target={target}
          onLoadingChange={setLoading}
          onMetadataChange={setMetadata}
        />
      </div>

      <GotoBox onGo={goTo} />

      <MetadataPanel
        ra={metadata.ra}
        dec={metadata.dec}
        observationMjd={metadata.observationMjd}
      />

      <div className="absolute right-4 top-4 z-20 flex items-center gap-2">
        {loading > 0 && (
          <div
            role="status"
            aria-live="polite"
            className="flex items-center gap-2 rounded-xl border border-[#31578C]/70 bg-[#080F1F]/90 px-3 py-2 text-[10px] font-medium tracking-wide text-[#C5D5F2] shadow-lg backdrop-blur-xl"
          >
            <span className="h-2 w-2 animate-pulse rounded-full bg-[#FC3D21]" />
            <span>
              LOADING {loading} {loading === 1 ? 'TILE' : 'TILES'}
            </span>
          </div>
        )}
        <ModeToggle />
      </div>

      <DiscoveryTools
        inverted={inverted}
        onToggleInvert={() => setInverted((value) => !value)}
        onJumpToExample={() => goTo(DEFAULT_TARGET.ra, DEFAULT_TARGET.dec)}
        observationMjd={metadata.observationMjd}
      />
    </main>
  );
}
