import argparse
from collections import Counter

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.ingestion import ImageValidationIssue, StagedPlaceImage
from app.models.place import Place


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report staged CityBuddy images without modifying data."
    )
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--show-details", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        rows = database.execute(
            select(StagedPlaceImage, Place.name, Place.category)
            .join(Place, Place.id == StagedPlaceImage.place_id)
            .where(StagedPlaceImage.ingestion_run_id == arguments.run_id)
            .order_by(Place.category, Place.name, StagedPlaceImage.id)
        ).all()
        if not rows:
            print(f"No staged images found for ingestion run {arguments.run_id}.")
            return

        status_counts = Counter(image.validation_status for image, _, _ in rows)
        category_counts = Counter(category for _, _, category in rows)
        print(f"Staged image run {arguments.run_id}: {len(rows)} candidates")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")
        print("Categories:")
        for category, count in sorted(category_counts.items()):
            print(f"  {category}: {count}")

        if not arguments.show_details:
            print("Use --show-details to list every image and validation finding.")
            return

        image_ids = [image.id for image, _, _ in rows]
        issues_by_image: dict[int, list[ImageValidationIssue]] = {}
        issues = database.scalars(
            select(ImageValidationIssue).where(
                ImageValidationIssue.staged_image_id.in_(image_ids)
            )
        ).all()
        for issue in issues:
            issues_by_image.setdefault(issue.staged_image_id, []).append(issue)

        for image, place_name, category in rows:
            print()
            print(
                f"Staged image {image.id}: [{image.validation_status}] "
                f"{category}: {place_name}"
            )
            print(f"  Wikidata: {image.wikidata_id}")
            print(f"  Commons: {image.source_image_id}")
            print(f"  License: {image.license}")
            print(f"  Source page: {image.source_page_url}")
            for issue in issues_by_image.get(image.id, []):
                print(f"  {issue.severity.upper()} {issue.code}: {issue.message}")
    finally:
        database.close()


if __name__ == "__main__":
    main()
