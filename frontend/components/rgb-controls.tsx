'use client';

import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { DEFAULT_RGB, type RGBSettings } from '@/lib/sky';

const SLIDERS: {
  key: keyof RGBSettings;
  label: string;
  min: number;
  max: number;
}[] = [
  { key: 'r_weight', label: 'Red', min: 0, max: 2 },
  { key: 'g_weight', label: 'Green', min: 0, max: 2 },
  { key: 'b_weight', label: 'Blue', min: 0, max: 2 },
  { key: 'brightness', label: 'Brightness', min: 0.2, max: 3 },
];

export function RGBControls({
  onApply,
}: {
  onApply: (rgb: RGBSettings) => void;
}) {
  const [draft, setDraft] = useState<RGBSettings>({ ...DEFAULT_RGB });
  const [collapsed, setCollapsed] = useState(false);
  const id = useId();

  return (
    <section
      aria-label="RGB colour controls"
      className="absolute bottom-4 left-1/2 z-30 w-80 max-w-[calc(100vw-2rem)] -translate-x-1/2 rounded-2xl border border-[#31578C] bg-[#080F1F]/95 p-4 text-white shadow-xl backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">RGB Controls</h2>

        <button
          type="button"
          className="rounded border border-[#31578C] px-3 py-1"
          aria-expanded={!collapsed}
          aria-controls={`${id}-body`}
          aria-label={
            collapsed ? 'Expand RGB controls' : 'Collapse RGB controls'
          }
          onClick={() => setCollapsed((value) => !value)}
        >
          {collapsed ? '+' : '−'}
        </button>
      </div>

      <form
        id={`${id}-body`}
        hidden={collapsed}
        className="max-h-[60vh] overflow-y-auto"
        onSubmit={(event) => {
          event.preventDefault();
          onApply({ ...draft });
        }}
      >
        <p className="mt-2 text-xs text-slate-400">
          Green is derived from the short and long detector images.
          Click Apply RGB to update the image.
        </p>

        {SLIDERS.map(({ key, label, min, max }) => (
          <div key={key} className="mt-3">
            <div className="mb-1 flex justify-between text-sm">
              <label htmlFor={`${id}-${key}`}>{label}</label>

              <output
                htmlFor={`${id}-${key}`}
                className="font-mono"
              >
                {draft[key].toFixed(2)}
              </output>
            </div>

            <input
              id={`${id}-${key}`}
              type="range"
              min={min}
              max={max}
              step={0.05}
              value={draft[key]}
              className="w-full accent-[#FC3D21]"
              onChange={(event) => {
                const value = Number(event.target.value);
                setDraft((previous) => ({
                  ...previous,
                  [key]: value,
                }));
              }}
            />
          </div>
        ))}

        <div className="mt-4 flex gap-2">
          <Button
            type="submit"
            className="flex-1 bg-[#FC3D21] text-white hover:bg-[#e5351b]"
          >
            Apply RGB
          </Button>

          <Button
            type="button"
            variant="outline"
            className="border-[#31578C] bg-transparent text-white"
            onClick={() => {
              const defaults = { ...DEFAULT_RGB };
              setDraft(defaults);
              onApply(defaults);
            }}
          >
            Reset
          </Button>
        </div>
      </form>
    </section>
  );
}