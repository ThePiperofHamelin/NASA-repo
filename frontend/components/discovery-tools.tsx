'use client';

import { useState } from 'react';

type DiscoveryToolsProps = {
  inverted: boolean;
  onToggleInvert: () => void;
  onJumpToExample: () => void;
  observationMjd: number | null;
};

const STEP_COUNT = 4;

function formatMjd(mjd: number | null): string {
  if (mjd === null || !Number.isFinite(mjd)) return 'Not available yet';
  const date = new Date((mjd - 40587) * 86400000);
  if (Number.isNaN(date.getTime())) return 'Not available yet';
  return `${date.toISOString().slice(0, 19).replace('T', ' ')} UTC`;
}

export function DiscoveryTools({
  inverted,
  onToggleInvert,
  onJumpToExample,
  observationMjd,
}: DiscoveryToolsProps) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  return (
    <>
      <div className="absolute right-4 top-16 z-30 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="guided-discovery"
          onClick={() => {
            setOpen((current) => !current);
            setStep(0);
          }}
          className="rounded-lg border border-[#31578C] bg-[#080F1F]/95 px-3 py-2 text-[11px] font-semibold text-white shadow-lg backdrop-blur hover:border-[#6484BD] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
        >
          {open ? 'Close Tour' : 'Explore Changes'}
        </button>

        <button
          type="button"
          aria-pressed={inverted}
          onClick={onToggleInvert}
          className={`rounded-lg border px-3 py-2 text-[11px] font-semibold shadow-lg backdrop-blur focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white ${
            inverted
              ? 'border-[#FC3D21] bg-[#FC3D21] text-white hover:bg-[#D92F18]'
              : 'border-[#31578C] bg-[#080F1F]/95 text-white hover:border-[#FC3D21]'
          }`}
        >
          {inverted ? 'Normal View' : 'Invert Image'}
        </button>
      </div>

      {open && (
        <section
          id="guided-discovery"
          aria-label="Guided sky discovery"
          className="absolute right-4 top-28 z-40 max-h-[calc(100dvh-8rem)] w-[min(360px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-[#31578C] bg-[#080F1F]/95 p-4 text-white shadow-2xl backdrop-blur-xl"
        >
          <div className="mb-3 h-[3px] w-14 rounded-full bg-[#FC3D21]" />
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#FF8171]">
            SPHEREx / Guided Discovery
          </p>
          <p className="mt-2 font-mono text-[10px] text-[#AFC0D8]">
            STEP {step + 1} / {STEP_COUNT}
          </p>

          {step === 0 && (
            <div className="mt-3 space-y-3">
              <h2 className="text-lg font-bold">Explore an observed sky region</h2>
              <p className="text-xs leading-5 text-[#C5D5F2]">
                
            Start with the viewer&apos;s default sky position. The map uses astronomical
            image data, rather than a simulated star field.

                image data, rather than a simulated star field.
              </p>
              <button
                type="button"
                onClick={onJumpToExample}
                className="w-full rounded-lg bg-[#FC3D21] px-3 py-2 text-xs font-semibold text-white hover:bg-[#D92F18]"
              >
                Go to example region
              </button>
            </div>
          )}

          {step === 1 && (
            <div className="mt-3 space-y-3">
              <h2 className="text-lg font-bold">Read the observation details</h2>
              <p className="text-xs leading-5 text-[#C5D5F2]">
                RA and Dec describe the sky position. The metadata panel shows the
                time of a nearby available exposure, which may not represent every
                image visible on screen.
              </p>
              <div className="rounded-lg border border-[#31578C] bg-[#152541] p-3">
                <p className="text-[10px] uppercase tracking-wide text-[#AFC0D8]">
                  Nearby exposure time
                </p>
                <p className="mt-1 font-mono text-xs text-white">
                  {formatMjd(observationMjd)}
                </p>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="mt-3 space-y-3">
              <h2 className="text-lg font-bold">Inspect visual contrast</h2>
              <p className="text-xs leading-5 text-[#C5D5F2]">
                Try an inverted display to inspect bright and dark structures.
                This is a visual filter only: it does not change the underlying
                scientific data or show a second observation in time.
              </p>
              <button
                type="button"
                onClick={onToggleInvert}
                className="w-full rounded-lg border border-[#FC3D21] px-3 py-2 text-xs font-semibold text-white hover:bg-[#FC3D21]/20"
              >
                {inverted ? 'Return to normal colours' : 'Try inverted colours'}
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="mt-3 space-y-3">
              <h2 className="text-lg font-bold">What changes over time?</h2>
              <p className="text-xs leading-5 text-[#C5D5F2]">
                To identify a moving or changing source, we need two genuine
                observations of the same sky region at different times, aligned
                in sky coordinates and compared on the same scale.
              </p>
              <div className="rounded-lg border border-[#31578C] bg-[#152541] p-3 text-xs leading-5 text-[#C5D5F2]">
                <strong className="text-white">Try the Image Filters panel:</strong>{' '}
                choose a UTC time range and bandpass to re-query the observations
                shown in the viewer. A side-by-side two-epoch comparison is still
                a future integration.
              </div>
            </div>
          )}

          <div className="mt-5 flex items-center justify-between gap-2 border-t border-white/10 pt-3">
            <button
              type="button"
              disabled={step === 0}
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              className="rounded-lg border border-[#31578C] px-3 py-2 text-xs text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => {
                if (step === STEP_COUNT - 1) setOpen(false);
                else setStep((s) => s + 1);
              }}
              className="rounded-lg bg-[#0B3D91] px-4 py-2 text-xs font-semibold text-white hover:bg-[#154DA4]"
            >
              {step === STEP_COUNT - 1 ? 'Finish Tour' : 'Next Step'}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
