from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CategoryDefinition:
    """A normalized CityBuddy category and its OSM selectors."""

    key: str
    label: str
    group: str
    osm_filters: tuple[str, ...]
    image_eligible: bool = False


CATEGORY_GROUP_LABELS = {
    "food_drink": "Food & Drink",
    "culture_attractions": "Culture & Attractions",
    "nature_recreation": "Nature & Recreation",
    "nightlife": "Nightlife",
    "shopping_markets": "Shopping & Markets",
    "learning_community": "Learning & Community",
    "places_of_worship": "Places of Worship",
    "accommodation": "Accommodation",
}


CATEGORY_DEFINITIONS: tuple[CategoryDefinition, ...] = (
    CategoryDefinition("restaurant", "Restaurant", "food_drink", ('["amenity"="restaurant"]["name"]',)),
    CategoryDefinition("cafe", "Cafe", "food_drink", ('["amenity"="cafe"]["name"]',)),
    CategoryDefinition("bar", "Bar", "food_drink", ('["amenity"="bar"]["name"]',)),
    CategoryDefinition("pub", "Pub", "food_drink", ('["amenity"="pub"]["name"]',)),
    CategoryDefinition("fast_food", "Fast Food", "food_drink", ('["amenity"="fast_food"]["name"]',)),
    CategoryDefinition("museum", "Museum", "culture_attractions", ('["tourism"="museum"]["name"]',), True),
    CategoryDefinition("gallery", "Gallery", "culture_attractions", ('["tourism"="gallery"]["name"]',), True),
    CategoryDefinition("attraction", "Attraction", "culture_attractions", ('["tourism"="attraction"]["name"]',), True),
    CategoryDefinition("theatre", "Theatre", "culture_attractions", ('["amenity"="theatre"]["name"]',), True),
    CategoryDefinition("monument", "Monument", "culture_attractions", ('["historic"="monument"]["name"]',), True),
    CategoryDefinition("historic_site", "Historic Site", "culture_attractions", ('["historic"]["name"]',), True),
    CategoryDefinition("viewpoint", "Viewpoint", "culture_attractions", ('["tourism"="viewpoint"]["name"]',), True),
    CategoryDefinition("park", "Park", "nature_recreation", ('["leisure"="park"]["name"]',), True),
    CategoryDefinition("garden", "Garden", "nature_recreation", ('["leisure"="garden"]["name"]',), True),
    CategoryDefinition("playground", "Playground", "nature_recreation", ('["leisure"="playground"]["name"]',)),
    CategoryDefinition("fitness_centre", "Fitness Centre", "nature_recreation", ('["leisure"="fitness_centre"]["name"]',)),
    CategoryDefinition("sports_centre", "Sports Centre", "nature_recreation", ('["leisure"="sports_centre"]["name"]',)),
    CategoryDefinition("nightclub", "Nightclub", "nightlife", ('["amenity"="nightclub"]["name"]',)),
    CategoryDefinition("music_venue", "Music Venue", "nightlife", ('["amenity"="music_venue"]["name"]',), True),
    CategoryDefinition("market", "Market", "shopping_markets", ('["amenity"="marketplace"]["name"]',), True),
    CategoryDefinition("supermarket", "Supermarket", "shopping_markets", ('["shop"="supermarket"]["name"]',)),
    CategoryDefinition("shopping_centre", "Shopping Centre", "shopping_markets", ('["shop"="mall"]["name"]',), True),
    CategoryDefinition("library", "Library", "learning_community", ('["amenity"="library"]["name"]',), True),
    CategoryDefinition("community_centre", "Community Centre", "learning_community", ('["amenity"="community_centre"]["name"]',)),
    CategoryDefinition("tourist_information", "Tourist Information", "learning_community", ('["tourism"="information"]["information"="office"]["name"]',)),
    CategoryDefinition("church", "Church", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="christian"]["name"]',), True),
    CategoryDefinition("mosque", "Mosque", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="muslim"]["name"]',), True),
    CategoryDefinition("synagogue", "Synagogue", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="jewish"]["name"]',), True),
    CategoryDefinition("hindu_temple", "Hindu Temple", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="hindu"]["name"]',), True),
    CategoryDefinition("buddhist_temple", "Buddhist Temple", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="buddhist"]["name"]',), True),
    CategoryDefinition("gurdwara", "Gurdwara", "places_of_worship", ('["amenity"="place_of_worship"]["religion"="sikh"]["name"]',), True),
    CategoryDefinition("place_of_worship", "Other Place of Worship", "places_of_worship", ('["amenity"="place_of_worship"][!"religion"]["name"]',), True),
    CategoryDefinition("hotel", "Hotel", "accommodation", ('["tourism"="hotel"]["name"]',), True),
    CategoryDefinition("hostel", "Hostel", "accommodation", ('["tourism"="hostel"]["name"]',), True),
)

