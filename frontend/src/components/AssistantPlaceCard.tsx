import Image from "next/image";

import { getGoogleMapsUrl } from "@/lib/maps";
import type { AssistantRecommendation } from "@/types/assistant";
import type { Language } from "@/types/language";

type Props = {
  recommendation: AssistantRecommendation;
  language: Language;
};

export default function AssistantPlaceCard({ recommendation, language }: Props) {
  const { place } = recommendation;
  const image = place.primary_image;
  const imageUrl = image?.thumbnail_url ?? image?.image_url;
  const labels = language === "it"
    ? { why: "Perché è adatto", map: "Apri in Maps", transit: "Mezzi pubblici", details: "Altri dettagli" }
    : { why: "Why it matches", map: "Open in Maps", transit: "Public transport", details: "More details" };

  return (
    <article className="overflow-hidden rounded-2xl border border-white/10 bg-[#0B112B]/70">
      <div className="flex gap-4 p-4">
        {imageUrl ? (
          <div className="relative h-24 w-28 shrink-0 overflow-hidden rounded-xl bg-[#121936] sm:h-28 sm:w-36">
            <Image src={imageUrl} alt={place.name} fill sizes="144px" className="object-cover" />
          </div>
        ) : (
          <div className="flex h-24 w-28 shrink-0 items-center justify-center rounded-xl bg-[#FF6846]/10 text-2xl text-[#FF6846] sm:h-28 sm:w-36">⌖</div>
        )}

        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#FF6846]">
            {place.category.replaceAll("_", " ")}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-[#FFF8E7]">{place.name}</h3>
          <p className="mt-1 text-sm text-[#A9B1D6]">{place.address}, {place.city}</p>
          {recommendation.distance_km !== null && (
            <p className="mt-1 text-xs text-[#FFC83D]">{recommendation.distance_km.toFixed(1)} km</p>
          )}
        </div>
      </div>

      <div className="border-t border-white/10 px-4 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#FFC83D]">{labels.why}</p>
        <p className="mt-1 text-sm leading-6 text-[#FFF8E7]">{recommendation.reason}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={getGoogleMapsUrl(place)} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-white/10 px-3 py-2 text-xs hover:border-[#FF6846]/50">{labels.map}</a>
          {recommendation.transit_url && (
            <a href={recommendation.transit_url} target="_blank" rel="noopener noreferrer" className="rounded-lg bg-[#FFC83D] px-3 py-2 text-xs font-semibold text-[#070B24]">{labels.transit}</a>
          )}
        </div>
        {(place.description || place.opening_hours || place.website) && (
          <details className="mt-3 text-sm text-[#A9B1D6]">
            <summary className="cursor-pointer text-[#FFF8E7]">{labels.details}</summary>
            {place.description && <p className="mt-2 leading-6">{place.description}</p>}
            {place.opening_hours && <p className="mt-2">{place.opening_hours}</p>}
          </details>
        )}
      </div>
    </article>
  );
}
