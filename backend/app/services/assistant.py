from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import asdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.core.cities import CITIES, CITY_ALIASES
from app.core.languages import SUPPORTED_LANGUAGE_CODES, fallback_text, language_name
from app.core.maps import get_google_maps_transit_url
from app.core.place_catalog import canonicalize_category
from app.llm.base import StructuredLLMProvider
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import (
    ASSISTANT_RESPONSE_SYSTEM_PROMPT,
    PLAN_SYNTHESIS_SYSTEM_PROMPT,
    SEMANTIC_PLANNER_SYSTEM_PROMPT,
    TOOL_RESPONSE_SYSTEM_PROMPT,
)
from app.llm.schemas import (
    DiscoveryIntent,
    GroundedClaim,
    GroundedResponse,
    PlanSynthesisResponse,
    PlannerTask,
    SemanticPlan,
    ToolGroundedResponse,
)
from app.schemas.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantRecommendation,
)
from app.services.place_types import RetrievedPlace
from app.services.rag import RetrievedEvidence
from app.services.official_site import OfficialPageType, OfficialSiteEvidence
from app.services.weather import WeatherForecast
from app.tools.weather import WeatherRequest

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


PlaceRetriever = Callable[..., list[RetrievedPlace]]
EvidenceRetriever = Callable[..., list[RetrievedEvidence]]
WeatherTool = Callable[[WeatherRequest], WeatherForecast]
OfficialSiteTool = Callable[..., OfficialSiteEvidence]



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
            "ui_language": request.language,
            "supported_response_languages": list(SUPPORTED_LANGUAGE_CODES),
        },
        ensure_ascii=False,
    )


def _normalized_plan_city(city: str) -> str:
    normalized = " ".join(city.strip().casefold().split()) or "turin"
    return CITY_ALIASES.get(normalized, normalized)


def _deterministic_constraints(city: str, *, wants_transport: bool = False) -> list[str]:
    """Return only application-owned capability constraints.

    Language understanding belongs to Qwen. Python validates supported city/tool
    boundaries and does not parse multilingual wording.
    """

    constraints: list[str] = []
    if wants_transport:
        constraints.append("live_transport")
    if city not in CITIES:
        constraints.append("unsupported_city")
    return constraints


def _validated_target_place_name(message: str, target_name: str | None) -> str | None:
    """Accept an explicitly named place, but never confuse the city with a place target."""

    if not target_name:
        return None
    normalized_message = " ".join(message.casefold().split())
    normalized_target = " ".join(target_name.casefold().split())
    if not normalized_target or normalized_target not in normalized_message:
        return None

    city_names = set(CITIES)
    city_names.update(CITY_ALIASES)
    city_names.update(alias.casefold() for alias in CITY_ALIASES.values())
    city_names.update(config.display_name.casefold() for config in CITIES.values())
    if normalized_target in city_names:
        return None
    return target_name.strip()


def _planned_task_intent(
    request: AssistantChatRequest,
    plan: SemanticPlan,
    task: PlannerTask,
) -> DiscoveryIntent:
    """Validate one Qwen planner task into application-owned retrieval fields.

    Qwen owns multilingual interpretation. The application only canonicalizes catalog
    keys, validates bounds, preserves explicit application-known constraints when
    available, and maps the bounded task type onto an allowlisted tool route.
    """

    categories: list[str] = []
    category_limits: dict[str, int] = {}
    for item in task.categories:
        category = canonicalize_category(item.category)
        if category is None:
            raise IntentValidationError(
                f"Planner returned unsupported CityBuddy category: {item.category}"
            )
        if category not in categories:
            categories.append(category)
        if item.quantity is not None:
            category_limits[category] = item.quantity

    if category_limits and len(category_limits) == len(categories):
        limit = min(sum(category_limits.values()), 10)
    elif len(categories) == 1 and categories[0] in category_limits:
        limit = category_limits[categories[0]]
    else:
        limit = 5

    response_language = (
        plan.response_language
        if plan.response_language in SUPPORTED_LANGUAGE_CODES
        else request.language
    )
    city = _normalized_plan_city(plan.city)
    radius = request.radius_km if request.radius_km is not None else task.radius_km
    target_name = _validated_target_place_name(request.message, task.target_place_name)

    constraints = _deterministic_constraints(
        city, wants_transport=task.wants_transport
    )

    return DiscoveryIntent.model_validate(
        {
            "city": city,
            "categories": categories,
            "limit": limit,
            "nearby": bool(task.nearby or radius is not None),
            "radius_km": radius if (task.nearby or radius is not None) else None,
            "wants_transport": task.wants_transport,
            "language": response_language,
            "request_language": plan.request_language,
            "category_limits": category_limits,
            "preferences": task.preferences,
            "goal": task.goal,
            "tool_intent": task.task_type,
            "target_place_name": target_name,
            "forecast_hours": task.forecast_hours,
            "unsupported_constraints": constraints,
        }
    )


