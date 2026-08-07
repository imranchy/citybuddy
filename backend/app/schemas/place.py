from pydantic import BaseModel, Field


class CategoryOptionRead(BaseModel):
    key: str
    label: str


class CategoryGroupRead(BaseModel):
    key: str
    label: str
    categories: list[CategoryOptionRead]


class PlaceImageRead(BaseModel):
    source: str
    image_url: str
    thumbnail_url: str | None
    source_page_url: str
    attribution: str
    license: str
    license_url: str | None

class PlaceRead(BaseModel):
    id: int
    name: str
    category: str
    description: str | None
    address: str
    city: str
    country_code: str
    latitude: float
    longitude: float
    price_level: int | None
    rating: float | None
    dietary_options: list[str] = Field(default_factory=list)
    opening_hours: str | None
    website: str | None
    operator: str | None
    primary_image: PlaceImageRead | None = None

class NearbyPlaceRead(PlaceRead):
    distance_km: float
