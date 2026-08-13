from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.core.cities import CITIES
from app.core.maps import (
    GOOGLE_MAPS_TRANSIT_DISCLAIMER,
    get_google_maps_transit_url,
)
from app.core.place_catalog import CATEGORY_DEFINITIONS
from app.llm.base import StructuredLLMProvider
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import ASSISTANT_RESPONSE_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from app.llm.schemas import DiscoveryIntent, GroundedClaim, GroundedResponse
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantEvidence,
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
    "tra questi",
    "fra questi",
    "il primo",
    "il secondo",
    "questo posto",
)

ITALIAN_TRANSIT_DISCLAIMER = (
    "Apri Google Maps per indicazioni aggiornate con i mezzi pubblici. Percorsi, "
    "orari di partenza, interruzioni e disponibilità possono cambiare; verifica "
    "le informazioni più recenti prima di partire."
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


def _refers_to_previous_places(message: str) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in CONTEXT_REFERENCE_TERMS)


def _explicit_categories(message: str) -> list[str]:
    """Find explicitly named catalog categories for validation and recovery."""

    normalized = message.casefold().replace("_", " ")
    matches: list[str] = []
    for definition in CATEGORY_DEFINITIONS:
        phrases = {
            definition.key.replace("_", " ").casefold(),
            definition.label.casefold(),
        }
        for phrase in tuple(phrases):
            phrases.add(f"{phrase}s")
            if phrase.endswith("y"):
                phrases.add(f"{phrase[:-1]}ies")
        if any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in phrases):
            matches.append(definition.key)
    return matches


def _requested_limit(message: str, categories: list[str]) -> int | None:
    """Extract an explicit count only when it modifies a selected category."""

    normalized = message.casefold().replace("_", " ")
    for category in categories:
        category_pattern = re.escape(category.replace("_", " ")) + "s?"
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
        prefix = "Categoria" if language == "it" else "Category"
        return f"{prefix}: {preferred.value}."[:240]
    label = preferred.field.replace("_", " ").capitalize()
    return f"{label}: {preferred.value}."[:240]


def _fallback_reason(place: RetrievedPlace, language: str) -> str:
    if place.place.description:
        return place.place.description[:240]
    prefix = "Categoria" if language == "it" else "Category"
    return f"{prefix}: {place.place.category.replace('_', ' ')}."


def _answer_text(*, count: int, language: str, fallback: bool) -> str:
    if language == "it":
        if count == 1:
            answer = "Ecco un luogo che potrebbe fare al caso tuo."
        elif count > 1:
            answer = f"Ecco {count} luoghi che potrebbero fare al caso tuo."
        else:
            answer = "Non ho trovato luoghi adatti alla tua richiesta."
        return answer

    if count == 1:
        answer = "Here is one place that could be a good match."
    elif count > 1:
        answer = f"Here are {count} places that could be a good match."
    else:
        answer = "I could not find a suitable place for that request."
    return answer


