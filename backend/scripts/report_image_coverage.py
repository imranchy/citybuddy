import argparse

from sqlalchemy import func, select

from app.core.cities import get_city
from app.db.database import SessionLocal
from app.models.ingestion import StagedPlaceImage
from app.models.place import Place
from app.models.place_image import PlaceImage


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report measurable CityBuddy primary-image coverage."
    )
    parser.add_argument("--city", default="turin")
    parser.add_argument("--run-id", type=int)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    city = get_city(arguments.city)
    database = SessionLocal()
    try:
        total = database.scalar(
            select(func.count(Place.id)).where(Place.city == city.display_name)
        ) or 0
        with_primary = database.scalar(
            select(func.count(func.distinct(PlaceImage.place_id)))
            .join(Place, Place.id == PlaceImage.place_id)
            .where(Place.city == city.display_name, PlaceImage.is_primary.is_(True))
        ) or 0
        coverage = (with_primary / total * 100.0) if total else 0.0
        print(f"City: {city.display_name}")
        print(f"Total production places: {total}")
        print(f"Places with primary images: {with_primary}")
        print(f"Primary-image coverage now: {coverage:.2f}%")

        if arguments.run_id is not None:
            staged = database.scalars(
                select(StagedPlaceImage).where(
                    StagedPlaceImage.ingestion_run_id == arguments.run_id
                )
            ).all()
            discovered = len(staged)
            rejected = sum(
                item.validation_status == "invalid" for item in staged
            )
            promoted = sum(item.promotion_status == "promoted" for item in staged)
            promoted_primary_ids = set(
                database.scalars(
                    select(PlaceImage.place_id)
                    .join(
                        StagedPlaceImage,
                        StagedPlaceImage.promoted_image_id == PlaceImage.id,
                    )
                    .where(
                        StagedPlaceImage.ingestion_run_id == arguments.run_id,
                        StagedPlaceImage.promotion_status == "promoted",
                        PlaceImage.is_primary.is_(True),
                    )
                ).all()
            )
            before_primary = max(0, with_primary - len(promoted_primary_ids))
            before_coverage = (before_primary / total * 100.0) if total else 0.0
            print(f"Image staging run {arguments.run_id}:")
            print(f"  coverage before: {before_coverage:.2f}%")
            print(f"  image candidates discovered: {discovered}")
            print(f"  candidates rejected: {rejected}")
            print(f"  images promoted: {promoted}")
            print(f"  coverage after: {coverage:.2f}%")
    finally:
        database.close()


if __name__ == "__main__":
    main()
