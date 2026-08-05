import type { Place } from "@/types/place";
import {
  getGoogleDirectionsUrl,
  getGoogleMapsUrl,
} from "@/lib/maps";

type PlaceCardProps = {
  place: Place;
};

export default function PlaceCard({ place }: PlaceCardProps) {
  const googleMapsUrl = getGoogleMapsUrl(place);
  const directionsUrl = getGoogleDirectionsUrl(place);
  return (
    <article className="rounded-3xl border border-white/10 bg-[#121936] p-6 transition duration-200 hover:-translate-y-1 hover:border-[#FF6846]/40 sm:p-7">
      <div className="flex items-start justify-between gap-4">
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