import type { Place } from "@/types/place";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type HealthResponse = {
  status: string;
  application: string;
  version: string;
};

type PlacesQuery = {
  category: string;
  city: string;
  limit: number;
  offset: number;
};

async function getJson<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    signal,
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  return getJson<HealthResponse>("/api/health", signal);
}

export function getPlaceCategories(
  signal?: AbortSignal,
): Promise<string[]> {
  return getJson<string[]>("/api/places/categories", signal);
}

export function getPlaces(
  query: PlacesQuery,
  signal?: AbortSignal,
): Promise<Place[]> {
  const parameters = new URLSearchParams({
    limit: query.limit.toString(),
    offset: query.offset.toString(),
  });

  if (query.category) {
    parameters.set("category", query.category);
  }

  if (query.city.trim()) {
    parameters.set("city", query.city.trim());
  }

  return getJson<Place[]>(
    `/api/places?${parameters.toString()}`,
    signal,
  );
}