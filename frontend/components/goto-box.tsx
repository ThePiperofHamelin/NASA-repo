
'use client';

import { useState } from 'react';
import { DEFAULT_TARGET } from '@/lib/sky';

export function GotoBox({
  onGo,
}: {
  onGo: (ra: number, dec: number) => void;
}) {
  const [ra, setRa] = useState(String(DEFAULT_TARGET.ra));
  const [dec, setDec] = useState(String(DEFAULT_TARGET.dec));
  const [collapsed, setCollapsed] = useState(false);

  const raNum = Number(ra);
  const decNum = Number(dec);

  const valid =
    ra.trim() !== '' &&
    dec.trim() !== '' &&
    Number.isFinite(raNum) &&
    Number.isFinite(decNum) &&
    raNum >= 0 &&
    raNum < 360 &&
    decNum >= -90 &&
    decNum <= 90;

  return (
    <form
      aria-label="Celestial coordinate navigation"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onGo(raNum, decNum);
      }}
      className={`
        absolute left-4 top-4 z-20
        max-w-[calc(100vw-2rem)]
        overflow-hidden rounded-2xl
        border border-[#31578C]/70
        bg-[#080F1F]/90 text-white
        shadow-[0_18px_60px_rgba(0,0,0,0.5)]
        backdrop-blur-xl
        transition-all duration-300
        ${collapsed ? 'w-64' : 'w-[390px]'}
      `}
    >
      <div className="h-[3px] bg-gradient-to-r from-[#FC3D21] to-[#0B3D91]" />

      <div className="p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-[#FF8171]">
              SPHEREx / Navigation
            </p>

            <h2 className="mt-1 text-sm font-bold">
              Celestial Coordinates
            </h2>
          </div>

          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-expanded={!collapsed}
            aria-label={
              collapsed
                ? 'Expand navigation'
                : 'Collapse navigation'
            }
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#496BA5] bg-[#0B3D91]/60 text-white transition-colors hover:bg-[#0B3D91] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            {collapsed ? '+' : '−'}
          </button>
        </div>

        {!collapsed && (
          <div className="mt-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex min-w-0 flex-col gap-2">
                <span className="text-[10px] uppercase text-[#AFC0D8]">
                  RA
                </span>

                <input
                  type="text"
                  inputMode="decimal"
                  value={ra}
                  onChange={(e) => setRa(e.target.value)}
                  aria-label="Right Ascension in degrees"
                  className="w-full min-w-0 rounded-lg border border-[#29446F] bg-[#152541] px-3 py-2.5 font-mono text-xs text-white outline-none focus:border-[#FC3D21]"
                />
              </label>

              <label className="flex min-w-0 flex-col gap-2">
                <span className="text-[10px] uppercase text-[#AFC0D8]">
                  DEC
                </span>

                <input
                  type="text"
                  inputMode="decimal"
                  value={dec}
                  onChange={(e) => setDec(e.target.value)}
                  aria-label="Declination in degrees"
                  className="w-full min-w-0 rounded-lg border border-[#29446F] bg-[#152541] px-3 py-2.5 font-mono text-xs text-white outline-none focus:border-[#FC3D21]"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={!valid}
              className="mt-4 w-full rounded-lg bg-[#FC3D21] px-4 py-2.5 text-xs font-bold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[#D92F18] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              GO TO TARGET →
            </button>

            <p className="mt-3 border-t border-white/10 pt-3 font-mono text-[9px] text-[#9CAFCB]">
              RA: 0–360° | DEC: −90° to +90°
            </p>
          </div>
        )}
      </div>
    </form>
  );
}
