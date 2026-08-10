import argparse
from collections import Counter

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.ingestion import StagedPlaceImage
from app.models.place import Place
from app.services.ingestion import promote_staged_images
from scripts.promote_staged_places import positive_integer


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote validated staged images into production."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--staged-id",
        dest="staged_ids",
        action="append",
        type=positive_integer,
    )
    selection.add_argument("--run-id", type=positive_integer)
    parser.add_argument(
        "--all-eligible",
        action="store_true",
        help="Required with --run-id to approve all valid pending images.",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        if arguments.run_id is not None:
            if not arguments.all_eligible:
                raise SystemExit("--run-id requires explicit --all-eligible approval.")
            images = database.scalars(
                select(StagedPlaceImage)
                .where(
                    StagedPlaceImage.ingestion_run_id == arguments.run_id,
                    StagedPlaceImage.validation_status == "valid",
                    StagedPlaceImage.promotion_status == "pending",
                )
                .order_by(StagedPlaceImage.id)
            ).all()
            if not images:
                raise SystemExit("No eligible pending images found for that run.")
            staged_ids = [image.id for image in images]
        else:
            staged_ids = arguments.staged_ids
            images = database.scalars(
                select(StagedPlaceImage)
                .where(StagedPlaceImage.id.in_(staged_ids))
                .order_by(StagedPlaceImage.id)
            ).all()
            found_ids = {image.id for image in images}
            missing_ids = sorted(set(staged_ids) - found_ids)
            if missing_ids:
                raise SystemExit(f"Unknown staged image IDs: {missing_ids}.")

        place_categories = dict(
            database.execute(
                select(Place.id, Place.category).where(
                    Place.id.in_(image.place_id for image in images)
                )
            ).all()
        )
        counts = Counter(place_categories[image.place_id] for image in images)
        print("Image promotion preview:")
        for category, count in sorted(counts.items()):
            print(f"  {category}: {count}")
        print(f"  total: {len(images)}")
        for image in images[:50]:
            print(
                f"  {image.id} [{image.validation_status}/"
                f"{image.promotion_status}] place/{image.place_id}: "
                f"{image.source_image_id}"
            )
        if len(images) > 50:
            print(f"  ...and {len(images) - 50} more")

        if not arguments.apply:
            print("Preview complete. No production images were changed.")
            return

        batch = promote_staged_images(database, staged_ids=staged_ids)
        print(
            f"Image promotion batch {batch.id} completed: "
            f"{batch.promoted_count} promoted, {batch.skipped_count} skipped."
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
