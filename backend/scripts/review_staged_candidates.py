import argparse
from collections import Counter

from sqlalchemy import select

from app.core.config import settings
from app.core.ingestion import missing_enrichment_updates
from app.db.database import SessionLocal
from app.llm.ollama import OllamaError, OllamaProvider
from app.models.ingestion import (
    AgentReviewDecision,
    ImageValidationIssue,
    StagedPlace,
    StagedPlaceImage,
    ValidationIssue,
)
from app.models.place import Place
from app.services.ingestion_agents import build_review_graph, review_candidate
from app.services.review_runner import run_with_ollama_retries


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run bounded agent review over one CityBuddy staging run."
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--candidate-type", choices=("place", "image", "all"), default="all"
    )
    parser.add_argument(
        "--include-valid",
        action="store_true",
        help="Also record deterministic decisions for valid candidates.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist review decisions only. This never promotes production data.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Review at most this many eligible candidates after deterministic skips.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=2,
        help="Maximum attempts for a candidate when the local model call fails.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help=(
            "Ollama timeout for offline ingestion review. Defaults to at least 90 seconds "
            "without changing the user-facing assistant timeout."
        ),
    )
    arguments = parser.parse_args()
    if arguments.limit is not None and arguments.limit < 1:
        parser.error("--limit must be at least 1")
    if arguments.retry_attempts < 1:
        parser.error("--retry-attempts must be at least 1")
    if arguments.timeout_seconds is not None and arguments.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than 0")
    return arguments


def place_payload(database, place: StagedPlace) -> dict:
    current = database.get(Place, place.target_place_id) if place.target_place_id else None
    issue_codes = database.scalars(
        select(ValidationIssue.code).where(ValidationIssue.staged_place_id == place.id)
    ).all()
    current_production = (
        {
            "description": current.description,
            "opening_hours": current.opening_hours,
            "website": current.website,
            "operator": current.operator,
        }
        if current is not None
        else None
    )
    candidate_fields = {
        "description": place.description,
        "opening_hours": place.opening_hours,
        "website": place.website,
        "operator": place.operator,
    }
    safe_updates = (
        missing_enrichment_updates(current_production, candidate_fields)
        if current_production is not None
        else {}
    )
    return {
        "staged_candidate_id": place.id,
        "candidate_kind": place.candidate_kind,
        "target_place_id": place.target_place_id,
        "source": place.source,
        "source_id": place.source_id,
        "name": place.name,
        "category": place.category,
        "description": place.description,
        "address": place.address,
        "city": place.city,
        "country_code": place.country_code,
        "website": place.website,
        "operator": place.operator,
        "opening_hours": place.opening_hours,
        "validation_findings": list(issue_codes),
        "current_production": current_production,
        "safe_enrichment_updates": safe_updates,
        "policy_facts": {
            "has_valid_geolocation": True,
            "missing_address_is_not_a_conflict": True,
            "existing_record_enrichment_is_expected": place.candidate_kind == "enrichment",
            "promotion_can_only_fill_missing_allowlisted_fields": True,
        },
    }


def image_payload(database, image: StagedPlaceImage) -> dict:
    place = database.get(Place, image.place_id)
    issue_codes = database.scalars(
        select(ImageValidationIssue.code).where(
            ImageValidationIssue.staged_image_id == image.id
        )
    ).all()
    return {
        "place_name": place.name if place is not None else None,
        "place_category": place.category if place is not None else None,
        "place_source_id": place.source_id if place is not None else None,
        "place_id": image.place_id,
        "wikidata_id": image.wikidata_id,
        "source": image.source,
        "source_image_id": image.source_image_id,
        "image_url": image.image_url,
        "source_page_url": image.source_page_url,
        "attribution": image.attribution,
        "license": image.license,
        "license_url": image.license_url,
        "validation_findings": list(issue_codes),
    }


