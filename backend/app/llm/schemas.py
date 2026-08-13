from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.place_catalog import DESTINATION_CATEGORIES


class DiscoveryIntent(BaseModel):
    """Model-interpreted request constrained to CityBuddy capabilities."""

    model_config = ConfigDict(extra="forbid")

    city: str = "turin"
    categories: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=5, ge=1, le=10)
    nearby: bool = False
    radius_km: float | None = Field(default=None, ge=0.1, le=20.0)
    wants_transport: bool = False
    language: Literal["en", "it"] = "en"
    unsupported_constraints: list[
        Literal[
            "live_opening_status",
            "live_availability",
            "live_transport",
            "unverified_price",
            "unverified_rating",
            "unsupported_city",
            "other",
        ]
    ] = Field(default_factory=list)

    @field_validator("city")
    @classmethod
    def normalize_city(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "torino":
            return "turin"
        return normalized

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            category = value.strip().lower().replace(" ", "_")
            if category not in DESTINATION_CATEGORIES:
                raise ValueError(f"Unsupported CityBuddy category: {value}")
            if category not in normalized:
                normalized.append(category)
        return normalized

    @model_validator(mode="after")
    def validate_nearby_fields(self) -> "DiscoveryIntent":
        if self.radius_km is not None and not self.nearby:
            raise ValueError("radius_km requires nearby=true")
        return self


class GroundedRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: int
    reason: str = Field(min_length=1, max_length=240)
    evidence_ids: list[int] = Field(default_factory=list, max_length=5)


class GroundedClaim(BaseModel):
    """A machine-checkable fact copied from one retrieved record."""

    model_config = ConfigDict(extra="forbid")

    place_id: int
    field: Literal[
        "name",
        "category",
        "description",
        "address",
        "opening_hours",
        "website",
        "operator",
        "rating",
        "price_level",
    ]
    value: str | int | float | None


class GroundedResponse(BaseModel):
    """Small evaluation response whose place references can be validated."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[GroundedRecommendation] = Field(max_length=10)
    claims: list[GroundedClaim] = Field(max_length=30)
    abstained: bool
    summary: str = Field(min_length=1, max_length=500)
