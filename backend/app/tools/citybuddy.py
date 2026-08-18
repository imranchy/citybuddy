from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.cities import get_city
from app.core.place_catalog import DESTINATION_CATEGORIES, canonicalize_category
from app.schemas.place import PlaceRead
from app.services.place_discovery import retrieve_place_by_id, retrieve_places


class PlaceToolResult(BaseModel):
    """A reviewed CityBuddy place returned through the controlled tool layer."""

    model_config = ConfigDict(extra="forbid")

    place: PlaceRead
    distance_km: float | None = None


class PlaceSearchResult(BaseModel):
    """Bounded, structured result from the CityBuddy place-search tool."""

    model_config = ConfigDict(extra="forbid")

    city: str
    categories: list[str]
    count: int
    places: list[PlaceToolResult]


class PlaceSearchInput(BaseModel):
    """Application validation boundary for place-search tool arguments."""

    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, max_length=100)
    categories: list[str] = Field(default_factory=list, max_length=8)
    limit: Annotated[int, Field(ge=1, le=10)] = 5
    latitude: Annotated[float | None, Field(ge=-90, le=90)] = None
    longitude: Annotated[float | None, Field(ge=-180, le=180)] = None
    radius_km: Annotated[float | None, Field(gt=0, le=20)] = None

    @model_validator(mode="after")
    def validate_location(self) -> "PlaceSearchInput":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.radius_km is not None and self.latitude is None:
            raise ValueError("radius_km requires latitude and longitude")
        return self


def normalize_tool_categories(categories: list[str]) -> list[str]:
    """Canonicalize requested categories without allowing arbitrary DB filters."""

    normalized: list[str] = []
    for value in categories:
        category = canonicalize_category(value)
        if category is None or category not in DESTINATION_CATEGORIES:
            raise ValueError(f"Unsupported CityBuddy category: {value!r}")
        if category not in normalized:
            normalized.append(category)
    return normalized


def search_places(database: Session, request: PlaceSearchInput) -> PlaceSearchResult:
    """Search reviewed places using only CityBuddy's controlled retrieval function."""

    city = get_city(request.city)
    categories = normalize_tool_categories(request.categories)
    retrieved = retrieve_places(
        database,
        city=city.key,
        categories=categories,
        limit=request.limit,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_km=request.radius_km,
    )

    places = [
        PlaceToolResult(place=item.place, distance_km=item.distance_km)
        for item in retrieved
    ]
    return PlaceSearchResult(
        city=city.display_name,
        categories=categories,
        count=len(places),
        places=places,
    )


def get_place(database: Session, *, place_id: int) -> PlaceRead:
    """Return one reviewed production place by internal CityBuddy place ID."""

    if place_id <= 0:
        raise ValueError("place_id must be a positive CityBuddy place ID")

    place = retrieve_place_by_id(database, place_id=place_id)
    if place is None:
        raise ValueError(f"No reviewed CityBuddy place exists with ID {place_id}.")
    return place
