'use client';

import { useState } from 'react';
import {
  BAND_OPTIONS,
  DEFAULT_FILTERS,
  type ObservationFilters,
  inputValueToMjd,
  mjdToInputValue,
} from '@/lib/sky';

type ObservationFiltersPanelProps = {
  filters: ObservationFilters;
  onApply: (filters: ObservationFilters) => void;
};

const inputClass =
  'w-full min-w-0 rounded-lg border border-[#29446F] bg-[#152541] px-3 py-2.5 font-mono text-xs text-white outline-none [color-scheme:dark] focus:border-[#FC3D21]';

function bandValueFor(filters: ObservationFilters) {
  const current = filters.bands?.join(',') ?? null;
  return (
    BAND_OPTIONS.find((option) => (option.bands?.join(',') ?? null) === current)
      ?.value ?? 'auto'
  );
}

function bandOption(value: string) {
  return BAND_OPTIONS.find((option) => option.value === value) ?? BAND_OPTIONS[0];
}

export function ObservationFilters({
  filters,
  onApply,
}: ObservationFiltersPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [start, setStart] = useState(
    filters.start == null ? '' : mjdToInputValue(filters.start),
  );
  const [end, setEnd] = useState(
    filters.end == null ? '' : mjdToInputValue(filters.end),
  );
  const [band, setBand] = useState(bandValueFor(filters));

  const startMjd = inputValueToMjd(start);
  const endMjd = inputValueToMjd(end);
  const invalidStart = start.trim() !== '' && startMjd === null;
  const invalidEnd = end.trim() !== '' && endMjd === null;
  const invalidRange =
    startMjd !== null && endMjd !== null && startMjd > endMjd;
  const valid = !invalidStart && !invalidEnd && !invalidRange;

  const selectedBand = bandOption(band);
  const rangeLabel =
    startMjd !== null || endMjd !== null
      ? `${startMjd === null ? 'Any' : startMjd.toFixed(2)} – ${
          endMjd === null ? 'Any' : endMjd.toFixed(2)
        } MJD`
      : 'All observation times';

  return (
    <form
      aria-label="Observation time and bandpass filters"
      onSubmit={(event) => {
        event.preventDefault();
        if (!valid) return;
        onApply({
          start: startMjd,
          end: endMjd,
          bands: selectedBand.bands ? [...selectedBand.bands] : null,
        });
      }}
      className={`
        absolute bottom-4 left-4 z-20
        max-w-[calc(100vw-2rem)]
        overflow-hidden rounded-2xl
        border border-[#31578C]/70
        bg-[#080F1F]/90 text-white
        shadow-[0_18px_60px_rgba(0,0,0,0.5)]
        backdrop-blur-xl
        transition-all duration-300
        ${collapsed ? 'w-72' : 'w-[360px]'}
      `}
    >
      <div className="h-[3px] bg-gradient-to-r from-[#0B3D91] to-[#FC3D21]" />

      <div className="p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-[#FF8171]">
              SPHEREx / Observations
            </p>

            <h2 className="mt-1 text-sm font-bold">Image Filters</h2>
          </div>

          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-expanded={!collapsed}
            aria-label={
              collapsed ? 'Expand image filters' : 'Collapse image filters'
            }
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#496BA5] bg-[#0B3D91]/60 text-white transition-colors hover:bg-[#0B3D91] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            {collapsed ? '+' : '−'}
          </button>
        </div>

        {collapsed && (
          <p className="mt-3 border-t border-white/10 pt-3 font-mono text-[10px] text-[#AFC0D8]">
            {rangeLabel} · {selectedBand.label}
          </p>
        )}

        {!collapsed && (
          <div className="mt-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="flex min-w-0 flex-col gap-2">
                <span className="text-[10px] uppercase text-[#AFC0D8]">
                  From (UTC)
                </span>

                <input
                  type="datetime-local"
                  step="60"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                  aria-label="Earliest observation time in UTC"
                  aria-invalid={invalidStart}
                  className={`${inputClass} ${
                    invalidStart ? 'border-[#FC3D21]' : ''
                  }`}
                />
              </label>

              <label className="flex min-w-0 flex-col gap-2">
                <span className="text-[10px] uppercase text-[#AFC0D8]">
                  To (UTC)
                </span>

                <input
                  type="datetime-local"
                  step="60"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                  aria-label="Latest observation time in UTC"
                  aria-invalid={invalidEnd}
                  className={`${inputClass} ${
                    invalidEnd ? 'border-[#FC3D21]' : ''
                  }`}
                />
              </label>
            </div>

            <label className="mt-3 flex min-w-0 flex-col gap-2">
              <span className="text-[10px] uppercase text-[#AFC0D8]">
                Bandpass
              </span>

              <select
                value={band}
                onChange={(event) => setBand(event.target.value as typeof band)}
                aria-label="Detector bandpass pair"
                className={inputClass}
              >
                {BAND_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} — {option.detail}
                  </option>
                ))}
              </select>
            </label>

            <p
              className={`mt-3 font-mono text-[10px] ${
                invalidRange ? 'text-[#FF8171]' : 'text-[#9CAFCB]'
              }`}
            >
              {invalidRange
                ? 'The start time must not be after the end time.'
                : `${rangeLabel} · ${selectedBand.label}`}
            </p>

            <div className="mt-4 flex gap-2">
              <button
                type="submit"
                disabled={!valid}
                className="flex-1 rounded-lg bg-[#FC3D21] px-4 py-2.5 text-xs font-bold uppercase tracking-[0.18em] text-white transition-colors hover:bg-[#D92F18] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
              >
                Apply Filters
              </button>

              <button
                type="button"
                onClick={() => {
                  setStart('');
                  setEnd('');
                  setBand('auto');
                  onApply(DEFAULT_FILTERS);
                }}
                className="rounded-lg border border-[#31578C] px-3 py-2.5 text-xs font-semibold text-white transition-colors hover:border-[#6484BD] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
              >
                Reset
              </button>
            </div>

            <p className="mt-3 border-t border-white/10 pt-3 font-mono text-[9px] text-[#9CAFCB]">
              The newest matching exposure in each cell is displayed.
            </p>
          </div>
        )}
      </div>
    </form>
  );
}