def _record(place: RetrievedPlace) -> dict[str, Any]:
    record = place.place.model_dump(mode="json", exclude={"primary_image"})
    if place.distance_km is not None:
        record["distance_km"] = round(place.distance_km, 3)
    return record


def _place_fact_records(database: Any, place_ids: list[int]) -> list[dict[str, Any]]:
    """Return approved typed facts for the already-retrieved place set.

    Failure is deliberately non-fatal: structured facts enrich Gemma's context but do
    not replace reviewed place/RAG retrieval.
    """
    if not place_ids:
        return []
    try:
        from sqlalchemy import select
        from app.models.place_fact import PlaceFact

        rows = database.scalars(
            select(PlaceFact)
            .where(
                PlaceFact.place_id.in_(place_ids),
                PlaceFact.review_status == "approved",
            )
            .order_by(PlaceFact.place_id, PlaceFact.fact_type)
        ).all()
        return [
            {
                "place_id": row.place_id,
                "fact_type": row.fact_type,
                "value": row.value,
                "source_url": row.source_url,
                "source_fetched_at": (
                    row.source_fetched_at.isoformat()
                    if row.source_fetched_at is not None
                    else None
                ),
                "evidence_excerpt": row.evidence_excerpt,
            }
            for row in rows
        ]
    except Exception:
        return []


def _grounding_prompt(
    request: AssistantChatRequest,
    intent: DiscoveryIntent,
    places: list[RetrievedPlace],
    evidence: list[RetrievedEvidence],
    place_facts: list[dict[str, Any]] | None = None,
) -> str:
    return json.dumps(
        {
            "conversation_history": [item.model_dump() for item in request.history],
            "current_user_message": request.message,
            "validated_intent": intent.model_dump(),
            "category_quotas": intent.category_limits,
            "required_response_language": intent.language,
            "required_response_language_name": language_name(intent.language),
            "retrieved_records": [_record(place) for place in places],
            "retrieved_evidence": [asdict(item) for item in evidence],
            "structured_place_facts": place_facts or [],
            "application_time_context": _city_time_facts(intent),
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


def _normalize_grounded_response(
    response: GroundedResponse,
    places: list[RetrievedPlace],
    evidence: list[RetrievedEvidence],
    result_limit: int,
) -> tuple[GroundedResponse, dict[int, list[GroundedClaim]], list[str]]:
    """Repair harmless model mistakes while keeping grounding fail-closed.

    Structural mistakes such as duplicate recommendations, excessive result counts,
    unsupported claims, and bad evidence references are recoverable because the
    application can deterministically remove them. A response is rejected only when
    no usable retrieved recommendation remains or when it explicitly abstains without
    providing a usable recommendation.
    """

    records = {place.place.id: _record(place) for place in places}
    evidence_by_id = {item.id: item for item in evidence}
    repairs: list[str] = []

    normalized_recommendations = []
    seen_place_ids: set[int] = set()
    for recommendation in response.recommendations:
        if recommendation.place_id not in records:
            repairs.append("dropped_unretrieved_place")
            continue
        if recommendation.place_id in seen_place_ids:
            repairs.append("deduplicated_place")
            continue
        seen_place_ids.add(recommendation.place_id)

        valid_evidence_ids = [
            evidence_id
            for evidence_id in recommendation.evidence_ids
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id].place_id == recommendation.place_id
        ]
        if valid_evidence_ids != recommendation.evidence_ids:
            repairs.append("removed_invalid_evidence")

        normalized_recommendations.append(
            recommendation.model_copy(update={"evidence_ids": valid_evidence_ids})
        )
        if len(normalized_recommendations) >= result_limit:
            if len(response.recommendations) > len(normalized_recommendations):
                repairs.append("truncated_to_result_limit")
            break

    claims_by_place: dict[int, list[GroundedClaim]] = {}
    selected_ids = {item.place_id for item in normalized_recommendations}
    for claim in response.claims:
        record = records.get(claim.place_id)
        if (
            claim.place_id not in selected_ids
            or record is None
            or not _claim_is_supported(claim, record)
        ):
            repairs.append("removed_unsupported_claim")
            continue
        claims_by_place.setdefault(claim.place_id, []).append(claim)

    if not normalized_recommendations:
        if response.abstained:
            return (
                response.model_copy(update={"recommendations": [], "claims": []}),
                {},
                repairs,
            )
        raise GroundingValidationError(
            "The model returned no usable recommendations from retrieved records."
        )

    if response.abstained:
        repairs.append("ignored_inconsistent_abstention")

    normalized_claims = [
        claim
        for claims in claims_by_place.values()
        for claim in claims
    ]
    normalized = response.model_copy(
        update={
            "recommendations": normalized_recommendations,
            "claims": normalized_claims,
            "abstained": False,
        }
    )
    return normalized, claims_by_place, list(dict.fromkeys(repairs))


def _repair_category_quota_selection(
    recommendation_ids: list[int],
    places: list[RetrievedPlace],
    category_quotas: dict[str, int],
    result_limit: int,
) -> tuple[list[int], bool]:
    """Preserve valid model ranking, then fill quota shortfalls deterministically."""

    by_id = {item.place.id: item for item in places}
    selected: list[int] = []
    counts = {category: 0 for category in category_quotas}

    for place_id in recommendation_ids:
        place = by_id.get(place_id)
        if place is None:
            continue
        category = place.place.category
        if category in counts and counts[category] >= category_quotas[category]:
            continue
        selected.append(place_id)
        if category in counts:
            counts[category] += 1
        if len(selected) >= result_limit:
            break

    repaired = selected != recommendation_ids[:result_limit]
    for category, quota in category_quotas.items():
        if counts[category] >= quota:
            continue
        for place in places:
            if place.place.category != category or place.place.id in selected:
                continue
            selected.append(place.place.id)
            counts[category] += 1
            repaired = True
            if counts[category] >= quota or len(selected) >= result_limit:
                break

    return selected[:result_limit], repaired


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


def _tool_prompt(
    request: AssistantChatRequest,
    intent: DiscoveryIntent,
    *,
    tool_name: str,
    evidence: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "conversation_history": [item.model_dump() for item in request.history],
            "current_user_message": request.message,
            "validated_intent": intent.model_dump(),
            "required_response_language": intent.language,
            "required_response_language_name": language_name(intent.language),
            "tool_name": tool_name,
            "tool_evidence": evidence,
        },
        ensure_ascii=False,
        default=str,
    )


