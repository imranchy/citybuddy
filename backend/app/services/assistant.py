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
from app.core.languages import fallback_text, language_name
from app.core.maps import get_google_maps_transit_url
from app.core.place_catalog import (
    canonicalize_category,
    category_terms,
    find_explicit_categories,
)
from app.llm.base import StructuredLLMProvider
from app.llm.embeddings import EmbeddingProvider
from app.llm.prompts import (
    ASSISTANT_RESPONSE_SYSTEM_PROMPT,
    INTENT_SYSTEM_PROMPT,
    TOOL_RESPONSE_SYSTEM_PROMPT,
)
from app.llm.schemas import (
    DiscoveryIntent,
    GroundedClaim,
    GroundedResponse,
    RawDiscoveryIntent,
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

WEATHER_TERMS = (
    "weather", "forecast", "temperature", "rain", "snow", "wind",
    "meteo", "previsioni", "temperatura", "pioggia", "neve", "vento",
)
MENU_TERMS = (
    "menu", "menù", "dish", "dishes", "vegetarian",
    "vegan", "halal", "allergen", "gluten", "carta", "piatto", "piatti",
    "vegetar", "vegano", "vegana", "allerg", "senza glutine",
)
OPENING_TERMS = (
    "open today", "open now", "opening hours", "hours today", "when does",
    "orari", "aperto oggi", "aperta oggi", "aperto ora", "aperta ora",
    "chiude", "apre",
)
EXHIBITION_TERMS = (
    "exhibition", "exhibitions", "what's on", "what is on", "events today",
    "mostra", "mostre", "esposizione", "esposizioni",
)
OFFICIAL_INFO_TERMS = (
    "shops", "shop", "stores", "store", "brands", "brand", "artisans",
    "artisan", "collections", "collection", "accessibility", "accessible",
    "wheelchair", "parking", "facilities", "facility", "amenities",
    "visitor services", "rules", "negozi", "botteghe", "marchi", "artigiani",
    "collezioni", "accessibilità", "accessibile", "parcheggio", "servizi",
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


def _requested_category_limits(message: str, categories: list[str]) -> dict[str, int]:
    """Return explicit per-category counts without collapsing mixed requests."""

    normalized = " ".join(message.casefold().replace("_", " ").split())
    limits: dict[str, int] = {}
    for category in categories:
        terms = category_terms(category) or (category.replace("_", " "),)
        for term in sorted(terms, key=len, reverse=True):
            category_pattern = re.escape(term)
            numeric_match = re.search(
                rf"\b(10|[1-9])\s+(?:\w+\s+)?{category_pattern}\b",
                normalized,
            )
            if numeric_match:
                limits[category] = int(numeric_match.group(1))
                break

            matched = False
            for word, count in COUNT_WORDS.items():
                if re.search(
                    rf"\b{re.escape(word)}\s+(?:\w+\s+)?{category_pattern}\b",
                    normalized,
                ):
                    limits[category] = count
                    matched = True
                    break
            if matched:
                break

            if re.search(
                rf"\b(?:a|an|un|una)\s+{category_pattern}\b",
                normalized,
            ):
                limits[category] = 1
                break
    return limits


def _requested_limit(message: str, categories: list[str]) -> int | None:
    """Extract the application-owned total result count.

    When the user gives a count for every explicitly requested category, the total is
    the sum of those quotas (for example, one museum + one park -> two results).
    """

    limits = _requested_category_limits(message, categories)
    if not limits:
        return None
    if len(categories) > 1 and len(limits) == len(categories):
        return min(sum(limits.values()), 10)
    return next(iter(limits.values()))


def _compound_subrequests(message: str) -> list[str]:
    """Split an explicitly compound message into bounded conversational turns.

    This is orchestration, not semantic classification: each resulting turn still goes
    through the normal Qwen intent -> controlled retrieval/tool -> Gemma response path.
    We only split on clear sentence/question boundaries and require at least two parts.
    """

    compact = " ".join(message.strip().split())
    if not compact:
        return []
    parts = [
        part.strip()
        for part in re.split(r"(?<=[?!])\s+|(?<=\.)\s+(?=[A-ZÀ-Ý])", compact)
        if part.strip()
    ]
    if len(parts) < 2:
        return []
    # Avoid turning ordinary multi-sentence descriptions into agent loops. At least
    # two clauses must look like direct questions/requests.
    request_starts = (
        "recommend", "find", "show", "tell", "what", "where", "when",
        "which", "who", "how", "is", "are", "does", "do", "can",
        "suggest", "give", "trova", "consiglia", "dimmi", "qual", "quale",
        "dove", "quando", "come", "è", "sono",
    )
    request_like = sum(part.casefold().startswith(request_starts) for part in parts)
    if request_like < 2:
        return []
    return parts[:12]


def _fallback_city(message: str) -> str:
    """Recover an explicitly named city when the intent model is unavailable."""

    normalized = message.casefold()
    for city_name, city_key in FALLBACK_CITY_NAMES.items():
        if re.search(rf"\b{re.escape(city_name)}\b", normalized):
            return city_key

    # Preserve an explicit proper-noun city in common location phrases so a
    # model outage cannot silently turn "Milan" into Turin. This is only a
    # conservative fallback; the application still supports only configured cities.
    match = re.search(
        r"\b(?:in|near|around|a|à|en)\s+([A-ZÀ-Ý][A-Za-zÀ-ÿ'’-]{2,})\b",
        message,
    )
    if match:
        return match.group(1).casefold()
    return "turin"

def _canonical_model_categories(values: list[str]) -> list[str]:
    categories: list[str] = []
    for value in values:
        category = canonicalize_category(value)
        if category is not None and category not in categories:
            categories.append(category)
    return categories


def _contains_any(message: str, terms: tuple[str, ...]) -> bool:
    normalized = message.casefold()
    return any(term in normalized for term in terms)


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


def _application_tool_intent(message: str, proposed: str) -> str:
    """Repair advisory tool routing from the semantics of the current message.

    Only weather is promoted deterministically from discovery. Other live routes must
    already be proposed by the intent model *and* be supported by the current message,
    preventing previous conversation context from hijacking a new request.
    """

    if _contains_any(message, WEATHER_TERMS):
        return "weather"
    if proposed == "official_menu":
        return "official_menu" if _contains_any(message, MENU_TERMS) else "discovery"
    if proposed == "official_opening":
        return (
            "official_opening"
            if _has_live_opening_request(message) or _contains_any(message, OPENING_TERMS)
            else "discovery"
        )
    if proposed == "official_prices":
        live_price_terms = (
            "price", "prices", "cost", "costs", "how much", "ticket", "tickets",
            "prezzo", "prezzi", "costo", "biglietto", "biglietti",
        )
        return "official_prices" if _contains_any(message, live_price_terms) else "discovery"
    if proposed == "official_exhibitions":
        return "official_exhibitions" if _contains_any(message, EXHIBITION_TERMS) else "discovery"
    if proposed == "official_info":
        return "official_info" if _contains_any(message, OFFICIAL_INFO_TERMS) else "discovery"
    return proposed


def normalize_discovery_intent(
    request: AssistantChatRequest,
    intent: RawDiscoveryIntent | DiscoveryIntent,
) -> DiscoveryIntent:
    """Normalize advisory model output into strict application-owned intent."""

    explicit_categories = _explicit_categories(request.message)
    model_categories = _canonical_model_categories(intent.categories)
    # Explicit supported categories in the current user message are application-owned
    # constraints. The intent model may help when the user is vague, but it must never
    # broaden an explicit request (for example museum -> museum + hotel + restaurant).
    categories = explicit_categories or model_categories
    validated_city = _validated_city(request.message, intent.city)
    explicit_radius = request.radius_km or _requested_radius_km(request.message)
    nearby = _asks_for_nearby(request.message) or explicit_radius is not None

    wants_transport = bool(intent.wants_transport) or _asks_for_transport(request.message)
    constraints = _deterministic_constraints(
        request.message,
        validated_city,
        wants_transport=wants_transport,
    )
    repaired_tool_intent = _application_tool_intent(request.message, intent.tool_intent)
    if repaired_tool_intent == "official_opening":
        constraints = [item for item in constraints if item != "live_opening_status"]
    if repaired_tool_intent == "official_prices":
        constraints = [item for item in constraints if item != "unverified_price"]

    normalized = {
        "language": request.language,
        "city": validated_city,
        "categories": categories,
        "limit": _requested_limit(request.message, categories) or 5,
        "nearby": nearby,
        "radius_km": explicit_radius if nearby else None,
        "wants_transport": wants_transport,
        "tool_intent": repaired_tool_intent,
        "target_place_name": _validated_target_place_name(
            request.message, intent.target_place_name
        ),
        "forecast_hours": intent.forecast_hours,
        "unsupported_constraints": constraints,
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
            "explicit_category_quotas": _requested_category_limits(
                request.message, intent.categories
            ),
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

    evidence_by_id = {item.id: item for item in evidence}
    evidence_place_ids = {item.place_id for item in evidence}
    for recommendation in response.recommendations:
        if any(
            evidence_id not in evidence_by_id
            or evidence_by_id[evidence_id].place_id != recommendation.place_id
            for evidence_id in recommendation.evidence_ids
        ):
            raise GroundingValidationError("A recommendation cited invalid evidence.")
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
        provider: StructuredLLMProvider,
        intent_model: str | None = None,
        response_model: str | None = None,
        model: str | None = None,
        retriever: PlaceRetriever | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str = "bge-m3",
        evidence_retriever: EvidenceRetriever | None = None,
        evidence_limit: int = 16,
        weather_tool: WeatherTool | None = None,
        official_site_tool: OfficialSiteTool | None = None,
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
            response_call = self.provider.generate_structured(
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

    def respond(
        self,
        database: Session,
        request: AssistantChatRequest,
    ) -> AssistantChatResponse:
        subrequests = _compound_subrequests(request.message)
        if not subrequests:
            return self._respond_single(database, request)

        rolling_history = list(request.history)
        context_ids = list(request.context_place_ids)
        responses: list[tuple[str, AssistantChatResponse]] = []
        unique_recommendations: dict[int, AssistantRecommendation] = {}
        warnings: list[str] = []
        transport_disclaimer: str | None = None

        from app.schemas.assistant import ConversationMessage

        for submessage in subrequests:
            subrequest = AssistantChatRequest(
                message=submessage,
                language=request.language,
                history=rolling_history[-10:],
                context_place_ids=context_ids,
                latitude=request.latitude,
                longitude=request.longitude,
                radius_km=request.radius_km,
            )
            response = self._respond_single(database, subrequest)
            responses.append((submessage, response))
            for recommendation in response.recommendations:
                unique_recommendations.setdefault(recommendation.place.id, recommendation)
            warnings.extend(item for item in response.warnings if item not in warnings)
            if response.transport_disclaimer:
                transport_disclaimer = response.transport_disclaimer
            if response.recommendations:
                context_ids = [item.place.id for item in response.recommendations]

            rolling_history.extend(
                [
                    ConversationMessage(role="user", content=submessage[:2000]),
                    ConversationMessage(role="assistant", content=response.answer[:2000]),
                ]
            )

        first_response = responses[0][1]
        combined_answer = "\n\n".join(
            f"{index}. {response.answer}"
            for index, (_, response) in enumerate(responses, start=1)
        )
        recommendations = list(unique_recommendations.values())[:10]
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
                requires_explicit_category_match = not raw_candidate.tool_intent.startswith(
                    "official_"
                )
                if (
                    requires_explicit_category_match
                    and explicit_categories
                    and not set(explicit_categories).intersection(raw_categories)
                ):
                    raise IntentValidationError(
                        "The model omitted an explicitly named supported category."
                    )
                candidate = normalize_discovery_intent(request, raw_candidate)
                if (
                    requires_explicit_category_match
                    and explicit_categories
                    and not set(explicit_categories).intersection(candidate.categories)
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
            and (model_refers_to_context or _refers_to_previous_places(request.message))
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
        category_quotas = _requested_category_limits(request.message, intent.categories)
        use_category_quotas = bool(
            not named_places
            and not candidate_ids
            and len(intent.categories) > 1
            and len(category_quotas) == len(intent.categories)
        )
        if use_category_quotas:
            places = []
            seen_place_ids: set[int] = set()
            for category in intent.categories:
                category_places = retriever(
                    database,
                    city=intent.city,
                    categories=[category],
                    limit=category_quotas[category],
                    latitude=request.latitude if intent.nearby else None,
                    longitude=request.longitude if intent.nearby else None,
                    radius_km=request.radius_km or intent.radius_km,
                    place_ids=None,
                    name_query=None,
                )
                for item in category_places:
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
                if use_category_quotas:
                    selected_records = {item.place.id: item for item in places}
                    returned_counts = {category: 0 for category in category_quotas}
                    for recommendation in grounded.recommendations:
                        category = selected_records[recommendation.place_id].place.category
                        if category in returned_counts:
                            returned_counts[category] += 1
                    if any(
                        returned_counts[category] < category_quotas[category]
                        for category in category_quotas
                    ):
                        raise GroundingValidationError(
                            "The model did not preserve explicit per-category quotas."
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
