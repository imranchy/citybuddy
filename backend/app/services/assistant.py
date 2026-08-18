from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.core.cities import CITIES
from app.core.languages import fallback_text, language_name
from app.core.maps import get_google_maps_transit_url
from app.core.place_catalog import (
    canonicalize_category,
    category_terms,
    find_explicit_categories,
)
from app.llm.base import StructuredLLMProvider
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import ASSISTANT_RESPONSE_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from app.llm.schemas import (
    DiscoveryIntent,
    GroundedClaim,
    GroundedResponse,
    RawDiscoveryIntent,
)
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantRecommendation,
)
from app.services.place_types import RetrievedPlace
from app.services.rag import RetrievedEvidence

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


PlaceRetriever = Callable[..., list[RetrievedPlace]]
EvidenceRetriever = Callable[..., list[RetrievedEvidence]]

TRANSPORT_TERMS = (
    "public transport",
    "public transportation",
    "bus",
    "tram",
    "metro",
    "subway",
    "trasporto pubblico",
    "mezzi pubblici",
    "autobus",
    "pullman",
)

CONTEXT_REFERENCE_TERMS = (
    "which one",
    "which of",
    "among them",
    "of those",
    "the first",
    "the second",
    "this place",
    "that place",
    "quale",
    "quale dei",
    "quale delle",
    "tra questi",
    "fra questi",
    "il primo",
    "il secondo",
    "questo posto",
)

COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
}

FALLBACK_CITY_NAMES = {
    "turin": "turin",
    "torino": "turin",
    "lisbon": "lisbon",
    "lisbona": "lisbon",
}


NEARBY_TERMS = (
    "nearby",
    "near me",
    "around me",
    "close to me",
    "vicino a me",
    "vicini a me",
    "nelle vicinanze",
    "qui vicino",
)

LIVE_OPENING_PATTERNS = (
    r"\bopen (?:right )?now\b",
    r"\bcurrently open\b",
    r"\bapert[oi] (?:proprio )?(?:ora|adesso)\b",
    r"\bapert[ei] (?:proprio )?(?:ora|adesso)\b",
)

LIVE_AVAILABILITY_TERMS = (
    "available now",
    "current availability",
    "availability right now",
    "disponibile adesso",
    "disponibili adesso",
    "disponibilità attuale",
)

PRICE_TERMS = (
    "price",
    "prices",
    "cost",
    "costs",
    "how much",
    "cheap",
    "cheapest",
    "expensive",
    "free entry",
    "prezzo",
    "prezzi",
    "costo",
    "costa",
    "economico",
    "economica",
    "gratuito",
    "gratuita",
)

RATING_TERMS = (
    "rating",
    "rated",
    "best rated",
    "best-rated",
    "michelin",
    "starred",
    "stars",
    "valutazione",
    "valutazioni",
    "stelle",
)


class GroundingValidationError(RuntimeError):
    """Raised when a generated answer is not supported by retrieved records."""


class IntentValidationError(RuntimeError):
    """Raised when structured intent omits an explicit supported category."""


def _conversation_prompt(request: AssistantChatRequest) -> str:
    history = [message.model_dump() for message in request.history]
    return json.dumps(
        {
            "conversation_history": history,
            "current_user_message": request.message,
            "required_response_language": request.language,
        },
        ensure_ascii=False,
    )


def _asks_for_transport(message: str) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in TRANSPORT_TERMS)


def _asks_for_nearby(message: str) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in NEARBY_TERMS)


def _has_live_opening_request(message: str) -> bool:
    normalized = message.casefold()
    return any(re.search(pattern, normalized) for pattern in LIVE_OPENING_PATTERNS)


def _deterministic_constraints(
    message: str, city: str, *, wants_transport: bool = False
) -> list[str]:
    """Derive final safety/capability flags after semantic intent normalization."""

    normalized = message.casefold()
    constraints: list[str] = []

    if wants_transport or _asks_for_transport(message):
        constraints.append("live_transport")
    if _has_live_opening_request(message):
        constraints.append("live_opening_status")
    if any(term in normalized for term in LIVE_AVAILABILITY_TERMS):
        constraints.append("live_availability")
    if any(term in normalized for term in PRICE_TERMS):
        constraints.append("unverified_price")
    if any(term in normalized for term in RATING_TERMS):
        constraints.append("unverified_rating")
    if city not in CITIES:
        constraints.append("unsupported_city")

    return constraints


