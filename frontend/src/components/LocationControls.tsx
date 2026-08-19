"use client";

import type { Language } from "@/types/language";
import { FILTER_COPY } from "@/lib/i18n";

type LocationControlsProps = {
  language: Language;
  radiusKm: number;
  isLocating: boolean;
  locationStatus: string;
  isNearbyMode: boolean;
  onRadiusChange: (radiusKm: number) => void;
  onUseLocation: () => void;
  onExitNearbyMode: () => void;
};

export default function LocationControls({
  language,
  radiusKm,
  isLocating,
  locationStatus,
  isNearbyMode,
  onRadiusChange,
  onUseLocation,
  onExitNearbyMode,
}: LocationControlsProps) {
  const t = FILTER_COPY[language];
  return (
    <div className="mt-4 flex flex-col gap-4 rounded-3xl border border-white/10 bg-[#121936] p-5 sm:flex-row sm:items-end">
      <div className="sm:w-52">
        <label
          htmlFor="radius-filter"
          className="mb-2 block text-xs font-semibold uppercase tracking-[0.15em] text-[#A9B1D6]"
        >
          {t.radius}
        </label>

        <select
          id="radius-filter"
          value={radiusKm}
          onChange={(event) =>
            onRadiusChange(Number(event.target.value))
          }
          className="min-h-12 w-full rounded-xl border border-white/10 bg-[#0B112B] px-4 text-[#FFF8E7] outline-none focus:border-[#FF6846]"
        >
          <option value={1}>1 km</option>
          <option value={2}>2 km</option>
          <option value={3}>3 km</option>
          <option value={4}>4 km</option>
          <option value={5}>5 km</option>
        </select>
      </div>

      <button
        type="button"
        disabled={isLocating}
        onClick={onUseLocation}
        className="min-h-12 rounded-xl bg-[#FFC83D] px-5 font-semibold text-[#070B24] transition hover:bg-[#FFD66B] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isLocating ? t.finding : t.useLocation}
      </button>

      {isNearbyMode && (
        <button
          type="button"
          onClick={onExitNearbyMode}
          className="min-h-12 rounded-xl border border-white/10 px-5 text-[#A9B1D6] transition hover:border-[#FF6846]/50 hover:text-[#FFF8E7]"
        >
          {t.showAll}
        </button>
      )}

      {locationStatus && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-[#A9B1D6] sm:ml-auto"
        >
          {locationStatus}
        </p>
      )}
    </div>
  );
}
