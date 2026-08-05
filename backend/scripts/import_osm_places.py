import_osm_places.py


import argparse
import time
from collections import Counter

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.core.cities import CityConfig, get_city
from app.core.place_catalog import (
    DESTINATION_CATEGORIES,
    TRANSPORT_CATEGORIES,
    PlaceLayer,
    get_category,
    get_osm_filters,
)
from app.db.database import SessionLocal
from app.models.place import Place


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

USER_AGENT = (
    "CityBuddy/0.1 "
    "(https://github.com/imranchy/citybuddy)"
)


def get_coordinates(element: dict) -> tuple[float, float] | None:
    """Return longitude and latitude for an OSM element."""

    if element["type"] == "node":
        return element.get("lon"), element.get("lat")

    center = element.get("center")

    if center:
        return center.get("lon"), center.get("lat")

    return None


def get_localized_tag(
    tags: dict[str, str],
    key: str,
    city: CityConfig,
) -> str | None:
    """Prefer local-language OSM content, then the generic value."""

    return (
        tags.get(f"{key}:{city.default_language}")
        or tags.get(key)
        or tags.get(f"{key}:en")
    )


def get_address(tags: dict[str, str]) -> str:
    """Construct a readable address from available OSM tags."""

    if tags.get("addr:full"):
        return tags["addr:full"]

    street = tags.get("addr:street")
    house_number = tags.get("addr:housenumber")

    if street and house_number:
        return f"{street} {house_number}"

    if street:
        return street

    return "Address unavailable"


def get_description(
    tags: dict[str, str],
    city: CityConfig,
) -> str | None:
    """Create a description from local OSM metadata when available."""

    description = get_localized_tag(tags, "description", city)

    if description:
        return description

    cuisine = tags.get("cuisine")

    if cuisine:
        readable_cuisine = cuisine.replace(";", ", ").replace("_", " ")
        return f"Offers {readable_cuisine} cuisine."

    return None


def get_dietary_options(tags: dict[str, str]) -> list[str]:
    """Extract known dietary information from OSM tags."""

    dietary_tags = {
        "diet:vegetarian": "vegetarian",
        "diet:vegan": "vegan",
        "diet:halal": "halal",
        "diet:gluten_free": "gluten_free",
    }

    return [
        citybuddy_value
        for osm_tag, citybuddy_value in dietary_tags.items()
        if tags.get(osm_tag) in {"yes", "only"}
    ]


def fetch_osm_places(
    city: CityConfig,
    *,
    layer: PlaceLayer,
    category: str | None,
) -> list[dict]:
    """Download configured places using small, retried Overpass queries."""

    osm_filters = get_osm_filters(layer=layer, category=category)

    if not osm_filters:
        raise ValueError(
            f"Category '{category}' is not part of the {layer} layer."
        )

    collected_elements: dict[str, dict] = {}

    for osm_filter in osm_filters:
        query = f"""
        [out:json][timeout:60];
        nwr{osm_filter}({city.overpass_bounding_box});
        out center tags;
        """

        last_error: Exception | None = None

        for overpass_url in OVERPASS_URLS:
            try:
                print(f"Requesting {osm_filter} from {overpass_url}...")

                response = httpx.post(
                    overpass_url,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=120,
                )
                response.raise_for_status()
                elements = response.json().get("elements", [])

                for element in elements:
                    element_key = f"{element['type']}/{element['id']}"
                    collected_elements[element_key] = element

                print(f"Received {len(elements)} elements.")
                time.sleep(5)
                break

            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                print(f"Request failed: {error}")
                time.sleep(2)

        else:
            print(
                "Warning: all Overpass servers failed for "
                f"{osm_filter}; that source filter was skipped."
            )
            print(f"Last error: {last_error}")

    return list(collected_elements.values())


def print_counts(title: str, counts: Counter[str]) -> None:
    print(title)

    if not counts:
        print("  none")
        return

    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")


