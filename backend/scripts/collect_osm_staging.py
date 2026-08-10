import argparse
from collections import Counter
from typing import Any

from app.core.cities import CityConfig, get_city
from app.core.ingestion import limit_candidates_per_category
from app.core.place_catalog import DESTINATION_CATEGORIES, get_category
from app.db.database import SessionLocal
from app.services.ingestion import (
    create_ingestion_run,
    fail_ingestion_run,
    stage_place_candidates,
)
from scripts.import_osm_places import (
    fetch_osm_places_with_report,
    get_address,
    get_coordinates,
    get_description,
    get_dietary_options,
    get_lifecycle_tags,
    get_localized_tag,
    get_operational_metadata,
)


def build_osm_candidates(
    elements: list[dict[str, Any]],
    city: CityConfig,
    *,
    category: str | None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Normalize an OSM response without writing to the database."""

    candidates: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()

    for element in elements:
        tags = element.get("tags", {})
        name = get_localized_tag(tags, "name", city)
        normalized_category = get_category(tags)
        coordinates = get_coordinates(element)

        if not name or not normalized_category or not coordinates:
            skipped["incomplete"] += 1
            continue
        if category and normalized_category != category:
            skipped["out_of_scope"] += 1
            continue

        longitude, latitude = coordinates
        if longitude is None or latitude is None:
            skipped["incomplete"] += 1
            continue

        candidates.append(
            {
                "source": "osm",
                "source_id": f"{element['type']}/{element['id']}",
                "name": name,
                "category": normalized_category,
                "description": get_description(tags, city),
                "address": get_address(tags),
                "city": city.display_name,
                "country_code": city.country_code,
                "latitude": latitude,
                "longitude": longitude,
                "price_level": None,
                "rating": None,
                "dietary_options": get_dietary_options(tags),
                **get_operational_metadata(tags),
                "lifecycle_tags": get_lifecycle_tags(tags),
                "source_payload": element,
            }
        )

    candidates.sort(
        key=lambda item: (
            item["category"],
            item["name"].casefold(),
            item["source_id"],
        )
    )
    return candidates, skipped


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect OSM places into CityBuddy staging."
    )
    parser.add_argument("--city", default="turin")
    parser.add_argument("--category")
    parser.add_argument(
        "--trigger",
        choices=("manual", "scheduled"),
        default="manual",
        help="Record why the applied collection run started.",
    )
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument(
        "--limit",
        type=int,
        help="Limit candidates after fetching, primarily for testing.",
    )
    limit_group.add_argument(
        "--limit-per-category",
        type=int,
        help="Apply a stable cap to every category in an all-category run.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write candidates to staging. Production places are never modified.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    city = get_city(arguments.city)

    if arguments.category and arguments.category not in DESTINATION_CATEGORIES:
        available = ", ".join(sorted(DESTINATION_CATEGORIES))
        raise SystemExit(
            f"Invalid category '{arguments.category}'. Available: {available}."
        )

    database = SessionLocal() if arguments.apply else None
    run = None
    try:
        if database is not None:
            run = create_ingestion_run(
                database,
                source="osm",
                city=city.display_name,
                category=arguments.category,
                trigger=arguments.trigger,
            )

        fetch_result = fetch_osm_places_with_report(
            city,
            category=arguments.category,
        )
        candidates, skipped = build_osm_candidates(
            fetch_result.elements,
            city,
            category=arguments.category,
        )
        if arguments.limit is not None:
            candidates = candidates[: max(1, arguments.limit)]
        elif arguments.limit_per_category is not None:
            candidates = limit_candidates_per_category(
                candidates,
                max(1, arguments.limit_per_category),
            )

        category_counts = Counter(
            candidate["category"] for candidate in candidates
        )
        print(f"Normalized {len(candidates)} staging candidates.")
        for candidate_category, count in sorted(category_counts.items()):
            print(f"  {candidate_category}: {count}")
        for reason, count in sorted(skipped.items()):
            print(f"Skipped {reason}: {count}")

        if database is None:
            for candidate in candidates[:20]:
                print(
                    f"  PREVIEW {candidate['source_id']} "
                    f"{candidate['category']}: {candidate['name']}"
                )
            if len(candidates) > 20:
                print(f"  ...and {len(candidates) - 20} more")
            print("Preview complete. No database changes were made.")
            return

        if run is None:
            raise RuntimeError("Applied collection did not create an ingestion run.")
        counts = stage_place_candidates(database, run, candidates)
        run_statistics: dict[str, object] = dict(counts)
        run_statistics.update(
            {f"skipped_{reason}": count for reason, count in skipped.items()}
        )
        run_statistics["successful_source_groups"] = list(
            fetch_result.successful_groups
        )
        run_statistics["failed_source_groups"] = list(
            fetch_result.failed_groups
        )
        run.statistics = run_statistics
        database.commit()
        print(f"Ingestion run {run.id} completed: {run_statistics}")
        print("Candidates were written to staging only.")
    except Exception as error:
        if database is not None and run is not None:
            database.rollback()
            saved_run = database.get(type(run), run.id)
            if saved_run is not None:
                fail_ingestion_run(database, saved_run, error)
        raise
    finally:
        if database is not None:
            database.close()


if __name__ == "__main__":
    main()
