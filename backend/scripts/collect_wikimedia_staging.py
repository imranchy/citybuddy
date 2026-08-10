import argparse
import time
from collections import Counter
from typing import Any

import httpx
from sqlalchemy import select

from app.core.cities import get_city
from app.core.overpass import USER_AGENT
from app.core.place_catalog import IMAGE_CATEGORIES
from app.db.database import SessionLocal
from app.models.place import Place
from app.models.place_image import PlaceImage
from app.services.ingestion import (
    create_ingestion_run,
    fail_ingestion_run,
    stage_image_candidates,
)
from scripts.import_wikimedia_images import (
    fetch_commons_image,
    fetch_osm_wikidata_ids,
    fetch_wikidata_image_name,
    parse_wikidata_id,
)


def collect_image_candidates(
    database,
    *,
    city,
    limit: int | None,
    requested_wikidata_ids: frozenset[str] | None,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Collect licensed Commons candidates for reviewed production places."""

    mappings = fetch_osm_wikidata_ids(city)
    if requested_wikidata_ids is not None:
        mappings = {
            source_id: wikidata_id
            for source_id, wikidata_id in mappings.items()
            if wikidata_id in requested_wikidata_ids
        }

    places = database.scalars(
        select(Place)
        .where(
            Place.source == "osm",
            Place.city == city.display_name,
            Place.source_id.in_(mappings),
            Place.category.in_(IMAGE_CATEGORIES),
        )
        .order_by(Place.category, Place.name, Place.id)
    ).all()
    existing_place_ids = set(
        database.scalars(
            select(PlaceImage.place_id).where(
                PlaceImage.source == "wikimedia_commons"
            )
        ).all()
    )

    candidates: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=60,
        follow_redirects=True,
    ) as client:
        for place in places:
            if limit is not None and len(candidates) >= limit:
                break
            if place.id in existing_place_ids:
                skipped["already_has_commons_image"] += 1
                continue

            wikidata_id = mappings.get(place.source_id)
            if not wikidata_id:
                skipped["missing_wikidata_mapping"] += 1
                continue

            try:
                filename = fetch_wikidata_image_name(client, wikidata_id)
                if not filename:
                    skipped["missing_p18"] += 1
                    continue
                image_data = fetch_commons_image(client, filename)
                if not image_data:
                    skipped["incomplete_commons_metadata"] += 1
                    continue
            except (httpx.HTTPError, ValueError):
                skipped["request_failed"] += 1
                continue

            candidates.append(
                {
                    "place_id": place.id,
                    "place_name": place.name,
                    "place_category": place.category,
                    "wikidata_id": wikidata_id,
                    **image_data,
                    "source_payload": {
                        "wikidata_id": wikidata_id,
                        "place_source_id": place.source_id,
                        "commons_file": image_data["source_image_id"],
                    },
                }
            )
            time.sleep(0.2)

    return candidates, skipped


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Wikimedia images into CityBuddy staging."
    )
    parser.add_argument("--city", default="turin")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--wikidata-id",
        dest="wikidata_ids",
        action="append",
        type=parse_wikidata_id,
    )
    parser.add_argument(
        "--trigger",
        choices=("manual", "scheduled"),
        default="manual",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write candidates to image staging only.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    city = get_city(arguments.city)
    database = SessionLocal()
    run = None
    try:
        if arguments.apply:
            run = create_ingestion_run(
                database,
                source="wikimedia_commons",
                city=city.display_name,
                category=None,
                trigger=arguments.trigger,
            )

        candidates, skipped = collect_image_candidates(
            database,
            city=city,
            limit=(max(1, arguments.limit) if arguments.limit else None),
            requested_wikidata_ids=(
                frozenset(arguments.wikidata_ids)
                if arguments.wikidata_ids
                else None
            ),
        )
        counts = Counter(item["place_category"] for item in candidates)
        print(f"Collected {len(candidates)} image candidates.")
        for category, count in sorted(counts.items()):
            print(f"  {category}: {count}")
        for reason, count in sorted(skipped.items()):
            print(f"Skipped {reason}: {count}")

        if not arguments.apply:
            for candidate in candidates[:50]:
                print(
                    f"  PREVIEW place/{candidate['place_id']} "
                    f"{candidate['place_name']}: {candidate['source_image_id']}"
                )
            if len(candidates) > 50:
                print(f"  ...and {len(candidates) - 50} more")
            print("Preview complete. No database changes were made.")
            return

        if run is None:
            raise RuntimeError("Applied image collection did not create a run.")
        statistics = stage_image_candidates(database, run, candidates)
        statistics.update(
            {f"skipped_{reason}": count for reason, count in skipped.items()}
        )
        run.statistics = statistics
        database.commit()
        print(f"Image ingestion run {run.id} completed: {statistics}")
        print("Images were written to staging only.")
    except Exception as error:
        if run is not None:
            database.rollback()
            saved_run = database.get(type(run), run.id)
            if saved_run is not None:
                fail_ingestion_run(database, saved_run, error)
        raise
    finally:
        database.close()


if __name__ == "__main__":
    main()