def existing_decision(database, candidate_type: str, item) -> AgentReviewDecision | None:
    reference = (
        AgentReviewDecision.staged_place_id == item.id
        if candidate_type == "place"
        else AgentReviewDecision.staged_image_id == item.id
    )
    return database.scalar(
        select(AgentReviewDecision)
        .where(
            AgentReviewDecision.ingestion_run_id == item.ingestion_run_id,
            AgentReviewDecision.candidate_type == candidate_type,
            AgentReviewDecision.candidate_fingerprint == item.fingerprint,
            reference,
        )
        .order_by(AgentReviewDecision.id.desc())
        .limit(1)
    )



def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    review_timeout = (
        arguments.timeout_seconds
        if arguments.timeout_seconds is not None
        else max(settings.ollama_timeout_seconds, 90.0)
    )
    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        timeout_seconds=review_timeout,
    )
    graph = build_review_graph(
        provider=provider,
        qwen_model=settings.ollama_intent_model,
        gemma_model=settings.ollama_response_model,
    )
    counts: Counter[str] = Counter()
    try:
        items: list[tuple[str, object]] = []
        if arguments.candidate_type in {"place", "all"}:
            places = database.scalars(
                select(StagedPlace)
                .where(
                    StagedPlace.ingestion_run_id == arguments.run_id,
                    StagedPlace.promotion_status == "pending",
                )
                .order_by(StagedPlace.id)
            ).all()
            items.extend(("place", item) for item in places)
        if arguments.candidate_type in {"image", "all"}:
            images = database.scalars(
                select(StagedPlaceImage)
                .where(
                    StagedPlaceImage.ingestion_run_id == arguments.run_id,
                    StagedPlaceImage.promotion_status == "pending",
                )
                .order_by(StagedPlaceImage.id)
            ).all()
            items.extend(("image", item) for item in images)

        reviewed_eligible = 0
        for candidate_type, item in items:
            status = item.validation_status
            if status == "valid" and not arguments.include_valid:
                counts["skipped_valid"] += 1
                continue

            prior = existing_decision(database, candidate_type, item)
            if prior is not None:
                counts["skipped_existing_decision"] += 1
                continue

            if arguments.limit is not None and reviewed_eligible >= arguments.limit:
                counts["deferred_by_limit"] += 1
                continue
            reviewed_eligible += 1

            if candidate_type == "place":
                payload = place_payload(database, item)
            else:
                payload = image_payload(database, item)

            def run_review():
                return review_candidate(
                    graph,
                    candidate_type=candidate_type,
                    candidate_id=item.id,
                    validation_status=status,
                    candidate=payload,
                )

            def report_retry(attempt: int, attempts: int, error: OllamaError) -> None:
                print(
                    f"{candidate_type}/{item.id}: local model call failed "
                    f"(attempt {attempt}/{attempts}); retrying - {error}"
                )

            try:
                result = run_with_ollama_retries(
                    run_review,
                    attempts=arguments.retry_attempts,
                    on_retry=report_retry,
                )
            except OllamaError as error:
                counts["model_error_pending"] += 1
                print(
                    f"{candidate_type}/{item.id}: model_error_pending after "
                    f"{arguments.retry_attempts} attempt(s) - {error}"
                )
                continue

            counts[result.verdict] += 1
            if result.escalated:
                counts["escalated"] += 1
            print(
                f"{candidate_type}/{item.id}: {result.verdict} "
                f"({result.reviewer_model}, confidence={result.confidence:.2f}) - "
                f"{result.reason}"
            )
            if arguments.apply:
                decision = AgentReviewDecision(
                    ingestion_run_id=item.ingestion_run_id,
                    candidate_type=candidate_type,
                    staged_place_id=item.id if candidate_type == "place" else None,
                    staged_image_id=item.id if candidate_type == "image" else None,
                    candidate_fingerprint=item.fingerprint,
                    validation_status=status,
                    verdict=result.verdict,
                    confidence=result.confidence,
                    reason=result.reason,
                    concerns=list(result.concerns),
                    reviewer_model=result.reviewer_model,
                    escalated=result.escalated,
                )
                database.add(decision)
                # Commit each completed decision so a later process interruption can
                # resume without repeating successful local-model work.
                database.commit()

        if arguments.apply:
            print("Review decisions persisted incrementally. Production data was not modified.")
        else:
            database.rollback()
            print("Preview complete. No database changes were made.")
        print(f"Review summary: {dict(counts)}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
