import type { Language } from "@/types/language";
import type { Place } from "@/types/place";

export type ConversationMessage = {
  role: "user" | "assistant";
  content: string;
};

export type DiscoveryIntent = {
  city: string;
  categories: string[];
  limit: number;
  nearby: boolean;
  radius_km: number | null;
  wants_transport: boolean;
  language: string;
  request_language?: string;
  category_limits?: Record<string, number>;
  preferences?: string[];
  goal?: "recommend" | "describe" | "compare" | "itinerary" | "answer";
  tool_intent?: string;
  target_place_name?: string | null;
  unsupported_constraints: string[];
};

export type AssistantRecommendation = {
  place: Place;
  reason: string;
  distance_km: number | null;
  transit_url: string | null;
};


export type AssistantChatRequest = {
  message: string;
  language: Language;
  history: ConversationMessage[];
  context_place_ids: number[];
  latitude?: number;
  longitude?: number;
  radius_km?: number;
};

export type AssistantChatResponse = {
  answer: string;
  intent: DiscoveryIntent;
  recommendations: AssistantRecommendation[];
  grounded: boolean;
  provider_status: "available" | "fallback";
  transport_disclaimer: string | null;
  warnings: string[];
};
