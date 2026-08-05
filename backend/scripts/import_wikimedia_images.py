import argparse
import html
import re
import time

import httpx
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.place import Place
from app.models.place_image import PlaceImage


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIMEDIA_COMMONS_API_URL = (
    "https://commons.wikimedia.org/w/api.php"
)

TURIN_BOUNDING_BOX = "44.9580,7.5770,45.1330,7.7730"

SUPPORTED_CATEGORIES = {
    "museum",
    "gallery",
    "attraction",
    "park",
}

USER_AGENT = (
    "CityBuddy/0.1 "
    "(https://github.com/imranchy/citybuddy)"
)


def strip_html(value: str | None) -> str:
    """Convert simple Wikimedia HTML metadata into plain text."""

    if not value:
        return ""

    without_tags = re.sub(r"<[^>]+>", "", value)
    return html.unescape(without_tags).strip()


def get_category(tags: dict) -> str | None:
    """Convert relevant OSM tags into CityBuddy categories."""

    tourism = tags.get("tourism")

    if tourism in {"museum", "gallery", "attraction"}:
        return tourism

    if tags.get("leisure") == "park":
        return "park"

    return None


def fetch_osm_wikidata_ids() -> dict[str, str]:
    """Map CityBuddy OSM source IDs to explicit Wikidata IDs."""

    query = f"""
    [out:json][timeout:120];
    (
      nwr["tourism"~"^(museum|gallery|attraction)$"]
         ["wikidata"]({TURIN_BOUNDING_BOX});
      nwr["leisure"="park"]
         ["wikidata"]({TURIN_BOUNDING_BOX});
    );
    out tags;
    """

    last_error: Exception | None = None

    for overpass_url in OVERPASS_URLS:
        try:
            print(
                "Requesting OSM Wikidata references from "
                f"{overpass_url}..."
            )

            response = httpx.post(
                overpass_url,
                data={"data": query},
                headers={"User-Agent": USER_AGENT},
                timeout=180,
            )
            response.raise_for_status()

            mappings: dict[str, str] = {}

            for element in response.json().get("elements", []):
                tags = element.get("tags", {})
                category = get_category(tags)
                wikidata_id = tags.get("wikidata")

                if (
                    category not in SUPPORTED_CATEGORIES
                    or not wikidata_id
                ):
                    continue

                source_id = (
                    f"{element['type']}/{element['id']}"
                )
                mappings[source_id] = wikidata_id

            return mappings

        except (httpx.HTTPError, ValueError) as error:
            last_error = error
            print(f"Request failed: {error}")
            time.sleep(2)

    raise RuntimeError(
        "All Overpass requests failed."
    ) from last_error


def fetch_wikidata_image_name(
    client: httpx.Client,
    wikidata_id: str,
) -> str | None:
    """Return the Wikidata P18 image filename."""

    response = client.get(
        WIKIDATA_API_URL,
        params={
            "action": "wbgetentities",
            "ids": wikidata_id,
            "props": "claims",
            "format": "json",
            "formatversion": 2,
        },
    )
    response.raise_for_status()

    entity = (
        response.json()
        .get("entities", {})
        .get(wikidata_id, {})
    )

    claims = entity.get("claims", {})
    image_claims = claims.get("P18", [])

    if not image_claims:
        return None

    try:
        return image_claims[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, TypeError):
        return None


def metadata_value(
    metadata: dict,
    key: str,
) -> str:
    """Read a value from Wikimedia extmetadata."""

    item = metadata.get(key, {})

    if not isinstance(item, dict):
        return ""

    value = item.get("value")

    if not isinstance(value, str):
        return ""

    return strip_html(value)