class AssistantService:
    def __init__(
        self,
        *,
        provider: StructuredLLMProvider,
        model: str,
        retriever: PlaceRetriever | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str = "bge-m3",
        evidence_retriever: EvidenceRetriever | None = None,
        evidence_limit: int = 8,
    ) -> None:
        self.provider = provider
        self.model = model
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
        last_error: Exception | None = None
        for attempt in range(2):
            retry_instruction = (
                "\nThe previous response was invalid or omitted an explicitly named "
                "supported category. Re-read the request and return corrected schema-only "
                "data, preserving explicit categories and result counts."
                if attempt
                else ""
            )
            try:
                intent_call = self.provider.generate_structured(
                    model=self.model,
                    system_prompt=INTENT_SYSTEM_PROMPT,
                    user_prompt=_conversation_prompt(request) + retry_instruction,
                    output_schema=DiscoveryIntent,
                )
                candidate = DiscoveryIntent.model_validate(intent_call.output)
                if explicit_categories and not set(explicit_categories).intersection(
                    candidate.categories
                ):
                    raise IntentValidationError(
                        "The model omitted an explicitly named supported category."
                    )
                intent = candidate
                if attempt:
                    warnings.append("Intent extraction succeeded after one model retry.")
                break
            except Exception as error:
                last_error = error

        if intent is None:
            logger.warning(
                "Assistant intent extraction failed after retry: %s",
                type(last_error).__name__ if last_error else "unknown",
            )
            provider_available = False
            warnings.append(
                "Il modello locale non era disponibile; CityBuddy ha usato filtri verificati."
                if request.language == "it"
                else "The local model was unavailable; CityBuddy used verified filters."
            )
            intent = DiscoveryIntent(
                city="turin", categories=explicit_categories, language=request.language
            )

        # Language is a user preference, not a fact for the model to infer.
        if intent.language != request.language:
            intent = intent.model_copy(update={"language": request.language})

        if _asks_for_transport(request.message) and not intent.wants_transport:
            constraints = list(intent.unsupported_constraints)
            if "live_transport" not in constraints:
                constraints.append("live_transport")
            intent = intent.model_copy(
                update={"wants_transport": True, "unsupported_constraints": constraints}
            )

        intent_updates: dict[str, Any] = {}
        if not intent.categories and explicit_categories:
            intent_updates["categories"] = explicit_categories
        explicit_limit = _requested_limit(
            request.message, intent.categories or explicit_categories
        )
        if explicit_limit is not None:
            intent_updates["limit"] = explicit_limit
        if request.radius_km is not None:
            intent_updates.update({"nearby": True, "radius_km": request.radius_km})
        if intent.city in CITIES and "unsupported_city" in intent.unsupported_constraints:
            intent_updates["unsupported_constraints"] = [
                item
                for item in intent.unsupported_constraints
                if item != "unsupported_city"
            ]
        if intent_updates:
            intent = intent.model_copy(update=intent_updates)

        if intent.city not in CITIES:
            return AssistantChatResponse(
                answer=(
                    "Al momento CityBuddy supporta solo Torino."
                    if request.language == "it"
                    else "CityBuddy currently supports Torino only."
                ),
                intent=intent,
                recommendations=[],
                grounded=True,
                provider_status="available" if provider_available else "fallback",
                warnings=warnings,
            )

        if intent.nearby and request.latitude is None:
            return AssistantChatResponse(
                answer=(
                    "Condividi la tua posizione per cercare luoghi nelle vicinanze."
                    if request.language == "it"
                    else "Share your location to search for nearby places."
                ),
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
            and _refers_to_previous_places(request.message)
        )
        evidence: list[RetrievedEvidence] = []
        semantic_place_ids: list[int] = []
        if self.embedding_provider is not None:
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
                warnings.append(
                    "La ricerca semantica non era disponibile; sono stati usati dati verificati."
                    if request.language == "it"
                    else "Semantic evidence was unavailable; verified place data was used."
                )

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
            warnings.append(
                "CityBuddy non può verificare se un luogo è aperto in questo momento; "
                "controlla le informazioni aggiornate prima della visita."
                if request.language == "it"
                else "CityBuddy cannot verify whether a place is open right now; "
                "check current information before visiting."
            )
        if "unverified_rating" in intent.unsupported_constraints:
            warnings.append(
                "CityBuddy non può verificare la valutazione o il premio esterno richiesto."
                if request.language == "it"
                else "CityBuddy cannot verify the requested external rating or award."
            )

        selected = places[: intent.limit]
        claims_by_place: dict[int, list[GroundedClaim]] = {}
        reasons_by_place: dict[int, str] = {}
        evidence_ids_by_place: dict[int, list[int]] = {}
        conversational_answer: str | None = None
        # A final grounded generation makes even a single result conversational.
        # Deterministic validation and fallback still own factual safety.
        if provider_available and places:
            try:
                response_call = self.provider.generate_structured(
                    model=self.model,
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
                    item.place_id: item.reason for item in grounded.recommendations
                }
                evidence_ids_by_place = {
                    item.place_id: item.evidence_ids
                    for item in grounded.recommendations
                }
                conversational_answer = grounded.summary
            except Exception as error:
                logger.warning(
                    "Assistant grounding validation failed: %s",
                    type(error).__name__,
                )
                provider_available = False
                warnings.append(
                    "Non sono riuscito a verificare una preferenza tra questi luoghi."
                    if request.language == "it" and contextual_follow_up
                    else "I could not verify a preference between those places."
                    if contextual_follow_up
                    else "CityBuddy used verified filters for these suggestions."
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
                evidence=[
                    AssistantEvidence(
                        id=item.id,
                        title=item.title,
                        excerpt=item.content[:500],
                        source_type=item.source_type,
                        source_url=item.source_url,
                        attribution=item.attribution,
                        license=item.license,
                    )
                    for item in evidence
                    if item.id in evidence_ids_by_place.get(place.place.id, [])
                ],
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
                (
                    ITALIAN_TRANSIT_DISCLAIMER
                    if request.language == "it"
                    else GOOGLE_MAPS_TRANSIT_DISCLAIMER
                )
                if intent.wants_transport
                else None
            ),
            warnings=warnings,
        )
