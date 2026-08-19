from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.evidence import PlaceEvidence
from app.models.place import Place
from app.services.official_site import OfficialSiteEvidence
from app.tools.official_site import get_official_place_page
from app.services.rag import EvidenceCandidate


@dataclass(frozen=True, slots=True)
class OfficialDocumentTopic:
    key: str
    query: str
    title: str


OFFICIAL_DOCUMENT_TOPICS: tuple[OfficialDocumentTopic, ...] = (
    OfficialDocumentTopic(
        key="accessibility",
        query="accessibility wheelchair disabled barrier accessible",
        title="Accessibility and inclusive visitor information",
    ),
    OfficialDocumentTopic(
        key="visitor_services",
        query="visitor services facilities amenities parking family children info toilets",
        title="Visitor services and facilities",
    ),
    OfficialDocumentTopic(
        key="collections",
        query="permanent collections collection visitor highlights works masterpieces",
        title="Permanent collections and visitor highlights",
    ),
    OfficialDocumentTopic(
        key="shopping_directory",
        query="shops stores brands directory men women kids collections botteghe artigiani",
        title="Shops, brands and collections",
    ),
    OfficialDocumentTopic(
        key="dietary_policy",
        query="dietary vegetarian vegan gluten allergens halal food policy menu intolleranze",
        title="Dietary and food policy information",
    ),
)



TOPIC_RELEVANCE_TERMS: dict[str, tuple[str, ...]] = {
    "accessibility": (
        "accessibility", "accessible", "wheelchair", "disabled", "disability",
        "barrier", "barriere", "accessibilita", "accessibilità", "disabil",
        "sedia a rotelle",
    ),
    "visitor_services": (
        "facility", "facilities", "amenity", "amenities", "parking", "family",
        "children", "service", "services", "servizi", "parcheggio", "famiglie",
        "bambini", "guardaroba", "toilet", "toilettes", "restroom", "infopoint",
    ),
    "collections": (
        "permanent collection", "permanent collections", "collection", "collections",
        "collezione", "collezioni", "permanente", "permanenti", "highlights",
        "opere", "capolavori", "percorso", "percorsi",
    ),
    "shopping_directory": (
        "shop", "shops", "store", "stores", "brand", "brands", "directory",
        "men", "women", "kids", "negozi", "marchi", "uomo", "donna", "bambini",
        "bottega", "botteghe", "artigiano", "artigiani",
    ),
    "dietary_policy": (
        "vegetarian", "vegan", "gluten", "allergen", "allergens", "halal",
        "dietary", "vegetar", "vegano", "vegana", "allerg", "celiac", "senza glutine",
        "intolleranza", "intolleranze", "menu", "menù",
    ),
}

PREFIX_RELEVANCE_TERMS = {"disabil", "vegetar", "allerg"}


TOPIC_APPLICABLE_CATEGORIES: dict[str, frozenset[str]] = {
    # Store/brand directories are meaningful durable knowledge for shopping places,
    # not for a museum page that merely has a gift-shop footer link.
    "shopping_directory": frozenset({"shopping_centre", "market", "supermarket"}),
    # Dietary policy belongs to places where food service is a core visitor offering.
    "dietary_policy": frozenset({
        "restaurant", "cafe", "bar", "pub", "fast_food", "hotel", "hostel"
    }),
    # Permanent collections/highlights are primarily cultural-attraction knowledge.
    "collections": frozenset({
        "museum", "gallery", "attraction", "historic_site", "monument"
    }),
}


def _topic_applicable(topic: OfficialDocumentTopic, place: Place) -> bool:
    allowed = TOPIC_APPLICABLE_CATEGORIES.get(topic.key)
    if allowed is None:
        return True
    category = getattr(place, "category", None)
    # Lightweight tests/legacy call sites may provide a place-like object without a
    # category. In production Place.category is required, so only gate when present.
    return category is None or category in allowed


def _contains_relevance_term(text: str, term: str) -> bool:
    """Match relevance terms on lexical boundaries rather than arbitrary substrings."""

    normalized_term = term.casefold()
    escaped = re.escape(normalized_term)
    if normalized_term in PREFIX_RELEVANCE_TERMS:
        pattern = rf"(?<!\w){escaped}\w*"
    else:
        pattern = rf"(?<!\w){escaped}(?!\w)"
    return re.search(pattern, text.casefold(), flags=re.UNICODE) is not None


