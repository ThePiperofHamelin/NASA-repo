'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { DEFAULT_TARGET } from '@/lib/sky';

export function GotoBox({ onGo }: { onGo: (ra: number, dec: number) => void }) {
  const [ra, setRa] = useState(String(DEFAULT_TARGET.ra));
  const [dec, setDec] = useState(String(DEFAULT_TARGET.dec));

  const raNum = Number(ra);
  const decNum = Number(dec);
  const valid =
    ra.trim() !== '' && dec.trim() !== '' && raNum >= 0 && raNum < 360 && decNum >= -90 && decNum <= 90;

  return (
    <form
      className="absolute top-4 left-4 z-10 flex items-end gap-2 rounded-xl bg-card/80 p-3 ring-1 ring-foreground/10 backdrop-blur"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onGo(raNum, decNum);
      }}
    >
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        RA
        <Input className="w-28" inputMode="decimal" value={ra} onChange={(e) => setRa(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-xs text-muted-foreground">
        Dec
        <Input className="w-28" inputMode="decimal" value={dec} onChange={(e) => setDec(e.target.value)} />
      </label>
      <Button type="submit" disabled={!valid}>
        Go
      </Button>
    </form>
  );
}