def _validated_city(message: str, model_city: str) -> str:
    """Keep an unsupported model city only when the user actually named it."""

    explicit_known = _fallback_city(message)
    normalized = message.casefold()
    if explicit_known != "turin" or re.search(r"\b(?:turin|torino)\b", normalized):
        return explicit_known
    if model_city in CITIES:
        return model_city
    if model_city and re.search(rf"\b{re.escape(model_city.casefold())}\b", normalized):
        return model_city
    return "turin"


def _refers_to_previous_places(message: str) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in CONTEXT_REFERENCE_TERMS)


def _explicit_categories(message: str) -> list[str]:
    """Find explicitly named catalog categories and configured aliases."""

    return find_explicit_categories(message)


def _requested_radius_km(message: str) -> float | None:
    """Extract an explicit kilometre radius from the user message."""

    normalized = message.casefold().replace(",", ".")
    match = re.search(
        r"\b(?:within|entro|nel raggio di|raggio di)?\s*(\d+(?:\.\d+)?)\s*"
        r"(?:km|kilomet(?:re|er)s?|chilometri?)\b",
        normalized,
    )
    if not match:
        return None

    radius = float(match.group(1))
    return radius if 0.1 <= radius <= 20.0 else None


def _requested_limit(message: str, categories: list[str]) -> int | None:
    """Extract an explicit count next to any configured term for a category."""

    normalized = " ".join(message.casefold().replace("_", " ").split())
    for category in categories:
        terms = category_terms(category) or (category.replace("_", " "),)
        for term in sorted(terms, key=len, reverse=True):
            category_pattern = re.escape(term)
            numeric_match = re.search(
                rf"\b(10|[1-9])\s+(?:\w+\s+)?{category_pattern}\b",
                normalized,
            )
            if numeric_match:
                return int(numeric_match.group(1))

            for word, count in COUNT_WORDS.items():
                if re.search(
                    rf"\b{re.escape(word)}\s+(?:\w+\s+)?{category_pattern}\b",
                    normalized,
                ):
                    return count

            if re.search(
                rf"\b(?:a|an|un|una)\s+{category_pattern}\b",
                normalized,
            ):
                return 1
    return None


def _fallback_city(message: str) -> str:
    """Recover explicit known city names without asking the model to infer them."""

    normalized = message.casefold()
    for city_name, city_key in FALLBACK_CITY_NAMES.items():
        if re.search(rf"\b{re.escape(city_name)}\b", normalized):
            return city_key
    return "turin"

def _canonical_model_categories(values: list[str]) -> list[str]:
    categories: list[str] = []
    for value in values:
        category = canonicalize_category(value)
        if category is not None and category not in categories:
            categories.append(category)
    return categories


def normalize_discovery_intent(
    request: AssistantChatRequest,
    intent: RawDiscoveryIntent | DiscoveryIntent,
) -> DiscoveryIntent:
    """Normalize advisory model output into strict application-owned intent."""

    explicit_categories = _explicit_categories(request.message)
    model_categories = _canonical_model_categories(intent.categories)
    categories = model_categories or explicit_categories
    validated_city = _validated_city(request.message, intent.city)
    explicit_radius = request.radius_km or _requested_radius_km(request.message)
    nearby = _asks_for_nearby(request.message) or explicit_radius is not None

    wants_transport = bool(intent.wants_transport) or _asks_for_transport(request.message)
    normalized = {
        "language": request.language,
        "city": validated_city,
        "categories": categories,
        "limit": _requested_limit(request.message, categories) or 5,
        "nearby": nearby,
        "radius_km": explicit_radius if nearby else None,
        "wants_transport": wants_transport,
        "unsupported_constraints": _deterministic_constraints(
            request.message,
            validated_city,
            wants_transport=wants_transport,
        ),
    }
    return DiscoveryIntent.model_validate(normalized)


def _record(place: RetrievedPlace) -> dict[str, Any]:
    record = place.place.model_dump(mode="json", exclude={"primary_image"})
    if place.distance_km is not None:
        record["distance_km"] = round(place.distance_km, 3)
    return record


def _grounding_prompt(
    request: AssistantChatRequest,
    intent: DiscoveryIntent,
    places: list[RetrievedPlace],
    evidence: list[RetrievedEvidence],
) -> str:
    return json.dumps(
        {
            "conversation_history": [item.model_dump() for item in request.history],
            "current_user_message": request.message,
            "validated_intent": intent.model_dump(),
            "required_response_language": intent.language,
            "required_response_language_name": language_name(intent.language),
            "retrieved_records": [_record(place) for place in places],
            "retrieved_evidence": [asdict(item) for item in evidence],
        },
        ensure_ascii=False,
    )