def _topic_relevant(topic: OfficialDocumentTopic, evidence: OfficialSiteEvidence) -> bool:
    """Require positive topic evidence before durable RAG ingestion.

    URL/title matches are strong because they describe the selected page itself. Body
    text is treated more cautiously because navigation/footer text can mention unrelated
    concepts such as a museum shop on every page.
    """

    terms = TOPIC_RELEVANCE_TERMS.get(topic.key, ())
    metadata = _normalize_text(
        " ".join(part for part in (evidence.source_url, evidence.title or "") if part)
    )
    if any(_contains_relevance_term(metadata, term) for term in terms):
        return True

    body = _normalize_text(evidence.text or "")
    matched = {
        term.casefold()
        for term in terms
        if _contains_relevance_term(body, term)
    }
    if not matched:
        return False

    if topic.key == "shopping_directory":
        # A lone "shop"/"shopping" footer link is not enough to turn an unrelated
        # official page into a durable shopping-directory document. Require a stronger
        # directory/brand/store/collection signal plus another shopping signal.
        strong = {
            "store", "stores", "brand", "brands", "directory", "men", "women",
            "kids", "negozi", "marchi", "uomo", "donna", "bambini",
            "bottega", "botteghe", "artigiano", "artigiani",
        }
        return bool(matched & strong) and len(matched) >= 2

    if topic.key == "visitor_services":
        # Generic footer words like "services" are common; require corroboration.
        return len(matched) >= 2

    # Accessibility, permanent-collection and dietary terms are distinctive enough
    # that one explicit page-body signal is useful durable evidence.
    return True

MAX_DOCUMENT_CHARS = 6_000
CHUNK_CHARS = 1_800
CHUNK_OVERLAP_CHARS = 180


@dataclass(frozen=True, slots=True)
class OfficialDocumentCollection:
    candidates: list[EvidenceCandidate]
    completed_topics: dict[tuple[int, str], set[str]]
    failures: list[str]


def _topic_map() -> dict[str, OfficialDocumentTopic]:
    return {topic.key: topic for topic in OFFICIAL_DOCUMENT_TOPICS}


