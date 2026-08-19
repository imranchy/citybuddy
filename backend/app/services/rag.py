from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from collections.abc import Callable
from typing import Any
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.llm.embeddings import EmbeddingProvider
from app.core.cities import get_city
from app.core.place_catalog import DESTINATION_CATEGORIES
from app.models.evidence import PlaceEvidence
from app.models.place import Place


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    place_id: int
    source_type: str
    source_id: str
    source_url: str | None
    language: str
    title: str
    content: str
    attribution: str | None
    license: str | None
    fingerprint: str
    content_type: str | None = None
    source_fetched_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    id: int
    place_id: int
    title: str
    content: str
    source_type: str
    source_url: str | None
    attribution: str | None
    license: str | None
    similarity: float


def _source_url(place: Place) -> str | None:
    if place.source == "osm" and "/" in place.source_id:
        return f"https://www.openstreetmap.org/{place.source_id}"
    return None


def build_place_evidence(place: Place) -> EvidenceCandidate:
    facts = [
        f"Name: {place.name}.",
        f"Category: {place.category.replace('_', ' ')}.",
        f"Location: {place.address}, {place.city}, {place.country_code}.",
    ]
    if place.description:
        facts.append(f"Description: {place.description.strip()}")
    if place.operator:
        facts.append(f"Operator: {place.operator}.")
    if place.opening_hours:
        facts.append(f"Recorded opening hours: {place.opening_hours}.")
    if place.dietary_options:
        facts.append(f"Dietary options: {', '.join(place.dietary_options)}.")
    if place.website:
        facts.append(f"Official website recorded by CityBuddy: {place.website}.")
    content = "\n".join(facts)
    fingerprint = sha256(content.encode("utf-8")).hexdigest()
    return EvidenceCandidate(
        place_id=place.id,
        source_type="citybuddy_place",
        source_id=f"{place.source}:{place.source_id}",
        source_url=_source_url(place),
        language="und",
        title=place.name,
        content=content,
        attribution="OpenStreetMap contributors" if place.source == "osm" else place.source,
        license="ODbL" if place.source == "osm" else None,
        fingerprint=fingerprint,
        content_type="place_profile",
        source_fetched_at=None,
    )


def pending_evidence_candidates(
    database: Session,
    *,
    city: str | None = None,
    category: str | None = None,
    limit: int | None = None,
) -> list[EvidenceCandidate]:
    statement = select(Place).order_by(Place.id)
    if city:
        statement = statement.where(Place.city.ilike(city))
    if category:
        statement = statement.where(Place.category == category)
    if limit:
        statement = statement.limit(limit)
    places = database.scalars(statement).all()
    candidates = [build_place_evidence(place) for place in places]
    if not candidates:
        return []
    existing = {
        (item.place_id, item.source_type, item.source_id): item
        for item in database.scalars(
            select(PlaceEvidence).where(
                PlaceEvidence.place_id.in_([item.place_id for item in candidates])
            )
        ).all()
    }
    return [
        candidate
        for candidate in candidates
        if (
            existing.get(
                (candidate.place_id, candidate.source_type, candidate.source_id)
            ) is None
            or existing[
                (candidate.place_id, candidate.source_type, candidate.source_id)
            ].fingerprint
            != candidate.fingerprint
        )
    ]


def index_evidence_candidates(
    database: Session,
    *,
    candidates: list[EvidenceCandidate],
    provider: EmbeddingProvider,
    model: str,
    batch_size: int = 16,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    indexed = 0
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start : start + batch_size]
        vectors = provider.embed(model=model, texts=[item.content for item in batch])
        for candidate, vector in zip(batch, vectors, strict=True):
            values: dict[str, Any] = {
                **asdict(candidate),
                "embedding_model": model,
                "embedding": vector,
            }
            statement = insert(PlaceEvidence).values(**values)
            statement = statement.on_conflict_do_update(
                constraint="uq_place_evidence_source",
                set_={
                    key: value
                    for key, value in values.items()
                    if key not in {"place_id", "source_type", "source_id"}
                }
                | {"updated_at": func.now()},
            )
            database.execute(statement)
            indexed += 1
        database.commit()
        if progress is not None:
            progress(indexed, len(candidates))
    return indexed


def retrieve_evidence(
    database: Session,
    *,
    query_embedding: list[float],
    city: str,
    categories: list[str],
    place_ids: list[int] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    limit: int = 8,
) -> list[RetrievedEvidence]:
    """Semantically rank evidence after deterministic eligibility filters."""

    distance = PlaceEvidence.embedding.cosine_distance(query_embedding)
    city_name = get_city(city).display_name
    statement = (
        select(PlaceEvidence, distance.label("distance"))
        .join(Place, Place.id == PlaceEvidence.place_id)
        .where(
            Place.category.in_(DESTINATION_CATEGORIES),
            func.lower(Place.city) == city_name.casefold(),
        )
    )
    if categories:
        statement = statement.where(Place.category.in_(categories))
    if place_ids is not None:
        if not place_ids:
            return []
        statement = statement.where(Place.id.in_(place_ids))
    if latitude is not None and longitude is not None:
        user_location = cast(
            func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326),
            Geography(geometry_type="POINT", srid=4326),
        )
        statement = statement.where(
            func.ST_DWithin(
                Place.location,
                user_location,
                (radius_km or 2.0) * 1000,
            )
        )
    rows = database.execute(
        statement.order_by(distance).limit(min(max(limit, 1), 20))
    ).all()
    return [
        RetrievedEvidence(
            id=evidence.id,
            place_id=evidence.place_id,
            title=evidence.title,
            content=evidence.content,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            attribution=evidence.attribution,
            license=evidence.license,
            similarity=round(max(0.0, 1.0 - float(distance_value)), 4),
        )
        for evidence, distance_value in rows
    ]