def _claim_is_supported(claim: GroundedClaim, record: dict[str, Any]) -> bool:
    if claim.field not in record or record[claim.field] is None:
        return False
    expected = record[claim.field]
    if isinstance(expected, (int, float)) and isinstance(claim.value, (int, float)):
        return float(expected) == float(claim.value)
    return claim.value == expected


def _validate_grounded_response(
    response: GroundedResponse,
    places: list[RetrievedPlace],
    evidence: list[RetrievedEvidence],
    result_limit: int,
) -> dict[int, list[GroundedClaim]]:
    records = {place.place.id: _record(place) for place in places}
    recommendation_ids = [item.place_id for item in response.recommendations]
    if len(recommendation_ids) != len(set(recommendation_ids)):
        raise GroundingValidationError("The model returned duplicate place IDs.")
    if len(recommendation_ids) > result_limit:
        raise GroundingValidationError("The model exceeded the requested result limit.")
    if not set(recommendation_ids).issubset(records):
        raise GroundingValidationError("The model referenced an unretrieved place.")
    if response.abstained and (response.recommendations or response.claims):
        raise GroundingValidationError("An abstention contained recommendations.")
    if not response.abstained and not response.recommendations:
        raise GroundingValidationError("A non-abstention omitted recommendations.")

    claims_by_place: dict[int, list[GroundedClaim]] = {}
    for claim in response.claims:
        record = records.get(claim.place_id)
        if record is None or not _claim_is_supported(claim, record):
            raise GroundingValidationError("The model returned an unsupported claim.")
        claims_by_place.setdefault(claim.place_id, []).append(claim)

    if any(place_id not in claims_by_place for place_id in recommendation_ids):
        raise GroundingValidationError("A recommendation had no supporting claim.")

    evidence_by_id = {item.id: item for item in evidence}
    evidence_place_ids = {item.place_id for item in evidence}
    for recommendation in response.recommendations:
        if any(
            evidence_id not in evidence_by_id
            or evidence_by_id[evidence_id].place_id != recommendation.place_id
            for evidence_id in recommendation.evidence_ids
        ):
            raise GroundingValidationError("A recommendation cited invalid evidence.")
        if (
            recommendation.place_id in evidence_place_ids
            and not recommendation.evidence_ids
        ):
            raise GroundingValidationError("Available evidence was not cited.")
    return claims_by_place


def _fact_reason(
    claims: list[GroundedClaim], place: RetrievedPlace, language: str
) -> str:
    preferred = next(
        (claim for claim in claims if claim.field == "description"),
        next((claim for claim in claims if claim.field == "category"), claims[0]),
    )
    if preferred.field == "description":
        return str(preferred.value)[:240]
    if preferred.field == "category":
        return fallback_text(language, "verified_place")[:240]
    label = preferred.field.replace("_", " ").capitalize()
    return f"{label}: {preferred.value}."[:240]