def resolve_topics(keys: Iterable[str] | None = None) -> tuple[OfficialDocumentTopic, ...]:
    if keys is None:
        return OFFICIAL_DOCUMENT_TOPICS
    catalog = _topic_map()
    resolved: list[OfficialDocumentTopic] = []
    for raw_key in keys:
        key = raw_key.strip().casefold()
        if key not in catalog:
            raise ValueError(
                f"Unknown official-document topic '{raw_key}'. "
                f"Allowed: {', '.join(catalog)}."
            )
        if catalog[key] not in resolved:
            resolved.append(catalog[key])
    return tuple(resolved)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _chunks(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    normalized = normalized[:MAX_DOCUMENT_CHARS]
    if len(normalized) <= CHUNK_CHARS:
        return [normalized]

    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_CHARS, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(". ", start + CHUNK_CHARS // 2, end)
            if boundary > start:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


def _candidate_from_evidence(
    *,
    place: Place,
    topic: OfficialDocumentTopic,
    evidence: OfficialSiteEvidence,
    chunk: str,
    chunk_index: int,
) -> EvidenceCandidate:
    content = (
        f"Place: {place.name}.\n"
        f"Official information type: {topic.title}.\n"
        f"Official website evidence: {chunk}"
    )
    fingerprint = sha256(
        f"{evidence.source_url}\n{topic.key}\n{content}".encode("utf-8")
    ).hexdigest()
    return EvidenceCandidate(
        place_id=place.id,
        source_type="official_site",
        source_id=f"official:{topic.key}:{chunk_index}",
        source_url=evidence.source_url,
        language="und",
        title=f"{place.name} — {topic.title}",
        content=content,
        attribution=f"Official website for {place.name}",
        license=None,
        fingerprint=fingerprint,
        content_type=topic.key,
        source_fetched_at=evidence.fetched_at,
    )


def collect_official_document_candidates(
    database: Session,
    *,
    city: str,
    place_limit: int | None = None,
    place_id: int | None = None,
    topic_keys: Iterable[str] | None = None,
) -> OfficialDocumentCollection:
    """Collect stable official-site evidence from reviewed production places only.

    The network boundary remains inside get_official_place_page: the caller supplies
    a reviewed place ID and never a URL. Failures are isolated per place/topic.
    """

    topics = resolve_topics(topic_keys)
    statement = (
        select(Place)
        .where(
            func.lower(Place.city) == city.casefold(),
            Place.website.is_not(None),
            Place.website != "",
        )
        .order_by(Place.id)
    )
    if place_id is not None:
        statement = statement.where(Place.id == place_id)
    if place_limit is not None:
        statement = statement.limit(place_limit)
    places = list(database.scalars(statement).all())

    candidates: list[EvidenceCandidate] = []
    completed_topics: dict[tuple[int, str], set[str]] = {}
    failures: list[str] = []

    for place in places:
        seen_payloads: set[tuple[str, str]] = set()
        for topic in topics:
            if not _topic_applicable(topic, place):
                # Applicability is deterministic from the reviewed production category.
                # Mark the topic complete with no active chunks so evidence created by an
                # older, broader ingestion rule can be retired without making a request.
                completed_topics[(place.id, topic.key)] = set()
                continue
            try:
                evidence = get_official_place_page(
                    database,
                    place_id=place.id,
                    page_type="general",
                    query=topic.query,
                )
            except (ValueError, RuntimeError) as exc:
                failures.append(f"place {place.id} topic {topic.key}: {exc}")
                continue
            if not evidence.verified or not evidence.text:
                failures.append(
                    f"place {place.id} topic {topic.key}: "
                    f"{evidence.reason or 'no verified text'}"
                )
                continue
            if not _topic_relevant(topic, evidence):
                # Retrieval itself succeeded, but there is no durable evidence for
                # this topic. Mark the topic complete with no active chunks so a
                # previously misclassified/stale topic chunk can be retired safely.
                completed_topics[(place.id, topic.key)] = set()
                failures.append(
                    f"place {place.id} topic {topic.key}: no topic-relevant official content"
                )
                continue

            payload_key = (evidence.source_url, _normalize_text(evidence.text))
            if payload_key in seen_payloads:
                # Avoid indexing the same homepage repeatedly when no topic-specific
                # same-domain page exists. A successful duplicate refresh still marks
                # this topic complete so obsolete topic-specific chunks can retire.
                completed_topics[(place.id, topic.key)] = set()
                continue
            seen_payloads.add(payload_key)

            topic_candidates = [
                _candidate_from_evidence(
                    place=place,
                    topic=topic,
                    evidence=evidence,
                    chunk=chunk,
                    chunk_index=index,
                )
                for index, chunk in enumerate(_chunks(evidence.text), start=1)
            ]
            if not topic_candidates:
                continue
            candidates.extend(topic_candidates)
            completed_topics[(place.id, topic.key)] = {
                item.source_id for item in topic_candidates
            }

    return OfficialDocumentCollection(
        candidates=candidates,
        completed_topics=completed_topics,
        failures=failures,
    )


def pending_official_document_candidates(
    database: Session,
    *,
    candidates: list[EvidenceCandidate],
) -> list[EvidenceCandidate]:
    if not candidates:
        return []
    place_ids = sorted({item.place_id for item in candidates})
    existing = {
        (item.place_id, item.source_type, item.source_id): item
        for item in database.scalars(
            select(PlaceEvidence).where(
                PlaceEvidence.place_id.in_(place_ids),
                PlaceEvidence.source_type == "official_site",
            )
        ).all()
    }
    return [
        candidate
        for candidate in candidates
        if (
            existing.get((candidate.place_id, candidate.source_type, candidate.source_id))
            is None
            or existing[(candidate.place_id, candidate.source_type, candidate.source_id)].fingerprint
            != candidate.fingerprint
        )
    ]


def prune_superseded_official_chunks(
    database: Session,
    *,
    completed_topics: dict[tuple[int, str], set[str]],
) -> int:
    """Delete stale chunk tails only after a topic was successfully refreshed."""

    removed = 0
    for (place_id, topic_key), active_source_ids in completed_topics.items():
        rows = list(
            database.scalars(
                select(PlaceEvidence).where(
                    PlaceEvidence.place_id == place_id,
                    PlaceEvidence.source_type == "official_site",
                    PlaceEvidence.content_type == topic_key,
                )
            ).all()
        )
        for row in rows:
            if row.source_id not in active_source_ids:
                database.delete(row)
                removed += 1
    if removed:
        database.commit()
    return removed
