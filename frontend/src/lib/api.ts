import type { CategoryGroup, Place } from "@/types/place";
import type {
  AssistantChatRequest,
  AssistantChatResponse,
} from "@/types/assistant";

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

type NearbyPlacesQuery = {
  latitude: number;
  longitude: number;
  radiusKm: number;
  category: string;
  limit: number;
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

async function postJson<ResponseT, RequestT>(
  path: string,
  body: RequestT,
  signal?: AbortSignal,
): Promise<ResponseT> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  return response.json() as Promise<ResponseT>;
}

export function getHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  return getJson<HealthResponse>("/api/health", signal);
}

export function getPlaceCategories(
  signal?: AbortSignal,
): Promise<CategoryGroup[]> {
  return getJson<CategoryGroup[]>("/api/places/categories", signal);
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

export function getNearbyPlaces(
  query: NearbyPlacesQuery,
  signal?: AbortSignal,
): Promise<Place[]> {
  const parameters = new URLSearchParams({
    latitude: query.latitude.toString(),
    longitude: query.longitude.toString(),
    radius_km: query.radiusKm.toString(),
    limit: query.limit.toString(),
  });

  if (query.category) {
    parameters.set("category", query.category);
  }

  return getJson<Place[]>(
    `/api/places/nearby?${parameters.toString()}`,
    signal,
  );
}

export function sendAssistantMessage(
  request: AssistantChatRequest,
  signal?: AbortSignal,
): Promise<AssistantChatResponse> {
  return postJson<AssistantChatResponse, AssistantChatRequest>(
    "/api/assistant/chat",
    request,
    signal,
  );
}