def _sanitize_user_text(text: str) -> str:
    """Remove internal structured identifiers from user-visible model prose."""

    sanitized = re.sub(
        r"\s*\(?\b(?:place\s+)?id\s*[:#]?\s*\d+\)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"\s+([,.;:!?])", r"\1", sanitized)
    return " ".join(sanitized.split())


def _fallback_reason(place: RetrievedPlace, language: str) -> str:
    # Database descriptions are not guaranteed to match the selected UI language.
    # In model-free fallback mode, prefer a short localized category label rather
    # than leaking source-language prose into a different selected language.
    return fallback_text(language, "verified_place")


def _answer_text(*, count: int, language: str, fallback: bool) -> str:
    if count == 1:
        return fallback_text(language, "one_place")
    if count > 1:
        return fallback_text(language, "many_places", count=count)
    return fallback_text(language, "no_places")


class AssistantService:
    def __init__(
        self,
        *,
        provider: StructuredLLMProvider,
        intent_model: str | None = None,
        response_model: str | None = None,
        model: str | None = None,
        retriever: PlaceRetriever | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str = "bge-m3",
        evidence_retriever: EvidenceRetriever | None = None,
        evidence_limit: int = 8,
    ) -> None:
        # ``model`` remains as a compatibility path for tests and external code
        # written before model routing was introduced. Production configuration
        # supplies the two explicit roles.
        if model is None and (intent_model is None or response_model is None):
            raise ValueError(
                "Provide intent_model and response_model, or the legacy model argument."
            )
        self.provider = provider
        self.intent_model = intent_model or model
        self.response_model = response_model or model
        self.retriever = retriever
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.evidence_retriever = evidence_retriever
        self.evidence_limit = evidence_limit

    def respond(
        self,
        database: Session,
        request: AssistantChatRequest,
    ) -> AssistantChatResponse:
        warnings: list[str] = []
        provider_available = True
        explicit_categories = _explicit_categories(request.message)
        intent: DiscoveryIntent | None = None
        model_refers_to_context = False
        model_needs_semantic_retrieval = False
        last_error: Exception | None = None
        intent_attempt_models = [self.intent_model, self.intent_model]
        if self.response_model != self.intent_model:
            intent_attempt_models.append(self.response_model)
        for attempt, intent_model in enumerate(intent_attempt_models):
            retry_instruction = (
                "\nThe previous response was invalid or omitted an explicitly named "
                "supported category. Re-read the request and return corrected schema-only "
                "data, preserving explicit categories and result counts."
                if attempt
                else ""
            )
            try:
                intent_call = self.provider.generate_structured(
                    model=intent_model,
                    system_prompt=INTENT_SYSTEM_PROMPT,
                    user_prompt=_conversation_prompt(request) + retry_instruction,
                    output_schema=RawDiscoveryIntent,
                )
                raw_payload = (
                    intent_call.output.model_dump()
                    if hasattr(intent_call.output, "model_dump")
                    else intent_call.output
                )
                raw_candidate = RawDiscoveryIntent.model_validate(raw_payload)
                raw_categories = _canonical_model_categories(raw_candidate.categories)
                if explicit_categories and not set(explicit_categories).intersection(
                    raw_categories
                ):
                    raise IntentValidationError(
                        "The model omitted an explicitly named supported category."
                    )
                candidate = normalize_discovery_intent(request, raw_candidate)
                if explicit_categories and not set(explicit_categories).intersection(
                    candidate.categories
                ):
                    raise IntentValidationError(
                        "The model omitted an explicitly named supported category."
                    )
                intent = candidate
                model_refers_to_context = raw_candidate.refers_to_context
                model_needs_semantic_retrieval = raw_candidate.needs_semantic_retrieval
                if (
                    intent_model == self.response_model
                    and self.response_model != self.intent_model
                ):
                    warnings.append(fallback_text(request.language, "intent_recovered"))
                elif attempt:
                    warnings.append(fallback_text(request.language, "intent_retry"))
                break
            except Exception as error:
                last_error = error

        if intent is None:
            logger.warning(
                "Assistant intent extraction failed after retry: %s",
                type(last_error).__name__ if last_error else "unknown",
            )
            provider_available = False
            warnings.append(fallback_text(request.language, "model_unavailable"))
            fallback_city = _fallback_city(request.message)
            fallback_raw = RawDiscoveryIntent(
                city=fallback_city,
                categories=explicit_categories,
                language=request.language,
            )
            intent = normalize_discovery_intent(request, fallback_raw)

        if intent.city not in CITIES:
            return AssistantChatResponse(
                answer=fallback_text(request.language, "unsupported_city"),
                intent=intent,
                recommendations=[],
                grounded=True,
                provider_status="available" if provider_available else "fallback",
                warnings=warnings,
            )

        if intent.nearby and request.latitude is None:
            return AssistantChatResponse(
                answer=fallback_text(request.language, "location_required"),
                intent=intent,
                recommendations=[],
                grounded=True,
                provider_status="available" if provider_available else "fallback",
                warnings=warnings,
            )

        retriever = self.retriever
        if retriever is None:
            from app.services.place_discovery import retrieve_places

            retriever = retrieve_places

        contextual_follow_up = bool(
            request.context_place_ids
            and (model_refers_to_context or _refers_to_previous_places(request.message))
        )
        use_semantic_retrieval = bool(
            self.embedding_provider is not None
            and (
                model_needs_semantic_retrieval
                or contextual_follow_up
                or not explicit_categories
            )
        )
        evidence: list[RetrievedEvidence] = []
        semantic_place_ids: list[int] = []
        if use_semantic_retrieval:
            evidence_retriever = self.evidence_retriever
            if evidence_retriever is None:
                from app.services.rag import retrieve_evidence

                evidence_retriever = retrieve_evidence
            try:
                query_vector = self.embedding_provider.embed(
                    model=self.embedding_model,
                    texts=[request.message],
                )[0]
                evidence = evidence_retriever(
                    database,
                    query_embedding=query_vector,
                    city=intent.city,
                    categories=intent.categories,
                    place_ids=(
                        request.context_place_ids if contextual_follow_up else None
                    ),
                    latitude=request.latitude if intent.nearby else None,
                    longitude=request.longitude if intent.nearby else None,
                    radius_km=request.radius_km or intent.radius_km,
                    limit=self.evidence_limit,
                )
                semantic_place_ids = list(
                    dict.fromkeys(item.place_id for item in evidence)
                )
            except Exception as error:
                logger.warning(
                    "Assistant evidence retrieval failed: %s", type(error).__name__
                )
                warnings.append(fallback_text(request.language, "semantic_unavailable"))

        # Semantic search runs across every eligible indexed place before this
        # controlled candidate shortlist is materialized.
        candidate_ids = (
            semantic_place_ids
            or (request.context_place_ids if contextual_follow_up else None)
        )
        candidate_limit = min(
            max(len(semantic_place_ids), intent.limit), 10
        )
        places = retriever(
            database,
            city=intent.city,
            categories=intent.categories,
            limit=candidate_limit,
            latitude=request.latitude if intent.nearby else None,
            longitude=request.longitude if intent.nearby else None,
            radius_km=request.radius_km or intent.radius_km,
            place_ids=candidate_ids,
        )
        if semantic_place_ids:
            semantic_order = {
                place_id: index for index, place_id in enumerate(semantic_place_ids)
            }
            places.sort(
                key=lambda item: semantic_order.get(
                    item.place.id, len(semantic_order)
                )
            )
        retrieved_ids = {place.place.id for place in places}
        evidence = [item for item in evidence if item.place_id in retrieved_ids]

        if "live_opening_status" in intent.unsupported_constraints:
            warnings.append(fallback_text(request.language, "opening_unavailable"))
        if "unverified_rating" in intent.unsupported_constraints:
            warnings.append(fallback_text(request.language, "rating_unavailable"))

        selected = places[: intent.limit]
        claims_by_place: dict[int, list[GroundedClaim]] = {}
        reasons_by_place: dict[int, str] = {}
        conversational_answer: str | None = None
        # A final grounded generation makes even a single result conversational.
        # Deterministic validation and fallback still own factual safety.
        if provider_available and places:
            try:
                response_call = self.provider.generate_structured(
                    model=self.response_model,
                    system_prompt=ASSISTANT_RESPONSE_SYSTEM_PROMPT,
                    user_prompt=_grounding_prompt(request, intent, places, evidence),
                    output_schema=GroundedResponse,
                )
                grounded = GroundedResponse.model_validate(response_call.output)
                claims_by_place = _validate_grounded_response(
                    grounded, places, evidence, intent.limit
                )
                selected_by_id = {place.place.id: place for place in places}
                selected = [
                    selected_by_id[item.place_id]
                    for item in grounded.recommendations
                ]
                reasons_by_place = {
                    item.place_id: _sanitize_user_text(item.reason) for item in grounded.recommendations
                }
                conversational_answer = _sanitize_user_text(grounded.summary)
            except Exception as error:
                logger.warning(
                    "Assistant grounding validation failed: %s",
                    type(error).__name__,
                )
                provider_available = False
                warnings.append(
                    fallback_text(
                        request.language,
                        "context_unverified" if contextual_follow_up else "verified_filters",
                    )
                )
                if contextual_follow_up:
                    selected = []

        recommendations = [
            AssistantRecommendation(
                place=place.place,
                reason=(
                    reasons_by_place.get(place.place.id)
                    or (
                        _fact_reason(
                            claims_by_place[place.place.id], place, request.language
                        )
                        if place.place.id in claims_by_place
                        else _fallback_reason(place, request.language)
                    )
                ),
                distance_km=place.distance_km,
                transit_url=(
                    get_google_maps_transit_url(
                        place.place.latitude,
                        place.place.longitude,
                    )
                    if intent.wants_transport
                    else None
                ),
            )
            for place in selected
        ]
        return AssistantChatResponse(
            answer=conversational_answer or _answer_text(
                count=len(recommendations),
                language=intent.language,
                fallback=not provider_available,
            ),
            intent=intent,
            recommendations=recommendations,
            grounded=True,
            provider_status="available" if provider_available else "fallback",
            transport_disclaimer=(
                fallback_text(request.language, "transit_disclaimer")
                if intent.wants_transport
                else None
            ),
            warnings=warnings,
        )
