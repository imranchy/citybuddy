import argparse
from collections import Counter
from dataclasses import dataclass

from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.core.cities import CityConfig, get_city
from app.core.overpass import fetch_overpass_json
from app.core.place_catalog import (
    CATEGORY_DEFINITIONS,
    CATEGORY_GROUP_LABELS,
    DESTINATION_CATEGORIES,
    get_category,
    get_osm_filters,
)
from app.db.database import SessionLocal
from app.models.place import Place


@dataclass(frozen=True, slots=True)
class OsmFetchResult:
    elements: list[dict]
    successful_groups: tuple[str, ...]
    failed_groups: tuple[str, ...]


def get_osm_filter_batches(
    *,
    category: str | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Group selectors into a small number of product-aligned requests."""

    if category:
        return ((category, get_osm_filters(category=category)),)

    batches: list[tuple[str, tuple[str, ...]]] = []
    for group_key in CATEGORY_GROUP_LABELS:
        filters: list[str] = []
        for definition in CATEGORY_DEFINITIONS:
            if definition.group != group_key:
                continue
            for osm_filter in definition.osm_filters:
                if osm_filter not in filters:
                    filters.append(osm_filter)
        if filters:
            batches.append((group_key, tuple(filters)))
    return tuple(batches)


def fetch_osm_places_with_report(
    city: CityConfig,
    *,
    category: str | None,
) -> OsmFetchResult:
    """Download OSM places while preserving successful source groups."""

    collected_elements: dict[str, dict] = {}
    successful_groups: list[str] = []
    failed_groups: list[str] = []

    for group_key, osm_filters in get_osm_filter_batches(category=category):
        selectors = "\n".join(
            f"nwr{osm_filter}({city.overpass_bounding_box});"
            for osm_filter in osm_filters
        )
        query = f"""
        [out:json][timeout:180];
        (
          {selectors}
        );
        out center tags;
        """
        try:
            payload, endpoint = fetch_overpass_json(
                query,
                timeout_seconds=240,
            )
        except RuntimeError as error:
            failed_groups.append(group_key)
            print(f"Source group {group_key} failed and remains pending: {error}")
            continue

        elements = payload.get("elements", [])
        timestamp = payload.get("osm3s", {}).get("timestamp_osm_base")
        for element in elements:
            element = dict(element)
            element["_citybuddy_source_endpoint"] = endpoint
            element["_citybuddy_source_group"] = group_key
            if timestamp:
                element["_citybuddy_source_timestamp"] = timestamp
            element_key = f"{element['type']}/{element['id']}"
            collected_elements[element_key] = element
        successful_groups.append(group_key)
        print(f"Received {len(elements)} elements for source group {group_key}.")

    if not successful_groups:
        raise RuntimeError("Every requested Overpass source group failed.")

    return OsmFetchResult(
        elements=list(collected_elements.values()),
        successful_groups=tuple(successful_groups),
        failed_groups=tuple(failed_groups),
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


def get_operational_metadata(
    tags: dict[str, str],
) -> dict[str, str | None]:
    """Extract operational place metadata from OSM tags."""

    return {
        "opening_hours": tags.get("opening_hours"),
        "website": (
            tags.get("website")
            or tags.get("contact:website")
        ),
        "operator": tags.get("operator"),
    }


def fetch_osm_places(
    city: CityConfig,
    *,
    category: str | None,
) -> list[dict]:
    """Download configured places for legacy direct-import callers."""

    return fetch_osm_places_with_report(
        city,
        category=category,
    ).elements


def print_counts(title: str, counts: Counter[str]) -> None:
    print(title)

    if not counts:
        print("  none")
        return

    for category, count in sorted(counts.items()):
        print(f"  {category}: {count}")


def filter_candidates_by_source_ids(
    candidates: list[tuple[dict, str, str, float, float]],
    source_ids: frozenset[str] | None,
) -> list[tuple[dict, str, str, float, float]]:
    """Keep only candidates with explicitly approved OSM source IDs."""

    if source_ids is None:
        return candidates

    return [
        item
        for item in candidates
        if f"{item[0]['type']}/{item[0]['id']}" in source_ids
    ]


def get_lifecycle_tags(tags: dict[str, str]) -> list[str]:
    """Return OSM lifecycle tags that may indicate inactive features."""

    lifecycle_prefixes = (
        "abandoned",
        "construction",
        "demolished",
        "disused",
        "proposed",
        "razed",
    )

    return sorted(
        f"{key}={value}"
        for key, value in tags.items()
        if key in lifecycle_prefixes
        or key.startswith(
            tuple(f"{prefix}:" for prefix in lifecycle_prefixes)
        )
    )


def print_candidate_details(
    candidate: tuple[dict, str, str, float, float],
) -> None:
    """Print evidence needed for human review of an OSM candidate."""

    element, name, normalized_category, longitude, latitude = candidate
    tags = element.get("tags", {})
    source_id = f"{element['type']}/{element['id']}"
    lifecycle_tags = get_lifecycle_tags(tags)

    print()
    print(f"  PREVIEW {normalized_category}: {name}")
    print(f"    Source ID: {source_id}")
    print(f"    Coordinates: {latitude:.6f}, {longitude:.6f}")
    print(f"    Address: {get_address(tags)}")
    print(f"    Operator: {tags.get('operator', 'Not provided')}")
    print(
        "    Opening hours: "
        f"{tags.get('opening_hours', 'Not provided')}"
    )
    print(
        "    Website: "
        f"{tags.get('website') or tags.get('contact:website') or 'Not provided'}"
    )
    print(
        "    Lifecycle tags: "
        f"{', '.join(lifecycle_tags) if lifecycle_tags else 'None declared'}"
    )

def validate_refresh_request(
    refresh_existing: bool,
    source_ids: frozenset[str] | None,
) -> None:
    """Require an explicit source allowlist for existing-record refreshes."""

    if refresh_existing and source_ids is None:
        raise ValueError(
            "--refresh-existing requires at least one --source-id."
        )

def import_places(
    city: CityConfig,
    *,
    category: str | None,
    apply_changes: bool,
    limit: int | None,
    source_ids: frozenset[str] | None = None,
    show_details: bool = False,
    refresh_existing: bool = False,
) -> None:
    """Preview or import OSM places while avoiding duplicate records."""
    validate_refresh_request(refresh_existing, source_ids)
    print(
        f"Downloading discovery data for {city.display_name}, "
        f"{city.country_code}..."
    )

    elements = fetch_osm_places(city, category=category)
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
        existing_places_by_source_id = {
            place.source_id: place
            for place in database.scalars(
                select(Place).where(Place.source == "osm")
            ).all()
        }
        existing_source_ids = set(existing_places_by_source_id)

        all_candidates = [
            item
            for item in valid_elements
            if f"{item[0]['type']}/{item[0]['id']}"
            not in existing_source_ids
        ]

        existing_count = len(valid_elements) - len(all_candidates)
        approval_excluded_count = 0
        refresh_candidates: list[
            tuple[dict, str, str, float, float]
        ] = []

        if source_ids is not None:
            approved_candidates = filter_candidates_by_source_ids(
                all_candidates,
                source_ids,
            )
            approval_excluded_count = (
                len(all_candidates) - len(approved_candidates)
            )
            all_candidates = approved_candidates

        if refresh_existing:
            refresh_candidates = [
                item
                for item in filter_candidates_by_source_ids(
                    valid_elements,
                    source_ids,
                )
                if (
                    f"{item[0]['type']}/{item[0]['id']}"
                    in existing_source_ids
                )
            ]

        candidates = all_candidates

        if limit is not None:
            candidates = candidates[:limit]

        candidate_counts = Counter(item[2] for item in candidates)
        print_counts("New records eligible for this run:", candidate_counts)

        if source_ids is not None:
            print(
                "New records excluded by source-ID allowlist: "
                f"{approval_excluded_count}"
            )

        if show_details:
            for candidate in candidates:
                print_candidate_details(candidate)
        else:
            for _, name, normalized_category, _, _ in candidates[:20]:
                print(f"  PREVIEW {normalized_category}: {name}")

            if len(candidates) > 20:
                print(f"  ...and {len(candidates) - 20} more")

        if refresh_existing:
            refresh_counts = Counter(
                item[2] for item in refresh_candidates
            )
            print_counts(
                "Existing records eligible for metadata refresh:",
                refresh_counts,
            )

            for candidate in refresh_candidates:
                if show_details:
                    print_candidate_details(candidate)
                else:
                    _, name, normalized_category, _, _ = candidate
                    print(f"  REFRESH {normalized_category}: {name}")

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

        for element, _, _, _, _ in refresh_candidates:
            source_id = f"{element['type']}/{element['id']}"
            existing_place = existing_places_by_source_id[source_id]
            metadata = get_operational_metadata(
                element.get("tags", {})
            )

            existing_place.opening_hours = metadata["opening_hours"]
            existing_place.website = metadata["website"]
            existing_place.operator = metadata["operator"]

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
                    **get_operational_metadata(tags),
                )
            )

        database.commit()
        print(f"Imported {len(candidates)} new places.")
        print(
            "Refreshed operational metadata for "
            f"{len(refresh_candidates)} existing places."
        )
        print(
            "Existing records skipped: "
            f"{existing_count - len(refresh_candidates)}"
        )

        print(f"Incomplete records skipped: {incomplete_count}")
        print(f"Out-of-scope records skipped: {out_of_scope_count}")

    except Exception:
        database.rollback()
        raise

    finally:
        database.close()


def parse_osm_source_id(value: str) -> str:
    """Validate and normalize an OSM element source ID."""

    normalized_value = value.strip().lower()
    parts = normalized_value.split("/", maxsplit=1)

    if (
        len(parts) != 2
        or parts[0] not in {"node", "way", "relation"}
        or not parts[1].isdigit()
        or int(parts[1]) < 1
    ):
        raise argparse.ArgumentTypeError(
            "OSM source IDs must look like node/123, "
            "way/123, or relation/123."
        )

    return normalized_value


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
        "--category",
        help="Optionally restrict ingestion to one normalized category.",
    )
    parser.add_argument(
        "--source-id",
        dest="source_ids",
        action="append",
        type=parse_osm_source_id,
        help=(
            "Only process an explicitly approved OSM source ID. "
            "Repeat this option to approve multiple IDs."
        ),
    )
    parser.add_argument(
        "--show-details",
        action="store_true",
        help=(
            "Show source IDs and review metadata for every candidate."
        ),
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help=(
            "Refresh operational metadata for explicitly approved "
            "existing OSM records. Requires --source-id."
        ),
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

    if arguments.category and arguments.category not in DESTINATION_CATEGORIES:
        available = ", ".join(sorted(DESTINATION_CATEGORIES))
        raise SystemExit(
            f"Invalid category '{arguments.category}'. "
            f"Available categories: {available}."
        )

    if arguments.refresh_existing and not arguments.source_ids:
        raise SystemExit(
            "--refresh-existing requires at least one --source-id."
        )

    import_places(
        selected_city,
        category=arguments.category,
        apply_changes=arguments.apply,
        limit=(
            max(1, arguments.limit)
            if arguments.limit is not None
            else None
        ),
        source_ids=(
            frozenset(arguments.source_ids)
            if arguments.source_ids
            else None
        ),
        show_details=arguments.show_details,
        refresh_existing=arguments.refresh_existing,
    )
