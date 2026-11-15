
'use client';

import { useState } from 'react';

type MetadataPanelProps = {
  ra: number;
  dec: number;
  wavelength?: number | null;
  observationMjd?: number | null;
};

function formatObservationTime(mjd?: number | null) {
  if (mjd == null || !Number.isFinite(mjd)) {
    return 'Not available';
  }

  const timestamp = (mjd - 40587) * 86400000;
  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return 'Not available';
  }

  return date.toISOString().replace('T', ' ').slice(0, 19);
}

function DataCard({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="rounded-xl border border-[#29446F]/70 bg-[#152541]/70 p-3 transition-all duration-300 hover:border-[#5A83C5] hover:bg-[#1B3154]">
      <p className="mb-2 text-[9px] font-medium uppercase tracking-[0.16em] text-[#AFC0D8]">
        {label}
      </p>

      <div className="flex items-baseline gap-1">
        <span className="break-all font-mono text-[13px] font-semibold tabular-nums text-white">
          {value}
        </span>
        {unit && (
          <span className="text-[10px] text-[#B8C9E8]">
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}

export function MetadataPanel({
  ra,
  dec,
  wavelength,
  observationMjd,
}: MetadataPanelProps) {
  const [collapsed, setCollapsed] = useState(false);

  const hasWavelength =
    wavelength != null && Number.isFinite(wavelength);

  const observationTime = formatObservationTime(observationMjd);

  const hasObservationTime =
    observationTime !== 'Not available';

  const availableFields =
    2 + Number(hasWavelength) + Number(hasObservationTime);

  return (
    <aside
      aria-label="Observation metadata"
      className="
        absolute bottom-4 right-4 z-20
        w-80 max-w-[calc(100vw-2rem)]
        overflow-hidden rounded-2xl
        border border-[#31578C]/70
        bg-[#080F1F]/90
        text-white
        shadow-[0_18px_60px_rgba(0,0,0,0.5)]
        backdrop-blur-xl
        transition-all duration-300
        hover:border-[#6484BD]
      "
    >
      {/* NASA-inspired red accent line */}
      <div className="h-[3px] w-full bg-gradient-to-r from-[#FC3D21] via-[#FC3D21] to-[#0B3D91]" />

      <div className="relative p-4">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-[#FF8171]">
              SPHEREx / Sky Explorer
            </p>

            <h2 className="mt-2 text-base font-bold tracking-wide text-white">
              Observation Details
            </h2>

            <p className="mt-1 text-[10px] text-[#AAB8CE]">
              Astronomical Data Interface
            </p>
          </div>

          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            aria-expanded={!collapsed}
            aria-label={
              collapsed
                ? 'Expand observation details'
                : 'Collapse observation details'
            }
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#496BA5] bg-[#0B3D91]/60 text-sm text-white transition-colors hover:bg-[#0B3D91] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            {collapsed ? '+' : '−'}
          </button>
        </div>

        {/* Status */}
        <div className="mt-4 flex items-center gap-2 border-t border-white/10 pt-3">
          <span className="h-2 w-2 rounded-full bg-[#FC3D21]" />

          <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[#C4D2E8]">
            Viewer Active
          </span>
        </div>

        {/* Expandable content */}
        {!collapsed && (
          <div className="mt-4 max-h-[55vh] space-y-3 overflow-y-auto">

            {/* Data grid */}
            <div className="grid grid-cols-2 gap-2">
              <DataCard
                label="Right Ascension"
                value={ra.toFixed(5)}
                unit="°"
              />

              <DataCard
                label="Declination"
                value={dec.toFixed(5)}
                unit="°"
              />

              <DataCard
                label="Wavelength"
                value={
                  hasWavelength
                    ? wavelength!.toFixed(3)
                    : 'Not available'
                }
                unit={hasWavelength ? 'μm' : undefined}
              />

              <DataCard
                label="Data Fields"
                value={`${availableFields} / 4`}
              />
            </div>

            {/* Observation Time */}
            <div className="rounded-xl border border-[#29446F]/70 bg-[#152541]/70 p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-[#FC3D21]" />

                <span className="text-[9px] uppercase tracking-[0.15em] text-[#B8C7DE]">
                  Nearby Exposure / UTC
                </span>
              </div>

              <p className="font-mono text-xs font-medium tabular-nums tracking-wide text-white">
                {observationTime}
              </p>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-white/10 pt-3">
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-[#9CAFCB]">
                Observation Telemetry
              </span>

              <span className="font-mono text-[9px] text-[#C5D5F2]">
                {availableFields}/4 DATA
              </span>
            </div>

          </div>
        )}
      </div>
    </aside>
  );
}
