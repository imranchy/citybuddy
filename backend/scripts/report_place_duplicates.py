import argparse
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.cities import CityConfig, get_city
from app.db.database import SessionLocal
from app.models.place import Place


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    first_id: int
    first_source_id: str
    second_id: int
    second_source_id: str
    name: str
    category: str
    distance_metres: float


def find_duplicate_candidates(
    city: CityConfig,
    *,
    radius_metres: float,
) -> list[DuplicateCandidate]:
    """Find same-name, same-category places that are unusually close."""

    first_place = aliased(Place)
    second_place = aliased(Place)

    distance_metres = func.ST_Distance(
        first_place.location,
        second_place.location,
    ).label("distance_metres")

    statement = (
        select(
            first_place.id.label("first_id"),
            first_place.source_id.label("first_source_id"),
            second_place.id.label("second_id"),
            second_place.source_id.label("second_source_id"),
            first_place.name,
            first_place.category,
            distance_metres,
        )
        .join(
            second_place,
            first_place.id < second_place.id,
        )
        .where(
            first_place.source == "osm",
            second_place.source == "osm",
            func.lower(func.trim(first_place.name))
            == func.lower(func.trim(second_place.name)),
            first_place.category == second_place.category,
            func.lower(first_place.city) == city.display_name.lower(),
            func.lower(second_place.city) == city.display_name.lower(),
            func.ST_DWithin(
                first_place.location,
                second_place.location,
                radius_metres,
            ),
        )
        .order_by(first_place.name, distance_metres)
    )

    database = SessionLocal()

    try:
        rows = database.execute(statement).mappings().all()

        return [
            DuplicateCandidate(
                first_id=row["first_id"],
                first_source_id=row["first_source_id"],
                second_id=row["second_id"],
                second_source_id=row["second_source_id"],
                name=row["name"],
                category=row["category"],
                distance_metres=float(row["distance_metres"]),
            )
            for row in rows
        ]
    finally:
        database.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report possible duplicate places without modifying data."
        )
    )
    parser.add_argument(
        "--city",
        default="turin",
        help="Configured city key (default: turin).",
    )
    parser.add_argument(
        "--radius-metres",
        type=float,
        default=100,
        help="Maximum separation for a duplicate candidate (default: 100).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()

    if arguments.radius_metres <= 0:
        raise SystemExit("--radius-metres must be greater than zero.")

    try:
        selected_city = get_city(arguments.city)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    candidates = find_duplicate_candidates(
        selected_city,
        radius_metres=arguments.radius_metres,
    )

    if not candidates:
        print("No duplicate candidates found.")
        raise SystemExit(0)

    print(
        f"Found {len(candidates)} possible duplicate pairs in "
        f"{selected_city.display_name}:"
    )

    for candidate in candidates:
        print()
        print(f"Name: {candidate.name}")
        print(f"Category: {candidate.category}")
        print(
            f"First: places/{candidate.first_id} "
            f"(OSM {candidate.first_source_id})"
        )
        print(
            f"Second: places/{candidate.second_id} "
            f"(OSM {candidate.second_source_id})"
        )
        print(f"Distance: {candidate.distance_metres:.1f} m")

    print()
    print("Report only: no database changes were made.")
