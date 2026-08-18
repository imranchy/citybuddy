from typing import Annotated

from mcp.server import MCPServer
from pydantic import Field

from app.db.database import SessionLocal
from app.schemas.place import PlaceRead
from app.services.official_site import OfficialPageType, OfficialSiteEvidence
from app.tools.citybuddy import PlaceSearchInput, PlaceSearchResult, get_place, search_places
from app.tools.official_site import get_official_place_page as retrieve_official_place_page


mcp = MCPServer(
    "CityBuddy",
    instructions=(
        "Use only these bounded CityBuddy tools for reviewed place data and controlled "
        "official-site evidence. This server does not expose arbitrary SQL, caller-supplied "
        "URLs, shell commands, filesystem access, generic web search, or production writes."
    ),
)


@mcp.tool()
def search_citybuddy_places(
    city: Annotated[str, Field(min_length=1, max_length=100)],
    categories: Annotated[list[str] | None, Field(max_length=8)] = None,
    limit: Annotated[int, Field(ge=1, le=10)] = 5,
    latitude: Annotated[float | None, Field(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Field(ge=-180, le=180)] = None,
    radius_km: Annotated[float | None, Field(gt=0, le=20)] = None,
) -> PlaceSearchResult:
    """Search reviewed CityBuddy places with bounded city/category/location filters."""

    request = PlaceSearchInput(
        city=city,
        categories=categories or [],
        limit=limit,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
    )
    with SessionLocal() as database:
        return search_places(database, request)


@mcp.tool()
def get_place_details(
    place_id: Annotated[int, Field(gt=0)],
) -> PlaceRead:
    """Get reviewed details for one CityBuddy place ID returned by CityBuddy."""

    with SessionLocal() as database:
        return get_place(database, place_id=place_id)


@mcp.tool()
def get_official_place_page(
    place_id: Annotated[int, Field(gt=0)],
    page_type: OfficialPageType = "general",
) -> OfficialSiteEvidence:
    """Fetch bounded live text from a reviewed place's stored official website only."""

    with SessionLocal() as database:
        return retrieve_official_place_page(
            database,
            place_id=place_id,
            page_type=page_type,
        )


def main() -> None:
    """Run the local MCP server over stdio."""

    mcp.run()


if __name__ == "__main__":
    main()
