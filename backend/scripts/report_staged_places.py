import argparse

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.ingestion import StagedPlace, ValidationIssue


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report staged CityBuddy places without modifying data."
    )
    parser.add_argument("--run-id", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        places = database.scalars(
            select(StagedPlace)
            .where(StagedPlace.ingestion_run_id == arguments.run_id)
            .order_by(StagedPlace.validation_status, StagedPlace.name)
        ).all()

        if not places:
            print(f"No staged places found for ingestion run {arguments.run_id}.")
            return

        issues_by_place: dict[int, list[ValidationIssue]] = {}
        issues = database.scalars(
            select(ValidationIssue).where(
                ValidationIssue.staged_place_id.in_(place.id for place in places)
            )
        ).all()
        for issue in issues:
            issues_by_place.setdefault(issue.staged_place_id, []).append(issue)

        for place in places:
            print()
            print(
                f"Staged {place.id}: [{place.validation_status}] "
                f"{place.category}: {place.name}"
            )
            print(f"  Source: {place.source}/{place.source_id}")
            print(f"  Address: {place.address}, {place.city}")
            print(f"  Coordinates: {place.latitude}, {place.longitude}")
            for issue in issues_by_place.get(place.id, []):
                print(f"  {issue.severity.upper()} {issue.code}: {issue.message}")

        print()
        print("Report only: no database changes were made.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
