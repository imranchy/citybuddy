from sqlalchemy.orm import Session

from app.services.official_site import OfficialPageType, OfficialSiteEvidence, fetch_official_site
from app.services.place_discovery import retrieve_place_by_id


def get_official_place_page(
    database: Session,
    *,
    place_id: int,
    page_type: OfficialPageType,
    query: str | None = None,
) -> OfficialSiteEvidence:
    """Retrieve live evidence only from a reviewed place's stored official website."""

    if place_id <= 0:
        raise ValueError("place_id must be a positive CityBuddy place ID")

    place = retrieve_place_by_id(database, place_id=place_id)
    if place is None:
        raise ValueError(f"No reviewed CityBuddy place exists with ID {place_id}.")
    if not place.website:
        raise ValueError(f"Reviewed CityBuddy place {place_id} has no official website stored.")

    return fetch_official_site(
        place_id=place.id,
        place_name=place.name,
        website=place.website,
        page_type=page_type,
        query=query,
    )