def _weather_claims(forecast: WeatherForecast) -> dict[str, Any]:
    payload = forecast.model_dump(mode="json")
    current = payload["current"]
    facts: dict[str, Any] = {
        "city": payload["city"],
        "timezone": payload["timezone"],
        "forecast_hours": payload["forecast_hours"],
        "current.time": current["time"],
        "current.air_temperature_c": current["air_temperature_c"],
        "current.relative_humidity_percent": current["relative_humidity_percent"],
        "current.wind_speed_mps": current["wind_speed_mps"],
        "current.precipitation_amount_mm": current["precipitation_amount_mm"],
        "current.symbol_code": current["symbol_code"],
    }
    for index, point in enumerate(payload["forecast"]):
        prefix = f"forecast.{index}"
        for field in (
            "time",
            "air_temperature_c",
            "relative_humidity_percent",
            "wind_speed_mps",
            "precipitation_amount_mm",
            "symbol_code",
        ):
            facts[f"{prefix}.{field}"] = point[field]
    return facts


OFFICIAL_EVIDENCE_HINTS: dict[OfficialPageType, tuple[str, ...]] = {
    "general": (),
    "menu": (
        "menu", "carta", "food", "drink", "dish", "piatto", "veget",
        "vegan", "halal", "allergen", "allergeni", "gluten", "senza",
    ),
    "exhibitions": ("exhibition", "exhibit", "mostra", "mostre", "event", "eventi"),
    "prices": ("price", "pricing", "prezzo", "prezzi", "ticket", "bigliett", "euro", "€"),
    "opening_info": (
        "opening", "hours", "orari", "apert", "chius", "closed", "open",
        "ingresso",
    ),
}


def _official_query_terms(message: str) -> tuple[str, ...]:
    words = re.findall(r"[\wÀ-ÿ]+", message.casefold(), flags=re.UNICODE)
    ignored = {
        "the", "and", "for", "with", "that", "this", "what", "does", "have",
        "are", "there", "any", "can", "you", "about", "from", "into", "their",
    }
    return tuple(dict.fromkeys(word for word in words if len(word) >= 3 and word not in ignored))[:24]


def _relevant_official_excerpt(
    text: str | None,
    *,
    message: str,
    page_type: OfficialPageType,
    max_chars: int = 4_500,
) -> str | None:
    """Select a compact verbatim window from verified official-site text."""

    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    terms = tuple(dict.fromkeys((*OFFICIAL_EVIDENCE_HINTS[page_type], *_official_query_terms(message))))
    scored: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        score = sum(1 for term in terms if term in lowered)
        if score:
            scored.append((-score, index))

    if not scored:
        return "\n".join(lines)[:max_chars].rstrip()

    scored.sort()
    selected: set[int] = set()
    for _, index in scored[:10]:
        for candidate in range(max(0, index - 2), min(len(lines), index + 3)):
            selected.add(candidate)

    excerpt_lines: list[str] = []
    length = 0
    for index in sorted(selected):
        line = lines[index]
        addition = len(line) + (1 if excerpt_lines else 0)
        if length + addition > max_chars:
            break
        excerpt_lines.append(line)
        length += addition
    return "\n".join(excerpt_lines).strip() or "\n".join(lines)[:max_chars].rstrip()


