from dataclasses import dataclass
from typing import Literal


PlaceLayer = Literal["destination", "transport"]


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    """A normalized CityBuddy category and its OSM selectors."""

    key: str
    layer: PlaceLayer
    osm_filters: tuple[str, ...]
    image_eligible: bool = False


CATEGORY_DEFINITIONS: tuple[CategoryDefinition, ...] = (
    CategoryDefinition(
        "restaurant",
        "destination",
        ('["amenity"="restaurant"]["name"]',),
    ),
    CategoryDefinition(
        "cafe",
        "destination",
        ('["amenity"="cafe"]["name"]',),
    ),
    CategoryDefinition(
        "bar",
        "destination",
        ('["amenity"="bar"]["name"]',),
    ),
    CategoryDefinition(
        "museum",
        "destination",
        ('["tourism"="museum"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "gallery",
        "destination",
        ('["tourism"="gallery"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "attraction",
        "destination",
        ('["tourism"="attraction"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "park",
        "destination",
        ('["leisure"="park"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "viewpoint",
        "destination",
        ('["tourism"="viewpoint"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "library",
        "destination",
        ('["amenity"="library"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "theatre",
        "destination",
        ('["amenity"="theatre"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "market",
        "destination",
        ('["amenity"="marketplace"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "hotel",
        "destination",
        ('["tourism"="hotel"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "hostel",
        "destination",
        ('["tourism"="hostel"]["name"]',),
        image_eligible=True,
    ),
    CategoryDefinition(
        "tourist_information",
        "destination",
        ('["tourism"="information"]["name"]',),
    ),
    CategoryDefinition(
        "train_station",
        "transport",
        (
            '["railway"="station"]["name"]',
            '["railway"="halt"]["name"]',
        ),
    ),
    CategoryDefinition(
        "metro_station",
        "transport",
        ('["station"="subway"]["name"]',),
    ),
    CategoryDefinition(
        "tram_stop",
        "transport",
        ('["railway"="tram_stop"]["name"]',),
    ),
    CategoryDefinition(
        "bus_station",
        "transport",
        ('["amenity"="bus_station"]["name"]',),
    ),
    CategoryDefinition(
        "bus_stop",
        "transport",
        ('["highway"="bus_stop"]["name"]',),
    ),
    CategoryDefinition(
        "coach_stop",
        "transport",
        (
            '["highway"="bus_stop"]["coach"="yes"]["name"]',
            '["highway"="bus_stop"]["operator"~"FlixBus",i]["name"]',
        ),
    ),
    CategoryDefinition(
        "airport",
        "transport",
        ('["aeroway"="aerodrome"]["name"]',),
    ),
)

DESTINATION_CATEGORIES = frozenset(
    definition.key
    for definition in CATEGORY_DEFINITIONS
    if definition.layer == "destination"
)

TRANSPORT_CATEGORIES = frozenset(
    definition.key
    for definition in CATEGORY_DEFINITIONS
    if definition.layer == "transport"
)

IMAGE_CATEGORIES = frozenset(
    definition.key
    for definition in CATEGORY_DEFINITIONS
    if definition.image_eligible
)


def get_category(tags: dict[str, str]) -> str | None:
    """Normalize OSM tags into a CityBuddy category."""

    tourism = tags.get("tourism")

    if tourism in {
        "museum",
        "gallery",
        "attraction",
        "viewpoint",
        "hotel",
        "hostel",
    }:
        return tourism

    if tourism == "information":
        return "tourist_information"

    amenity = tags.get("amenity")

    if amenity in {"restaurant", "cafe", "bar", "library", "theatre"}:
        return amenity

    if amenity == "marketplace":
        return "market"

    if tags.get("leisure") == "park":
        return "park"

    if tags.get("aeroway") == "aerodrome":
        return "airport"

    railway = tags.get("railway")

    if tags.get("station") == "subway" or tags.get("subway") == "yes":
        return "metro_station"

    if railway in {"station", "halt"}:
        return "train_station"

    if railway == "tram_stop":
        return "tram_stop"

    if amenity == "bus_station":
        return "coach_stop" if _is_coach_stop(tags) else "bus_station"

    if tags.get("highway") == "bus_stop":
        return "coach_stop" if _is_coach_stop(tags) else "bus_stop"

    return None


def get_osm_filters(
    *,
    layer: PlaceLayer | Literal["all"] = "destination",
    category: str | None = None,
    image_eligible_only: bool = False,
) -> tuple[str, ...]:
    """Return de-duplicated OSM filters for an ingestion scope."""

    filters: list[str] = []

    for definition in CATEGORY_DEFINITIONS:
        if layer != "all" and definition.layer != layer:
            continue

        if category and definition.key != category:
            continue

        if image_eligible_only and not definition.image_eligible:
            continue

        for osm_filter in definition.osm_filters:
            if osm_filter not in filters:
                filters.append(osm_filter)

    return tuple(filters)


def _is_coach_stop(tags: dict[str, str]) -> bool:
    searchable_values = " ".join(
        tags.get(key, "")
        for key in ("brand", "network", "operator")
    ).lower()

    return (
        tags.get("coach") == "yes"
        or tags.get("bus") == "long_distance"
        or "flixbus" in searchable_values
    )
