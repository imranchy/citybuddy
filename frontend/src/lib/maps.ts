import type { Place } from "@/types/place";

export function getGoogleMapsUrl(place: Place): string {
  const location =
    place.address &&
    place.address !== "Address unavailable"
      ? `${place.name}, ${place.address}, ${place.city}`
      : `${place.name}, ${place.city}`;

  const parameters = new URLSearchParams({
    api: "1",
    query: location,
  });

  return `https://www.google.com/maps/search/?${parameters.toString()}`;
}

export function getGoogleDirectionsUrl(
  place: Place,
): string {
  const parameters = new URLSearchParams({
    api: "1",
    destination: `${place.latitude},${place.longitude}`,
    dir_action: "navigate",
  });

  return `https://www.google.com/maps/dir/?${parameters.toString()}`;
}