DESTINATION_CATEGORIES = frozenset(item.key for item in CATEGORY_DEFINITIONS)
IMAGE_CATEGORIES = frozenset(item.key for item in CATEGORY_DEFINITIONS if item.image_eligible)


def get_category(tags: dict[str, str]) -> str | None:
    """Normalize OSM tags into a CityBuddy discovery category."""

    tourism = tags.get("tourism")
    if tourism in {"museum", "gallery", "attraction", "viewpoint", "hotel", "hostel"}:
        return tourism
    if tourism == "information" and tags.get("information") == "office":
        return "tourist_information"

    amenity = tags.get("amenity")
    if amenity == "place_of_worship":
        religion = tags.get("religion")
        building = tags.get("building")
        worship_categories = {
            "christian": "church", "muslim": "mosque", "jewish": "synagogue",
            "hindu": "hindu_temple", "buddhist": "buddhist_temple", "sikh": "gurdwara",
        }
        building_categories = {
            "church": "church", "cathedral": "church", "chapel": "church",
            "mosque": "mosque", "synagogue": "synagogue", "temple": "place_of_worship",
        }
        return worship_categories.get(religion, building_categories.get(building, "place_of_worship"))

    amenity_categories = {
        "restaurant", "cafe", "bar", "pub", "fast_food", "library", "theatre",
        "community_centre", "nightclub", "music_venue",
    }
    if amenity in amenity_categories:
        return amenity
    if amenity == "marketplace":
        return "market"

    leisure = tags.get("leisure")
    if leisure in {"park", "garden", "playground", "fitness_centre", "sports_centre"}:
        return leisure
    if tags.get("shop") == "supermarket":
        return "supermarket"
    if tags.get("shop") == "mall":
        return "shopping_centre"
    if tags.get("historic") == "monument":
        return "monument"
    if tags.get("historic"):
        return "historic_site"
    return None


def get_osm_filters(*, category: str | None = None, image_eligible_only: bool = False) -> tuple[str, ...]:
    """Return de-duplicated OSM filters for the discovery catalog."""

    filters: list[str] = []
    for definition in CATEGORY_DEFINITIONS:
        if category and definition.key != category:
            continue
        if image_eligible_only and not definition.image_eligible:
            continue
        for osm_filter in definition.osm_filters:
            if osm_filter not in filters:
                filters.append(osm_filter)
    return tuple(filters)


def group_categories(categories: Iterable[str]) -> list[dict[str, object]]:
    """Group available leaf categories in stable product-display order."""

    available = set(categories)
    groups: list[dict[str, object]] = []
    for group_key, group_label in CATEGORY_GROUP_LABELS.items():
        options = [
            {"key": item.key, "label": item.label}
            for item in CATEGORY_DEFINITIONS
            if item.group == group_key and item.key in available
        ]
        if options:
            groups.append({"key": group_key, "label": group_label, "categories": options})
    return groups