def _normalized_evidence_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _city_time_facts(intent: DiscoveryIntent) -> dict[str, str]:
    city = CITIES.get(intent.city)
    if city is None:
        return {}
    local_now = datetime.now(ZoneInfo(city.timezone))
    return {
        "city_local_date": local_now.date().isoformat(),
        "city_local_weekday": local_now.strftime("%A"),
        "city_timezone": city.timezone,
    }


def _validate_tool_grounding(
    response: ToolGroundedResponse,
    *,
    facts: dict[str, Any],
    official_text: str | None = None,
    must_abstain: bool = False,
) -> None:
    if must_abstain and not response.abstained:
        raise GroundingValidationError("Unverified live evidence did not abstain.")
    if response.abstained:
        if response.claims:
            raise GroundingValidationError("A live-tool abstention contained claims.")
        return
    if not response.claims:
        raise GroundingValidationError("A live-tool answer omitted supporting claims.")
    for claim in response.claims:
        if claim.field == "text_excerpt":
            if (
                not isinstance(claim.value, str)
                or not official_text
                or _normalized_evidence_text(claim.value)
                not in _normalized_evidence_text(official_text)
            ):
                raise GroundingValidationError("Official-site excerpt was unsupported.")
            continue
        if claim.field not in facts or facts[claim.field] != claim.value:
            raise GroundingValidationError("Live-tool claim was unsupported.")


def _official_page_type(tool_intent: str) -> OfficialPageType:
    mapping: dict[str, OfficialPageType] = {
        "official_opening": "opening_info",
        "official_menu": "menu",
        "official_exhibitions": "exhibitions",
        "official_prices": "prices",
        "official_info": "general",
    }
    return mapping[tool_intent]


def _select_official_target(
    places: list[RetrievedPlace],
    *,
    target_name: str | None,
    context_place_ids: list[int],
) -> RetrievedPlace | None:
    # An explicitly named place in the current message always outranks earlier
    # conversation context. Context is only the fallback for "it/there/the first".
    if target_name:
        normalized = " ".join(target_name.casefold().split())
        exact = [
            item
            for item in places
            if " ".join(item.place.name.casefold().split()) == normalized
        ]
        if len(exact) == 1:
            return exact[0]
        partial = [
            item
            for item in places
            if normalized in item.place.name.casefold()
            or item.place.name.casefold() in normalized
        ]
        if len(partial) == 1:
            return partial[0]

    if len(context_place_ids) == 1:
        contextual = next(
            (item for item in places if item.place.id == context_place_ids[0]),
            None,
        )
        if contextual is not None:
            return contextual

    return places[0] if len(places) == 1 else None