def fetch_commons_image(
    client: httpx.Client,
    filename: str,
) -> dict | None:
    """Fetch URLs, attribution and licence metadata from Commons."""

    title = filename

    if not title.startswith("File:"):
        title = f"File:{title}"

    response = client.get(
        WIKIMEDIA_COMMONS_API_URL,
        params={
            "action": "query",
            "prop": "imageinfo",
            "titles": title,
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1200,
            "iiextmetadatalanguage": "en",
            "format": "json",
            "formatversion": 2,
        },
    )
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", [])

    if not pages:
        return None

    page = pages[0]

    if page.get("missing"):
        return None

    image_info_list = page.get("imageinfo", [])

    if not image_info_list:
        return None

    image_info = image_info_list[0]
    metadata = image_info.get("extmetadata", {})

    image_url = image_info.get("url")
    source_page_url = image_info.get("descriptionurl")
    licence = metadata_value(metadata, "LicenseShortName")
    licence_url = metadata_value(metadata, "LicenseUrl")
    attribution = (
        metadata_value(metadata, "Artist")
        or metadata_value(metadata, "Credit")
        or "Wikimedia Commons contributor"
    )

    if not image_url or not source_page_url or not licence:
        return None

    return {
        "source": "wikimedia_commons",
        "source_image_id": title,
        "image_url": image_url,
        "thumbnail_url": image_info.get("thumburl"),
        "source_page_url": source_page_url,
        "attribution": attribution,
        "license": licence,
        "license_url": licence_url or None,
    }


def import_images(
    *,
    apply_changes: bool,
    limit: int,
) -> None:
    """Find reliable Wikimedia images for supported places."""

    osm_wikidata_ids = fetch_osm_wikidata_ids()

    print(
        f"Found {len(osm_wikidata_ids)} OSM places "
        "with Wikidata references."
    )

    database = SessionLocal()

    try:
        places = database.scalars(
            select(Place)
            .where(
                Place.source == "osm",
                Place.source_id.in_(osm_wikidata_ids),
                Place.category.in_(SUPPORTED_CATEGORIES),
            )
            .order_by(Place.name)
        ).all()

        existing_place_ids = set(
            database.scalars(
                select(PlaceImage.place_id).where(
                    PlaceImage.source == "wikimedia_commons"
                )
            ).all()
        )

        imported_count = 0
        previewed_count = 0
        skipped_count = 0

        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=60,
            follow_redirects=True,
        ) as client:
            for place in places:
                if imported_count + previewed_count >= limit:
                    break

                if place.id in existing_place_ids:
                    skipped_count += 1
                    continue

                wikidata_id = osm_wikidata_ids.get(
                    place.source_id
                )

                if not wikidata_id:
                    skipped_count += 1
                    continue

                try:
                    filename = fetch_wikidata_image_name(
                        client,
                        wikidata_id,
                    )

                    if not filename:
                        skipped_count += 1
                        continue

                    image_data = fetch_commons_image(
                        client,
                        filename,
                    )

                    if not image_data:
                        skipped_count += 1
                        continue

                    print()
                    print(f"Place: {place.name}")
                    print(f"Category: {place.category}")
                    print(f"Wikidata: {wikidata_id}")
                    print(
                        "Commons file: "
                        f"{image_data['source_image_id']}"
                    )
                    print(
                        "Licence: "
                        f"{image_data['license']}"
                    )
                    print(
                        "Source page: "
                        f"{image_data['source_page_url']}"
                    )

                    if not apply_changes:
                        previewed_count += 1
                        continue

                    place_image = PlaceImage(
                        place_id=place.id,
                        is_primary=True,
                        **image_data,
                    )

                    database.add(place_image)
                    existing_place_ids.add(place.id)
                    imported_count += 1

                    time.sleep(0.2)

                except (httpx.HTTPError, ValueError) as error:
                    print(
                        f"Skipping {place.name} because "
                        f"the Wikimedia request failed: {error}"
                    )
                    skipped_count += 1

        if apply_changes:
            database.commit()
            print(f"Imported {imported_count} images.")
        else:
            database.rollback()
            print(
                f"Previewed {previewed_count} images. "
                "No database changes were made."
            )

        print(f"Skipped {skipped_count} places.")

    except Exception:
        database.rollback()
        raise

    finally:
        database.close()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import reliably linked Wikimedia Commons images "
            "for CityBuddy places."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Save discovered images to the database.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of images to preview or import.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()

    import_images(
        apply_changes=arguments.apply,
        limit=max(1, arguments.limit),
    )