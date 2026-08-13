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
  unsupported_constraints: string[];
};

export type AssistantRecommendation = {
  place: Place;
  reason: string;
  distance_km: number | null;
  transit_url: string | null;
  evidence: AssistantEvidence[];
};

export type AssistantEvidence = {
  id: number;
  title: string;
  excerpt: string;
  source_type: string;
  source_url: string | null;
  attribution: string | null;
  license: string | null;
};

export type AssistantChatRequest = {
  message: string;
  language: "en" | "it";
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
