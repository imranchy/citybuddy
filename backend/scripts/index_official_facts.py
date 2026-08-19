import argparse

from sqlalchemy import select

from app.core.config import settings
from app.db.database import SessionLocal
from app.llm.ollama import OllamaProvider
from app.models.place import Place
from app.services.official_facts import (
    collect_official_fact_candidates,
    pending_official_fact_candidates,
    promote_official_facts,
)


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be positive.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and promote allowlisted durable facts from verified official RAG evidence."
    )
    parser.add_argument("--city", default="Torino")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--place-limit", type=positive_integer)
    scope.add_argument("--place-id", type=positive_integer)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def require_reviewed_place(database, *, place_id: int | None, city: str) -> None:
    if place_id is None:
        return
    existing = database.scalar(
        select(Place.id).where(Place.id == place_id, Place.city.ilike(city))
    )
    if existing is None:
        raise SystemExit(
            f"Place {place_id} is not a reviewed production place in {city}."
        )


def main() -> None:
    arguments = parse_arguments()
    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        timeout_seconds=max(settings.ollama_timeout_seconds, 120),
    )
    database = SessionLocal()
    try:
        require_reviewed_place(database, place_id=arguments.place_id, city=arguments.city)
        collection = collect_official_fact_candidates(
            database,
            city=arguments.city,
            provider=provider,
            model=settings.ollama_intent_model,
            place_limit=arguments.place_limit,
            place_id=arguments.place_id,
        )
        pending = pending_official_fact_candidates(database, candidates=collection.candidates)
        print(f"Validated official facts extracted: {len(collection.candidates)}")
        print(f"Official facts requiring promotion: {len(pending)}")
        if collection.failures:
            print(f"Isolated fact-extraction failures: {len(collection.failures)}")
            for failure in collection.failures[:20]:
                print(f"  {failure}")
        for candidate in pending[:30]:
            print(
                f"  PREVIEW place/{candidate.place_id} {candidate.fact_type}={candidate.value}: "
                f"{candidate.source_url}"
            )
        if not arguments.apply:
            print("Preview complete. No structured facts were changed.")
            return
        promoted, retired = promote_official_facts(
            database,
            candidates=collection.candidates,
            completed_fact_types=collection.completed_fact_types,
        )
        print(f"Promoted {promoted} validated official facts; retired {retired} stale facts.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
