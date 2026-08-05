import Image from "next/image";
import type { Place } from "@/types/place";
import {
  getGoogleDirectionsUrl,
  getGoogleMapsUrl,
} from "@/lib/maps";

type PlaceCardProps = {
  place: Place;
};

const categorySymbols: Record<string, string> = {
  attraction: "✦",
  bar: "◆",
  cafe: "☕",
  gallery: "▣",
  museum: "⌂",
  park: "♧",
  restaurant: "●",
};

export default function PlaceCard({ place }: PlaceCardProps) {
  const googleMapsUrl = getGoogleMapsUrl(place);
  const directionsUrl = getGoogleDirectionsUrl(place);
  const image = place.primary_image;
  const displayImageUrl = image?.thumbnail_url ?? image?.image_url;

  return (
    <article className="rounded-3xl border border-white/10 bg-[#121936] p-6 transition duration-200 hover:-translate-y-1 hover:border-[#FF6846]/40 sm:p-7">
      {image && displayImageUrl ? (
        <div>
          <div className="relative aspect-[16/9] overflow-hidden rounded-2xl bg-[#0B112B]">
            <Image
              src={displayImageUrl}
              alt={`${place.name} in ${place.city}`}
              fill
              sizes="(max-width: 768px) 100vw, 50vw"
              className="object-cover"
            />
          </div>

          <p className="mt-2 text-xs leading-5 text-[#A9B1D6]/70">
            Photo by{" "}
            <a
              href={image.source_page_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline decoration-white/20 underline-offset-2 transition hover:text-[#FFF8E7]"
            >
              {image.attribution}
            </a>
            {" · "}
            {image.license_url ? (
              <a
                href={image.license_url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-white/20 underline-offset-2 transition hover:text-[#FFF8E7]"
              >
                {image.license}
              </a>
            ) : (
              image.license
            )}
          </p>
        </div>
      ) : (
        <div className="flex aspect-[16/9] flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-[#FF6846]/15 via-[#0B112B] to-[#FFC83D]/10">
          <span
            aria-hidden="true"
            className="text-4xl text-[#FF6846]"
          >
            {categorySymbols[place.category] ?? "⌖"}
          </span>

          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.15em] text-[#A9B1D6]">
            Photo unavailable
          </p>
        </div>
      )}

      <div className="mt-6 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#FF6846]">
            {place.category}
          </p>

          <h3 className="mt-2 text-2xl font-semibold">
            {place.name}
          </h3>
        </div>

        <span className="rounded-full border border-white/10 bg-[#0B112B] px-3 py-1 text-xs text-[#A9B1D6]">
          {place.city}
        </span>
      </div>

      {place.description && (
        <p className="mt-4 leading-7 text-[#A9B1D6]">
          {place.description}
        </p>
      )}

      <p className="mt-5 text-sm text-[#FFF8E7]">
        {place.address}, {place.city}
      </p>

      {place.dietary_options.length > 0 && (
        <div className="mt-5 flex flex-wrap gap-2">
          {place.dietary_options.map((option) => (
            <span
              key={option}
              className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-xs capitalize text-emerald-300"
            >
              {option}
            </span>
          ))}
        </div>
      )}

      {place.distance_km !== undefined && (
        <p className="mt-5 text-sm font-medium text-[#FFC83D]">
          {place.distance_km < 1
            ? `${Math.round(place.distance_km * 1000)} m away`
            : `${place.distance_km.toFixed(1)} km away`}
        </p>
      )}

      <div className="mt-5 flex flex-wrap gap-3">
        <a
          href={googleMapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-xl border border-white/10 px-4 py-2 text-sm font-medium text-[#FFF8E7] transition hover:border-[#FF6846]/50"
        >
          View on Google Maps
        </a>

        <a
          href={directionsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-xl bg-[#FF6846] px-4 py-2 text-sm font-semibold text-[#070B24] transition hover:bg-[#FF826B]"
        >
          Get directions
        </a>
      </div>

      <p className="mt-5 text-xs text-[#A9B1D6]/70">
        {place.latitude.toFixed(5)},{" "}
        {place.longitude.toFixed(5)}
      </p>
    </article>
  );
}