class AssistantService:
    def __init__(
        self,
        *,
        planner_provider: StructuredLLMProvider,
        response_provider: StructuredLLMProvider,
        planner_model: str,
        response_model: str,
        retriever: PlaceRetriever | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str = "bge-m3",
        evidence_retriever: EvidenceRetriever | None = None,
        evidence_limit: int = 16,
        weather_tool: WeatherTool | None = None,
        official_site_tool: OfficialSiteTool | None = None,
    ) -> None:
        self.planner_provider = planner_provider
        self.response_provider = response_provider
        self.planner_model = planner_model
        self.response_model = response_model
        self.retriever = retriever
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.evidence_retriever = evidence_retriever
        self.evidence_limit = evidence_limit
        self.weather_tool = weather_tool
        self.official_site_tool = official_site_tool

    def _live_answer(
        self,
        request: AssistantChatRequest,
        intent: DiscoveryIntent,
        *,
        tool_name: str,
        evidence: dict[str, Any],
        facts: dict[str, Any],
        official_text: str | None = None,
        must_abstain: bool = False,
    ) -> str | None:
        try:
            response_call = self.response_provider.generate_structured(
                model=self.response_model,
                system_prompt=TOOL_RESPONSE_SYSTEM_PROMPT,
                user_prompt=_tool_prompt(
                    request,
                    intent,
                    tool_name=tool_name,
                    evidence=evidence,
                ),
                output_schema=ToolGroundedResponse,
            )
            grounded = ToolGroundedResponse.model_validate(response_call.output)
            _validate_tool_grounding(
                grounded,
                facts=facts,
                official_text=official_text,
                must_abstain=must_abstain,
            )
            return _sanitize_user_text(grounded.answer)
        except Exception as error:
            logger.warning(
                "Assistant live-tool grounding failed for %s: %s",
                tool_name,
                type(error).__name__,
            )
            return None

    def _plan_request(
        self,
        request: AssistantChatRequest,
    ) -> tuple[SemanticPlan | None, list[str], bool]:
        """Ask Qwen for one multilingual semantic plan with bounded retry/escalation."""

        warnings: list[str] = []
        last_error: Exception | None = None
        attempt_models = [self.planner_model, self.planner_model]
        if self.response_model != self.planner_model:
            attempt_models.append(self.response_model)

        for attempt, planner_model in enumerate(attempt_models):
            retry_instruction = (
                "\nThe previous plan was invalid. Re-read the current message and "
                "return corrected schema-only data. Preserve explicit quantities, "
                "language instructions, task order, place references, and categories."
                if attempt
                else ""
            )
            try:
                active_provider = (
                    self.response_provider
                    if planner_model == self.response_model and self.response_model != self.planner_model
                    else self.planner_provider
                )
                call = active_provider.generate_structured(
                    model=planner_model,
                    system_prompt=SEMANTIC_PLANNER_SYSTEM_PROMPT,
                    user_prompt=_conversation_prompt(request) + retry_instruction,
                    output_schema=SemanticPlan,
                )
                output = call.output
                payload = output.model_dump() if hasattr(output, "model_dump") else output
                plan = SemanticPlan.model_validate(payload)
                # Schema validity is not enough: retry when the planner proposes an
                # unsupported category/city/task combination. This remains language-
                # independent application validation, not a second NLP parser.
                for task in plan.tasks:
                    _planned_task_intent(request, plan, task)

                if planner_model == self.response_model and self.response_model != self.planner_model:
                    warnings.append(fallback_text(request.language, "intent_recovered"))
                elif attempt:
                    warnings.append(fallback_text(request.language, "intent_retry"))
                return plan, warnings, True
            except Exception as error:
                last_error = error
                
        logger.warning(
            "Assistant semantic planning failed after retry: %s: %s",
            type(last_error).__name__ if last_error else "unknown",
            str(last_error) if last_error else "no error details",
        )
        warnings.append(fallback_text(request.language, "model_unavailable"))
        return None, warnings, False

    def _synthesize_plan(
        self,
        database: Session,
        request: AssistantChatRequest,
        plan: SemanticPlan,
        responses: list[tuple[PlannerTask, AssistantChatResponse]],
    ) -> str:
        synthesis_place_ids = list(dict.fromkeys(
            item.place.id
            for _, response in responses
            for item in response.recommendations
        ))
        payload = {
            "original_user_message": request.message,
            "response_language": plan.response_language,
            "plan_mode": plan.mode,
            "structured_place_facts": _place_fact_records(database, synthesis_place_ids),
            "task_results": [
                {
                    "task": task.model_dump(mode="json"),
                    "answer": response.answer,
                    "intent": response.intent.model_dump(mode="json"),
                    "recommendations": [
                        {
                            "place": item.place.model_dump(mode="json", exclude={"primary_image"}),
                            "reason": item.reason,
                            "distance_km": item.distance_km,
                            "transit_url": item.transit_url,
                        }
                        for item in response.recommendations
                    ],
                }
                for task, response in responses
            ],
        }
        try:
            call = self.response_provider.generate_structured(
                model=self.response_model,
                system_prompt=PLAN_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=json.dumps(payload, ensure_ascii=False),
                output_schema=PlanSynthesisResponse,
            )
            synthesized = PlanSynthesisResponse.model_validate(call.output)
            return _sanitize_user_text(synthesized.answer)
        except Exception as error:
            logger.warning("Assistant plan synthesis failed: %s", type(error).__name__)
            return "\n\n".join(
                response.answer for _, response in responses if response.answer.strip()
            )

    def respond(
        self,
        database: Session,
        request: AssistantChatRequest,
    ) -> AssistantChatResponse:
        planned, plan_warnings, planner_available = self._plan_request(request)

        if planned is None:
            fallback_intent = DiscoveryIntent(
                city="turin",
                categories=[],
                limit=5,
                language=request.language,
                request_language=request.language,
            )
            return AssistantChatResponse(
                answer=fallback_text(request.language, "model_unavailable"),
                intent=fallback_intent,
                recommendations=[],
                grounded=True,
                provider_status="fallback",
                warnings=plan_warnings,
            )

        plan = planned

        validated_tasks: list[tuple[PlannerTask, DiscoveryIntent]] = []
        try:
            for task in plan.tasks:
                validated_tasks.append(
                    (
                        task,
                        _planned_task_intent(
                            request,
                            plan,
                            task,
                        ),
                    )
                )
        except Exception as error:
            logger.warning("Assistant planner validation failed: %s", type(error).__name__)
            fallback_intent = DiscoveryIntent(
                city="turin",
                categories=[],
                limit=5,
                language=request.language,
                request_language=request.language,
            )
            warnings = plan_warnings + [fallback_text(request.language, "model_unavailable")]
            return AssistantChatResponse(
                answer=fallback_text(request.language, "model_unavailable"),
                intent=fallback_intent,
                recommendations=[],
                grounded=True,
                provider_status="fallback",
                warnings=warnings,
            )

        rolling_history = list(request.history)
        context_ids = list(request.context_place_ids)
        responses: list[tuple[PlannerTask, AssistantChatResponse]] = []
        unique_recommendations: dict[int, AssistantRecommendation] = {}
        warnings = list(plan_warnings)
        transport_disclaimer: str | None = None

        from app.schemas.assistant import ConversationMessage

        for task, intent in validated_tasks:
            task_context_ids = list(context_ids)
            if task.refers_to_context and task.reference_position is not None:
                index = task.reference_position - 1
                if 0 <= index < len(task_context_ids):
                    task_context_ids = [task_context_ids[index]]

            task_request = AssistantChatRequest(
                message=task.query,
                language=intent.language,
                history=rolling_history[-10:],
                context_place_ids=task_context_ids,
                latitude=request.latitude,
                longitude=request.longitude,
                radius_km=request.radius_km,
            )
            response = self._respond_single(
                database,
                task_request,
                precomputed_intent=intent,
                model_refers_to_context=task.refers_to_context or plan.is_continuation,
                model_needs_semantic_retrieval=bool(
                    task.preferences
                    or task.goal in {"describe", "compare", "itinerary"}
                    or task.refers_to_context
                ),
                initial_warnings=[],
                planner_available=planner_available,
            )
            responses.append((task, response))
            for recommendation in response.recommendations:
                unique_recommendations.setdefault(recommendation.place.id, recommendation)
            warnings.extend(item for item in response.warnings if item not in warnings)
            if response.transport_disclaimer:
                transport_disclaimer = response.transport_disclaimer
            if response.recommendations:
                context_ids = [item.place.id for item in response.recommendations]

            rolling_history.extend(
                [
                    ConversationMessage(role="user", content=task.query[:2000]),
                    ConversationMessage(role="assistant", content=response.answer[:2000]),
                ]
            )

        if len(responses) == 1:
            response = responses[0][1]
            if warnings == response.warnings:
                return response
            return response.model_copy(update={"warnings": warnings})

        first_response = responses[0][1]
        recommendations = list(unique_recommendations.values())[:10]
        combined_answer = self._synthesize_plan(database, request, plan, responses)
        return AssistantChatResponse(
            answer=combined_answer,
            intent=first_response.intent,
            recommendations=recommendations,
            grounded=all(response.grounded for _, response in responses),
            provider_status=(
                "available"
                if all(response.provider_status == "available" for _, response in responses)
                else "fallback"
            ),
            transport_disclaimer=transport_disclaimer,
            warnings=warnings,
        )

    def _respond_single(
        self,
        database: Session,
        request: AssistantChatRequest,
        *,
        precomputed_intent: DiscoveryIntent,
        model_refers_to_context: bool = False,
        model_needs_semantic_retrieval: bool = False,
        initial_warnings: list[str] | None = None,
        planner_available: bool = True,
    ) -> AssistantChatResponse:
        warnings: list[str] = list(initial_warnings or [])
        provider_available = planner_available
        intent = precomputed_intent

        if intent.city not in CITIES:
            return AssistantChatResponse(
                answer=fallback_text(request.language, "unsupported_city"),
                intent=intent,
                recommendations=[],
                grounded=True,
                provider_status="available" if provider_available else "fallback",
                warnings=warnings,
            )

        if intent.tool_intent == "weather":
            weather_tool = self.weather_tool
            if weather_tool is None:
                from app.tools.weather import get_weather

                weather_tool = get_weather
            try:
                weather = weather_tool(
                    WeatherRequest(
                        city=intent.city,
                        forecast_hours=intent.forecast_hours,
                        latitude=request.latitude,
                        longitude=request.longitude,
                    )
                )
                answer = self._live_answer(
                    request,
                    intent,
                    tool_name="get_weather",
                    evidence=weather.model_dump(mode="json"),
                    facts=_weather_claims(weather),
                )
                if answer is not None:
                    return AssistantChatResponse(
                        answer=answer,
                        intent=intent,
                        recommendations=[],
                        grounded=True,
                        provider_status="available",
                        warnings=warnings,
                    )
            except Exception as error:
                logger.warning(
                    "Assistant weather tool failed: %s", type(error).__name__
                )
            warnings.append(fallback_text(request.language, "live_tool_unavailable"))
            return AssistantChatResponse(
                answer=fallback_text(request.language, "live_tool_unavailable"),
                intent=intent,
                recommendations=[],
                grounded=True,
                provider_status="fallback",
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

        explicit_target_name = intent.target_place_name
        named_places: list[RetrievedPlace] = []
        if explicit_target_name:
            named_places = retriever(
                database,
                city=intent.city,
                categories=intent.categories,
                limit=5,
                latitude=request.latitude if intent.nearby else None,
                longitude=request.longitude if intent.nearby else None,
                radius_km=request.radius_km or intent.radius_km,
                place_ids=None,
                name_query=explicit_target_name,
            )

        contextual_follow_up = bool(
            request.context_place_ids
            and not named_places
            and model_refers_to_context
        )
        scoped_place_ids = (
            [item.place.id for item in named_places]
            if named_places
            else (request.context_place_ids if contextual_follow_up else None)
        )
        use_semantic_retrieval = bool(
            self.embedding_provider is not None
            and (
                model_needs_semantic_retrieval
                or contextual_follow_up
                or bool(named_places)
                or intent.tool_intent.startswith("official_")
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
                semantic_query = request.message
                if intent.preferences:
                    semantic_query = semantic_query + "\nPreferences: " + "; ".join(intent.preferences)
                query_vector = self.embedding_provider.embed(
                    model=self.embedding_model,
                    texts=[semantic_query],
                )[0]
                evidence = evidence_retriever(
                    database,
                    query_embedding=query_vector,
                    city=intent.city,
                    categories=([] if named_places else intent.categories),
                    place_ids=scoped_place_ids,
                    latitude=request.latitude if intent.nearby else None,
                    longitude=request.longitude if intent.nearby else None,
                    radius_km=request.radius_km or intent.radius_km,
                    limit=self.evidence_limit,
                )
                semantic_place_ids = list(dict.fromkeys(item.place_id for item in evidence))
            except Exception as error:
                logger.warning(
                    "Assistant evidence retrieval failed: %s", type(error).__name__
                )
                warnings.append(fallback_text(request.language, "semantic_unavailable"))

        candidate_ids = (
            [item.place.id for item in named_places]
            if named_places
            else (
                semantic_place_ids
                or (request.context_place_ids if contextual_follow_up else None)
            )
        )
        candidate_limit = min(max(len(candidate_ids or []), intent.limit), 10)
        category_quotas = intent.category_limits
        use_category_quotas = bool(
            not named_places
            and len(intent.categories) > 1
            and len(category_quotas) == len(intent.categories)
        )
        if use_category_quotas:
            places = []
            seen_place_ids: set[int] = set()
            for category in intent.categories:
                quota = category_quotas[category]
                category_places = retriever(
                    database,
                    city=intent.city,
                    categories=[category],
                    limit=quota,
                    latitude=request.latitude if intent.nearby else None,
                    longitude=request.longitude if intent.nearby else None,
                    radius_km=request.radius_km or intent.radius_km,
                    place_ids=candidate_ids,
                    name_query=None,
                )
                # Semantic evidence may not cover every explicitly requested category.
                # Fill a shortfall from reviewed DB records rather than violating quotas.
                if candidate_ids and len(category_places) < quota:
                    fallback_places = retriever(
                        database,
                        city=intent.city,
                        categories=[category],
                        limit=quota,
                        latitude=request.latitude if intent.nearby else None,
                        longitude=request.longitude if intent.nearby else None,
                        radius_km=request.radius_km or intent.radius_km,
                        place_ids=None,
                        name_query=None,
                    )
                    existing_ids = {item.place.id for item in category_places}
                    category_places.extend(
                        item for item in fallback_places if item.place.id not in existing_ids
                    )
                for item in category_places[:quota]:
                    if item.place.id not in seen_place_ids:
                        places.append(item)
                        seen_place_ids.add(item.place.id)
        else:
            places = named_places or retriever(
                database,
                city=intent.city,
                categories=intent.categories,
                limit=candidate_limit,
                latitude=request.latitude if intent.nearby else None,
                longitude=request.longitude if intent.nearby else None,
                radius_km=request.radius_km or intent.radius_km,
                place_ids=candidate_ids,
                name_query=None,
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

        if intent.tool_intent.startswith("official_"):
            target = _select_official_target(
                places,
                target_name=intent.target_place_name,
                context_place_ids=request.context_place_ids,
            )
            if target is None:
                warnings.append(fallback_text(request.language, "live_tool_unavailable"))
                return AssistantChatResponse(
                    answer=fallback_text(request.language, "live_tool_unavailable"),
                    intent=intent,
                    recommendations=[],
                    grounded=True,
                    provider_status="fallback",
                    warnings=warnings,
                )

            official_site_tool = self.official_site_tool
            if official_site_tool is None:
                from app.tools.official_site import get_official_place_page

                official_site_tool = get_official_place_page
            page_type = _official_page_type(intent.tool_intent)
            try:
                live_evidence = official_site_tool(
                    database,
                    place_id=target.place.id,
                    page_type=page_type,
                    query=request.message,
                )
                full_payload = live_evidence.model_dump(mode="json")
                relevant_text = _relevant_official_excerpt(
                    live_evidence.text,
                    message=request.message,
                    page_type=page_type,
                )
                time_facts = _city_time_facts(intent)
                live_payload = {
                    key: full_payload[key]
                    for key in (
                        "place_name",
                        "page_type",
                        "official_host",
                        "source_url",
                        "fetched_at",
                        "verified",
                        "reason",
                        "title",
                        "truncated",
                    )
                }
                live_payload["relevant_text"] = relevant_text
                live_payload.update(time_facts)
                live_facts = {
                    key: live_payload[key]
                    for key in live_payload
                    if key != "relevant_text"
                }
                answer = self._live_answer(
                    request,
                    intent,
                    tool_name="get_official_place_page",
                    evidence=live_payload,
                    facts=live_facts,
                    official_text=relevant_text,
                    must_abstain=(not live_evidence.verified or not relevant_text),
                )
                if answer is not None:
                    return AssistantChatResponse(
                        answer=answer,
                        intent=intent,
                        recommendations=[
                            AssistantRecommendation(
                                place=target.place,
                                reason=_fallback_reason(target, request.language),
                                distance_km=target.distance_km,
                            )
                        ],
                        grounded=True,
                        provider_status="available",
                        warnings=warnings,
                    )
            except Exception as error:
                logger.warning(
                    "Assistant official-site tool failed: %s", type(error).__name__
                )

            warnings.append(fallback_text(request.language, "live_tool_unavailable"))
            return AssistantChatResponse(
                answer=fallback_text(request.language, "live_tool_unavailable"),
                intent=intent,
                recommendations=[
                    AssistantRecommendation(
                        place=target.place,
                        reason=_fallback_reason(target, request.language),
                        distance_km=target.distance_km,
                    )
                ],
                grounded=True,
                provider_status="fallback",
                warnings=warnings,
            )

        if "live_opening_status" in intent.unsupported_constraints:
            warnings.append(fallback_text(request.language, "opening_unavailable"))
        if "unverified_rating" in intent.unsupported_constraints:
            warnings.append(fallback_text(request.language, "rating_unavailable"))

        selected = places[: intent.limit]
        place_facts = _place_fact_records(database, [item.place.id for item in places])
        claims_by_place: dict[int, list[GroundedClaim]] = {}
        reasons_by_place: dict[int, str] = {}
        conversational_answer: str | None = None
        # A final grounded generation makes even a single result conversational.
        # Deterministic validation and fallback still own factual safety.
        if provider_available and places:
            try:
                response_call = self.response_provider.generate_structured(
                    model=self.response_model,
                    system_prompt=ASSISTANT_RESPONSE_SYSTEM_PROMPT,
                    user_prompt=_grounding_prompt(
                        request, intent, places, evidence, place_facts
                    ),
                    output_schema=GroundedResponse,
                )
                grounded = GroundedResponse.model_validate(response_call.output)
                grounded, claims_by_place, grounding_repairs = _normalize_grounded_response(
                    grounded, places, evidence, intent.limit
                )
                selected_ids = [item.place_id for item in grounded.recommendations]
                if use_category_quotas:
                    selected_ids, quota_repaired = _repair_category_quota_selection(
                        selected_ids, places, category_quotas, intent.limit
                    )
                    if quota_repaired:
                        grounding_repairs.append("repaired_category_quotas")
                selected_by_id = {place.place.id: place for place in places}
                selected = [selected_by_id[place_id] for place_id in selected_ids]
                if grounding_repairs:
                    logger.info(
                        "Assistant grounding response repaired: %s",
                        ",".join(dict.fromkeys(grounding_repairs)),
                    )
                    # Once any model content needed repair, keep the selected IDs but
                    # fall back to application-owned copy for user-visible text. This
                    # prevents a dropped claim/recommendation from surviving indirectly
                    # in a free-form reason or summary.
                    reasons_by_place = {}
                    conversational_answer = None
                else:
                    reasons_by_place = {
                        item.place_id: _sanitize_user_text(item.reason)
                        for item in grounded.recommendations
                        if item.place_id in selected_ids
                    }
                    conversational_answer = _sanitize_user_text(grounded.summary)
            except Exception as error:
                logger.warning(
                    "Assistant grounding validation failed: %s: %s",
                    type(error).__name__,
                    str(error),
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
