import argparse
import subprocess
import sys
from dataclasses import dataclass

from sqlalchemy import exists, func, select

from app.core.cities import CityConfig, get_city
from app.db.database import SessionLocal
from app.models.ingestion import AgentReviewDecision, IngestionRun, StagedPlace, StagedPlaceImage


@dataclass(frozen=True)
class PhaseResult:
    name: str
    status: str
    detail: str = ""


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be a positive integer.")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Value must be greater than zero.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run CityBuddy's bounded once-daily refresh pipeline: OSM staging, "
            "agent review, safe place promotion, incremental evidence indexing, "
            "bounded official-document refresh, and conservative Wikimedia image enrichment."
        )
    )
    parser.add_argument("--city", default="turin")
    parser.add_argument("--place-limit-per-category", type=positive_integer)
    parser.add_argument("--image-limit", type=positive_integer)
    parser.add_argument("--review-limit", type=positive_integer)
    parser.add_argument("--retry-attempts", type=positive_integer, default=2)
    parser.add_argument("--review-timeout-seconds", type=positive_float)
    parser.add_argument("--index-batch-size", type=positive_integer, default=16)
    parser.add_argument("--official-doc-place-limit", type=positive_integer)
    parser.add_argument(
        "--skip-official-docs",
        action="store_true",
        help="Skip stable official-site document retrieval/indexing for this execution.",
    )
    parser.add_argument(
        "--resume-place-run-id",
        type=positive_integer,
        help="Resume an existing OSM staging run instead of collecting OSM again.",
    )
    parser.add_argument(
        "--resume-image-run-id",
        type=positive_integer,
        help=(
            "Resume an existing Wikimedia staging run instead of collecting images again."
        ),
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip Wikimedia collection/promotion for this execution.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply staging, persisted review decisions, safe promotions, and indexing. "
            "Without this flag the runner performs collection/index previews only."
        ),
    )
    return parser.parse_args()


def command_for(module: str, *arguments: str) -> list[str]:
    return [sys.executable, "-m", module, *arguments]


