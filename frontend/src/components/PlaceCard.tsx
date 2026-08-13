import Image from "next/image";
import type { Place } from "@/types/place";
import {
  getGoogleDirectionsUrl,
  getGoogleMapsUrl,
} from "@/lib/maps";

type PlaceCardProps = {
  place: Place;
  recommendationReason?: string;
  transitUrl?: string | null;
};

const categorySymbols: Record<string, string> = {
  attraction: "✦",
  bar: "◆",
  cafe: "☕",
  buddhist_temple: "◇",
  church: "✦",
  community_centre: "◎",
  fast_food: "●",
  fitness_centre: "◆",
  gallery: "▣",
  garden: "♧",
  gurdwara: "◇",
  hindu_temple: "◇",
  historic_site: "⌂",
  hostel: "⌂",
  hotel: "◆",
  library: "▤",
  market: "◇",
  monument: "▲",
  mosque: "◇",
  music_venue: "♫",
  museum: "⌂",
  park: "♧",
  place_of_worship: "◇",
  playground: "○",
  pub: "◆",
  restaurant: "●",
  shopping_centre: "▤",
  sports_centre: "◆",
  supermarket: "▤",
  synagogue: "◇",
  theatre: "◐",
  tourist_information: "i",
  viewpoint: "⌖",
};

export default function PlaceCard({
  place,
  recommendationReason,
  transitUrl,
}: PlaceCardProps) {
  const googleMapsUrl = getGoogleMapsUrl(place);
  const directionsUrl = getGoogleDirectionsUrl(place);
  const image = place.primary_image;
  const displayImageUrl = image?.thumbnail_url ?? image?.image_url;
  const websiteUrl =
    place.website?.startsWith("https://") ||
    place.website?.startsWith("http://")
      ? place.website
      : undefined;

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
            {place.category.replaceAll("_", " ")}
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

      {recommendationReason && (
        <div className="mt-5 rounded-2xl border border-[#FFC83D]/25 bg-[#FFC83D]/10 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#FFC83D]">
            Why it matches
          </p>
          <p className="mt-2 text-sm leading-6 text-[#FFF8E7]">
            {recommendationReason}
          </p>
        </div>
      )}

      <p className="mt-5 text-sm text-[#FFF8E7]">
        {place.address}, {place.city}
      </p>

      {(place.opening_hours || place.operator || websiteUrl) && (
        <dl className="mt-5 space-y-2 rounded-2xl border border-white/10 bg-[#0B112B]/60 p-4 text-sm">
          {place.opening_hours && (
            <div className="flex gap-2">
              <dt className="font-semibold text-[#FFC83D]">
                Hours:
              </dt>
              <dd className="text-[#A9B1D6]">
                {place.opening_hours}
              </dd>
            </div>
          )}

          {place.operator && (
            <div className="flex gap-2">
              <dt className="font-semibold text-[#FFC83D]">
                Operator:
              </dt>
              <dd className="text-[#A9B1D6]">
                {place.operator}
              </dd>
            </div>
          )}

          {websiteUrl && (
            <div className="flex gap-2">
              <dt className="font-semibold text-[#FFC83D]">
                Website:
              </dt>
              <dd>
                <a
                  href={websiteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#A9B1D6] underline decoration-white/20 underline-offset-2 transition hover:text-[#FFF8E7]"
                >
                  Visit official website
                </a>
              </dd>
            </div>
          )}
        </dl>
      )}

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

        {transitUrl && (
          <a
            href={transitUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-xl bg-[#FFC83D] px-4 py-2 text-sm font-semibold text-[#070B24] transition hover:bg-[#FFD66B]"
          >
            Public transport
          </a>
        )}
      </div>

      <p className="mt-5 text-xs text-[#A9B1D6]/70">
        {place.latitude.toFixed(5)},{" "}
        {place.longitude.toFixed(5)}
      </p>
    </article>
  );
}
