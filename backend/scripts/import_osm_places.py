import httpx
import time
from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.place import Place


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

# South, west, north, east boundaries covering Turin.
TURIN_BOUNDING_BOX = "44.9580,7.5770,45.1330,7.7730"

OSM_FILTERS = (
    '["amenity"="restaurant"]["name"]',
    '["amenity"="cafe"]["name"]',
    '["amenity"="bar"]["name"]',
    '["tourism"~"^(museum|attraction|gallery)$"]["name"]',
    '["leisure"="park"]["name"]',
)


def get_coordinates(element: dict) -> tuple[float, float] | None:
    """Return longitude and latitude for an OSM element."""

    if element["type"] == "node":
        return element.get("lon"), element.get("lat")

    center = element.get("center")

    if center:
        return center.get("lon"), center.get("lat")

    return None


def get_category(tags: dict) -> str | None:
    """Convert OpenStreetMap tags into CityBuddy categories."""

    amenity = tags.get("amenity")

    if amenity in {"restaurant", "cafe", "bar"}:
        return amenity

    tourism = tags.get("tourism")

    if tourism in {"museum", "attraction", "gallery"}:
        return tourism

    if tags.get("leisure") == "park":
        return "park"

    return None


def get_address(tags: dict) -> str:
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


def get_description(tags: dict) -> str | None:
    """Create a basic description from OSM metadata."""

    if tags.get("description"):
        return tags["description"]

    cuisine = tags.get("cuisine")

    if cuisine:
        readable_cuisine = cuisine.replace(";", ", ").replace("_", " ")
        return f"Offers {readable_cuisine} cuisine."

    return None


def get_dietary_options(tags: dict) -> list[str]:
    """Extract known dietary information from OSM tags."""

    dietary_options = []

    dietary_tags = {
        "diet:vegetarian": "vegetarian",
        "diet:vegan": "vegan",
        "diet:halal": "halal",
        "diet:gluten_free": "gluten_free",
    }

    for osm_tag, citybuddy_value in dietary_tags.items():
        if tags.get(osm_tag) in {"yes", "only"}:
            dietary_options.append(citybuddy_value)

    return dietary_options


def fetch_osm_places() -> list[dict]:
    """Download Turin places using small, retried Overpass queries."""

    collected_elements: dict[str, dict] = {}

    for osm_filter in OSM_FILTERS:
        query = f"""
        [out:json][timeout:60];
        nwr{osm_filter}({TURIN_BOUNDING_BOX});
        out center tags;
        """

        last_error: Exception | None = None

        for overpass_url in OVERPASS_URLS:
            try:
                print(f"Requesting {osm_filter} from {overpass_url}...")

                response = httpx.post(
                    overpass_url,
                    data={"data": query},
                    headers={
                        "User-Agent": "CityBuddy/0.1 development project",
                    },
                    timeout=120,
                )

                response.raise_for_status()
                elements = response.json().get("elements", [])

                for element in elements:
                    element_key = (
                        f"{element['type']}/{element['id']}"
                    )
                    collected_elements[element_key] = element

                print(f"Received {len(elements)} elements.")
                # Be respectful of shared public Overpass servers.
                time.sleep(10)
                break

            except (
                httpx.HTTPError,
                ValueError,
            ) as error:
                last_error = error
                print(f"Request failed: {error}")
                time.sleep(2)

        else:
            print(
                "Warning: all Overpass servers failed for "
                f"{osm_filter}. This category will be skipped "
                "during this run."
            )
            print(f"Last error: {last_error}")
    return list(collected_elements.values())


def import_places() -> None:
    """Import new OSM places while avoiding duplicate records."""

    print("Downloading Turin places from OpenStreetMap...")

    elements = fetch_osm_places()

    print(f"Received {len(elements)} OpenStreetMap elements.")

    database = SessionLocal()

    try:
        existing_source_ids = set(
            database.scalars(
                select(Place.source_id).where(Place.source == "osm")
            ).all()
        )

        imported_count = 0
        skipped_count = 0

        for element in elements:
            tags = element.get("tags", {})
            name = tags.get("name")
            category = get_category(tags)
            coordinates = get_coordinates(element)

            if not name or not category or not coordinates:
                skipped_count += 1
                continue

            longitude, latitude = coordinates

            if longitude is None or latitude is None:
                skipped_count += 1
                continue

            source_id = f"{element['type']}/{element['id']}"

            if source_id in existing_source_ids:
                skipped_count += 1
                continue

            place = Place(
                source="osm",
                source_id=source_id,
                name=name,
                category=category,
                description=get_description(tags),
                address=get_address(tags),
                city="Torino",
                country_code="IT",
                location=WKTElement(
                    f"POINT({longitude} {latitude})",
                    srid=4326,
                ),
                price_level=None,
                rating=None,
                dietary_options=get_dietary_options(tags),
            )

            database.add(place)
            existing_source_ids.add(source_id)
            imported_count += 1

        database.commit()

        print(f"Imported {imported_count} new places.")
        print(f"Skipped {skipped_count} existing or incomplete places.")

    except Exception:
        database.rollback()
        raise

    finally:
        database.close()


if __name__ == "__main__":
    import_places()