def run_phase(name: str, command: list[str]) -> PhaseResult:
    print(f"\n=== {name} ===", flush=True)
    print(f"Running: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode == 0:
        return PhaseResult(name=name, status="completed")
    return PhaseResult(
        name=name,
        status="failed",
        detail=f"command exited with code {completed.returncode}",
    )


def latest_run_id(*, source: str, city: str, after_id: int = 0) -> int | None:
    database = SessionLocal()
    try:
        return database.scalar(
            select(func.max(IngestionRun.id)).where(
                IngestionRun.source == source,
                IngestionRun.city == city,
                IngestionRun.id > after_id,
            )
        )
    finally:
        database.close()


def require_resumable_run(*, run_id: int, source: str, city: str) -> None:
    database = SessionLocal()
    try:
        run = database.get(IngestionRun, run_id)
        if run is None:
            raise SystemExit(f"Unknown ingestion run ID: {run_id}.")
        if run.source != source:
            raise SystemExit(
                f"Run {run_id} belongs to source '{run.source}', expected '{source}'."
            )
        if run.city != city:
            raise SystemExit(
                f"Run {run_id} belongs to city '{run.city}', expected '{city}'."
            )
    finally:
        database.close()


def has_eligible_places(run_id: int) -> bool:
    database = SessionLocal()
    try:
        approved_review = exists(
            select(AgentReviewDecision.id).where(
                AgentReviewDecision.ingestion_run_id == run_id,
                AgentReviewDecision.candidate_type == "place",
                AgentReviewDecision.staged_place_id == StagedPlace.id,
                AgentReviewDecision.candidate_fingerprint == StagedPlace.fingerprint,
                AgentReviewDecision.verdict == "approve",
            )
        )
        query = select(
            exists().where(
                StagedPlace.ingestion_run_id == run_id,
                StagedPlace.promotion_status == "pending",
                (StagedPlace.validation_status == "valid")
                | (
                    (StagedPlace.validation_status == "review_required")
                    & approved_review
                ),
            )
        )
        return bool(database.scalar(query))
    finally:
        database.close()


def has_eligible_images(run_id: int) -> bool:
    database = SessionLocal()
    try:
        query = select(
            exists().where(
                StagedPlaceImage.ingestion_run_id == run_id,
                StagedPlaceImage.promotion_status == "pending",
                StagedPlaceImage.validation_status == "valid",
            )
        )
        return bool(database.scalar(query))
    finally:
        database.close()


def collect_place_run(arguments: argparse.Namespace, city: CityConfig) -> tuple[int | None, PhaseResult]:
    if arguments.resume_place_run_id is not None:
        require_resumable_run(
            run_id=arguments.resume_place_run_id,
            source="osm",
            city=city.display_name,
        )
        return (
            arguments.resume_place_run_id,
            PhaseResult(
                name="OSM collection",
                status="resumed",
                detail=f"using existing run {arguments.resume_place_run_id}",
            ),
        )

    previous_id = latest_run_id(source="osm", city=city.display_name) or 0
    command = command_for(
        "scripts.collect_osm_staging",
        "--city",
        arguments.city,
        "--trigger",
        "scheduled",
        "--apply",
    )
    if arguments.place_limit_per_category is not None:
        command.extend(
            ["--limit-per-category", str(arguments.place_limit_per_category)]
        )
    result = run_phase("OSM collection", command)
    if result.status == "failed":
        return None, result

    run_id = latest_run_id(
        source="osm",
        city=city.display_name,
        after_id=previous_id,
    )
    if run_id is None:
        return None, PhaseResult(
            name="OSM collection",
            status="failed",
            detail="collection succeeded but no new OSM ingestion run was found",
        )
    return run_id, result


def collect_image_run(arguments: argparse.Namespace, city: CityConfig) -> tuple[int | None, PhaseResult]:
    if arguments.resume_image_run_id is not None:
        require_resumable_run(
            run_id=arguments.resume_image_run_id,
            source="wikimedia_commons",
            city=city.display_name,
        )
        return (
            arguments.resume_image_run_id,
            PhaseResult(
                name="Wikimedia collection",
                status="resumed",
                detail=f"using existing run {arguments.resume_image_run_id}",
            ),
        )

    previous_id = latest_run_id(source="wikimedia_commons", city=city.display_name) or 0
    command = command_for(
        "scripts.collect_wikimedia_staging",
        "--city",
        arguments.city,
        "--trigger",
        "scheduled",
        "--apply",
    )
    if arguments.image_limit is not None:
        command.extend(["--limit", str(arguments.image_limit)])
    result = run_phase("Wikimedia collection", command)
    if result.status == "failed":
        return None, result

    run_id = latest_run_id(
        source="wikimedia_commons",
        city=city.display_name,
        after_id=previous_id,
    )
    if run_id is None:
        return None, PhaseResult(
            name="Wikimedia collection",
            status="failed",
            detail="collection succeeded but no new Wikimedia ingestion run was found",
        )
    return run_id, result


def preview(arguments: argparse.Namespace, city: CityConfig) -> list[PhaseResult]:
    osm_command = command_for(
        "scripts.collect_osm_staging", "--city", arguments.city
    )
    if arguments.place_limit_per_category is not None:
        osm_command.extend(
            ["--limit-per-category", str(arguments.place_limit_per_category)]
        )

    results = [
        run_phase("OSM collection preview", osm_command),
        run_phase(
            "Evidence indexing preview",
            command_for("scripts.index_place_evidence", "--city", city.display_name),
        ),
    ]
    if not arguments.skip_official_docs:
        official_command = command_for(
            "scripts.index_official_documents", "--city", city.display_name
        )
        if arguments.official_doc_place_limit is not None:
            official_command.extend(
                ["--place-limit", str(arguments.official_doc_place_limit)]
            )
        results.append(run_phase("Official document preview", official_command))
    if not arguments.skip_images:
        image_command = command_for(
            "scripts.collect_wikimedia_staging", "--city", arguments.city
        )
        if arguments.image_limit is not None:
            image_command.extend(["--limit", str(arguments.image_limit)])
        results.append(run_phase("Wikimedia collection preview", image_command))
    return results


def applied_refresh(arguments: argparse.Namespace, city: CityConfig) -> list[PhaseResult]:
    results: list[PhaseResult] = []

    place_run_id, collection_result = collect_place_run(arguments, city)
    results.append(collection_result)

    if place_run_id is not None:
        review_command = command_for(
            "scripts.review_staged_candidates",
            "--run-id",
            str(place_run_id),
            "--candidate-type",
            "place",
            "--retry-attempts",
            str(arguments.retry_attempts),
            "--apply",
        )
        if arguments.review_limit is not None:
            review_command.extend(["--limit", str(arguments.review_limit)])
        if arguments.review_timeout_seconds is not None:
            review_command.extend(
                ["--timeout-seconds", str(arguments.review_timeout_seconds)]
            )
        review_result = run_phase("Place review", review_command)
        results.append(review_result)

        if review_result.status == "completed":
            if has_eligible_places(place_run_id):
                results.append(
                    run_phase(
                        "Place promotion",
                        command_for(
                            "scripts.promote_staged_places",
                            "--run-id",
                            str(place_run_id),
                            "--all-eligible",
                            "--approve-warnings",
                            "--apply",
                        ),
                    )
                )
            else:
                results.append(
                    PhaseResult(
                        name="Place promotion",
                        status="skipped",
                        detail="no eligible pending place candidates",
                    )
                )
        else:
            results.append(
                PhaseResult(
                    name="Place promotion",
                    status="skipped",
                    detail="place review failed; conservative promotion gate kept closed",
                )
            )
    else:
        results.extend(
            [
                PhaseResult(
                    name="Place review",
                    status="skipped",
                    detail="no usable OSM staging run",
                ),
                PhaseResult(
                    name="Place promotion",
                    status="skipped",
                    detail="no usable OSM staging run",
                ),
            ]
        )

    # Indexing is independent and incremental. It can safely catch up evidence left
    # pending by an earlier successful promotion even if today's OSM source failed.
    index_command = command_for(
        "scripts.index_place_evidence",
        "--city",
        city.display_name,
        "--batch-size",
        str(arguments.index_batch_size),
        "--apply",
    )
    results.append(run_phase("Evidence indexing", index_command))

    if arguments.skip_official_docs:
        results.append(
            PhaseResult(
                name="Official document refresh",
                status="skipped",
                detail="disabled by --skip-official-docs",
            )
        )
    else:
        official_command = command_for(
            "scripts.index_official_documents",
            "--city",
            city.display_name,
            "--batch-size",
            str(arguments.index_batch_size),
            "--apply",
        )
        if arguments.official_doc_place_limit is not None:
            official_command.extend(
                ["--place-limit", str(arguments.official_doc_place_limit)]
            )
        results.append(run_phase("Official document refresh", official_command))

    if arguments.skip_images:
        results.append(
            PhaseResult(
                name="Wikimedia enrichment",
                status="skipped",
                detail="disabled by --skip-images",
            )
        )
        return results

    image_run_id, image_collection_result = collect_image_run(arguments, city)
    results.append(image_collection_result)
    if image_run_id is None:
        results.append(
            PhaseResult(
                name="Image promotion",
                status="skipped",
                detail="no usable Wikimedia staging run",
            )
        )
    elif has_eligible_images(image_run_id):
        results.append(
            run_phase(
                "Image promotion",
                command_for(
                    "scripts.promote_staged_images",
                    "--run-id",
                    str(image_run_id),
                    "--all-eligible",
                    "--apply",
                ),
            )
        )
    else:
        results.append(
            PhaseResult(
                name="Image promotion",
                status="skipped",
                detail="no deterministically valid pending image candidates",
            )
        )
    return results


def print_summary(results: list[PhaseResult]) -> None:
    print("\n=== Daily refresh summary ===")
    for result in results:
        suffix = f" - {result.detail}" if result.detail else ""
        print(f"{result.name}: {result.status}{suffix}")


def main() -> None:
    arguments = parse_arguments()
    city = get_city(arguments.city)
    if arguments.apply:
        results = applied_refresh(arguments, city)
    else:
        results = preview(arguments, city)
    print_summary(results)

    failed = [result for result in results if result.status == "failed"]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
