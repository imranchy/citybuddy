import argparse
from collections import Counter

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.ingestion import AgentReviewDecision, StagedPlace
from app.services.ingestion import promote_staged_places


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("IDs must be positive integers.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote explicitly approved staged places into production."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--staged-id",
        dest="staged_ids",
        action="append",
        type=positive_integer,
        help="Approved staged ID. Repeat for multiple places from the same run.",
    )
    selection.add_argument(
        "--run-id",
        type=positive_integer,
        help="Select eligible pending candidates from one reviewed run.",
    )
    parser.add_argument(
        "--all-eligible",
        action="store_true",
        help="Required with --run-id to approve the run-level selection.",
    )
    parser.add_argument(
        "--approve-warnings",
        action="store_true",
        help="Explicitly approve review-required candidates in this batch.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create production records. Without this flag, only preview.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        if arguments.run_id is not None:
            if not arguments.all_eligible:
                raise SystemExit("--run-id requires explicit --all-eligible approval.")
            base_query = select(StagedPlace).where(
                StagedPlace.ingestion_run_id == arguments.run_id,
                StagedPlace.promotion_status == "pending",
            )
            if arguments.approve_warnings:
                approved_review_ids = select(AgentReviewDecision.staged_place_id).where(
                    AgentReviewDecision.ingestion_run_id == arguments.run_id,
                    AgentReviewDecision.candidate_type == "place",
                    AgentReviewDecision.verdict == "approve",
                    AgentReviewDecision.candidate_fingerprint == StagedPlace.fingerprint,
                )
                base_query = base_query.where(
                    (StagedPlace.validation_status == "valid")
                    | (
                        (StagedPlace.validation_status == "review_required")
                        & StagedPlace.id.in_(approved_review_ids)
                    )
                )
            else:
                base_query = base_query.where(StagedPlace.validation_status == "valid")
            places = database.scalars(
                base_query.order_by(
                    StagedPlace.category, StagedPlace.name, StagedPlace.id
                )
            ).all()
            if not places:
                raise SystemExit("No eligible pending places found for that run.")
            staged_ids = [place.id for place in places]
        else:
            staged_ids = arguments.staged_ids
            places = database.scalars(
                select(StagedPlace)
                .where(StagedPlace.id.in_(staged_ids))
                .order_by(StagedPlace.id)
            ).all()
            found_ids = {place.id for place in places}
            missing_ids = sorted(set(staged_ids) - found_ids)
            if missing_ids:
                raise SystemExit(f"Unknown staged place IDs: {missing_ids}.")

        print("Promotion preview:")
        counts = Counter(place.category for place in places)
        for category, count in sorted(counts.items()):
            print(f"  {category}: {count}")
        print(f"  total: {len(places)}")
        for place in places[:50]:
            print(
                f"  {place.id} [{place.validation_status}/"
                f"{place.promotion_status}] {place.category}: {place.name}"
            )
        if len(places) > 50:
            print(f"  ...and {len(places) - 50} more")

        if not arguments.apply:
            print("Preview complete. No production records were changed.")
            return

        batch = promote_staged_places(
            database,
            staged_ids=staged_ids,
            approve_warnings=arguments.approve_warnings,
        )
        print(
            f"Promotion batch {batch.id} completed: "
            f"{batch.promoted_count} promoted, {batch.skipped_count} skipped."
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