def import_places(
    city: CityConfig,
    *,
    layer: PlaceLayer,
    category: str | None,
    apply_changes: bool,
    limit: int | None,
) -> None:
    """Preview or import OSM places while avoiding duplicate records."""

    print(
        f"Downloading {layer} data for {city.display_name}, "
        f"{city.country_code}..."
    )

    elements = fetch_osm_places(city, layer=layer, category=category)
    fetched_counts: Counter[str] = Counter()
    valid_elements: list[tuple[dict, str, str, float, float]] = []
    incomplete_count = 0
    out_of_scope_count = 0

    for element in elements:
        tags = element.get("tags", {})
        name = get_localized_tag(tags, "name", city)
        normalized_category = get_category(tags)
        coordinates = get_coordinates(element)

        if not name or not normalized_category or not coordinates:
            incomplete_count += 1
            continue

        if category and normalized_category != category:
            out_of_scope_count += 1
            continue

        longitude, latitude = coordinates

        if longitude is None or latitude is None:
            incomplete_count += 1
            continue

        fetched_counts[normalized_category] += 1
        valid_elements.append(
            (element, name, normalized_category, longitude, latitude)
        )

    print_counts("Valid records returned by OSM:", fetched_counts)

    database = SessionLocal()

    try:
        existing_source_ids = set(
            database.scalars(
                select(Place.source_id).where(Place.source == "osm")
            ).all()
        )

        all_candidates = [
            item
            for item in valid_elements
            if f"{item[0]['type']}/{item[0]['id']}"
            not in existing_source_ids
        ]

        existing_count = len(valid_elements) - len(all_candidates)
        candidates = all_candidates

        if limit is not None:
            candidates = candidates[:limit]

        candidate_counts = Counter(item[2] for item in candidates)
        print_counts("New records eligible for this run:", candidate_counts)

        for _, name, normalized_category, _, _ in candidates[:20]:
            print(f"  PREVIEW {normalized_category}: {name}")

        if len(candidates) > 20:
            print(f"  ...and {len(candidates) - 20} more")

        if limit is not None and len(all_candidates) > len(candidates):
            print(
                "New records deferred by this run's limit: "
                f"{len(all_candidates) - len(candidates)}"
            )

        if not apply_changes:
            database.rollback()
            print("Preview complete. No database changes were made.")
            print(f"Incomplete records skipped: {incomplete_count}")
            print(f"Out-of-scope records skipped: {out_of_scope_count}")
            return

        for (
            element,
            name,
            normalized_category,
            longitude,
            latitude,
        ) in candidates:
            tags = element.get("tags", {})
            source_id = f"{element['type']}/{element['id']}"

            database.add(
                Place(
                    source="osm",
                    source_id=source_id,
                    name=name,
                    category=normalized_category,
                    description=get_description(tags, city),
                    address=get_address(tags),
                    city=city.display_name,
                    country_code=city.country_code,
                    location=WKTElement(
                        f"POINT({longitude} {latitude})",
                        srid=4326,
                    ),
                    price_level=None,
                    rating=None,
                    dietary_options=get_dietary_options(tags),
                )
            )

        database.commit()
        print(f"Imported {len(candidates)} new places.")
        print(f"Existing records skipped: {existing_count}")

        print(f"Incomplete records skipped: {incomplete_count}")
        print(f"Out-of-scope records skipped: {out_of_scope_count}")

        if layer == "transport":
            print(
                "Transport records are stored for the future transport "
                "layer and are excluded from destination endpoints."
            )

    except Exception:
        database.rollback()
        raise

    finally:
        database.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or import configured OSM data for CityBuddy."
    )
    parser.add_argument(
        "--city",
        default="turin",
        help="Configured city key (default: turin).",
    )
    parser.add_argument(
        "--layer",
        choices=("destination", "transport"),
        default="destination",
        help="Data layer to ingest (default: destination).",
    )
    parser.add_argument(
        "--category",
        help="Optionally restrict ingestion to one normalized category.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of new records to preview or import.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save the previewed records to the database.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()

    try:
        selected_city = get_city(arguments.city)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    allowed_categories = (
        DESTINATION_CATEGORIES
        if arguments.layer == "destination"
        else TRANSPORT_CATEGORIES
    )

    if arguments.category and arguments.category not in allowed_categories:
        available = ", ".join(sorted(allowed_categories))
        raise SystemExit(
            f"Invalid {arguments.layer} category '{arguments.category}'. "
            f"Available categories: {available}."
        )

    import_places(
        selected_city,
        layer=arguments.layer,
        category=arguments.category,
        apply_changes=arguments.apply,
        limit=(
            max(1, arguments.limit)
            if arguments.limit is not None
            else None
        ),
    )