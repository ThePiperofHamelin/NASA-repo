'use client';

import { useState } from 'react';
import { GotoBox } from '@/components/goto-box';
import { SkyViewer } from '@/components/sky-viewer';
import { DEFAULT_TARGET } from '@/lib/sky';

export default function Home() {
  const [target, setTarget] = useState({ ...DEFAULT_TARGET, key: 0 });
  const [loading, setLoading] = useState(0);

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-black">
      <SkyViewer
        target={target}
        onLoadingChange={setLoading}
      />
      <GotoBox onGo={(ra, dec) => setTarget((t) => ({ ra, dec, key: t.key + 1 }))} />
      {loading > 0 && (
        <div className="absolute top-4 right-4 z-10 rounded-full bg-card/80 px-3 py-1 text-xs text-muted-foreground ring-1 ring-foreground/10 backdrop-blur">
          Loading {loading} {loading === 1 ? 'tile' : 'tiles'}…
        </div>
      )}
    </main>
  );
}
