from pydantic import BaseModel, Field


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