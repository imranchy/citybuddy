from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.languages import LanguageCode
from app.core.place_catalog import DESTINATION_CATEGORIES


class PlannerCategoryRequest(BaseModel):
    """Language-independent category request proposed by the semantic planner."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=80)
    quantity: int | None = Field(default=None, ge=1, le=10)

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class PlannerTask(BaseModel):
    """One bounded task in a Qwen-generated CityBuddy plan."""

    model_config = ConfigDict(extra="forbid")

    task_type: Literal[
        "discovery",
        "weather",
        "official_opening",
        "official_menu",
        "official_exhibitions",
        "official_prices",
        "official_info",
    ] = "discovery"
    goal: Literal["recommend", "describe", "compare", "itinerary", "answer"] = "recommend"
    query: str = Field(min_length=1, max_length=500)
    categories: list[PlannerCategoryRequest] = Field(default_factory=list, max_length=8)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    target_place_name: str | None = Field(default=None, max_length=160)
    refers_to_context: bool = False
    reference_position: int | None = Field(default=None, ge=1, le=10)
    nearby: bool = False
    radius_km: float | None = Field(default=None, ge=0.1, le=20.0)
    wants_transport: bool = False
    forecast_hours: int = Field(default=12, ge=1, le=48)

    @field_validator("preferences")
    @classmethod
    def normalize_preferences(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            preference = " ".join(value.strip().split())
            if preference and preference not in normalized:
                normalized.append(preference)
        return normalized


class SemanticPlan(BaseModel):
    """Qwen's multilingual, bounded plan before application validation."""

    model_config = ConfigDict(extra="forbid")

    request_language: str = Field(default="en", min_length=2, max_length=24)
    response_language: LanguageCode
    city: str = Field(default="turin", min_length=1, max_length=80)
    is_continuation: bool = False
    mode: Literal["single", "compound", "comparison", "itinerary"] = "single"
    tasks: list[PlannerTask] = Field(min_length=1, max_length=12)

    @field_validator("city")
    @classmethod
    def normalize_plan_city(cls, value: str) -> str:
        normalized = value.strip().lower()
        return "turin" if normalized == "torino" else normalized


class PlanSynthesisResponse(BaseModel):
    """Gemma synthesis across already-grounded task results."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4_000)


class DiscoveryIntent(BaseModel):
    """Strict, application-normalized request safe to use for retrieval."""

    model_config = ConfigDict(extra="forbid")

    city: str = "turin"
    categories: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=5, ge=1, le=10)
    nearby: bool = False
    radius_km: float | None = Field(default=None, ge=0.1, le=20.0)
    wants_transport: bool = False
    language: LanguageCode = "en"
    request_language: str = Field(default="en", min_length=2, max_length=24)
    category_limits: dict[str, int] = Field(default_factory=dict)
    preferences: list[str] = Field(default_factory=list, max_length=12)
    goal: Literal["recommend", "describe", "compare", "itinerary", "answer"] = "recommend"
    tool_intent: Literal[
        "discovery",
        "weather",
        "official_opening",
        "official_menu",
        "official_exhibitions",
        "official_prices",
        "official_info",
    ] = "discovery"
    target_place_name: str | None = Field(default=None, max_length=160)
    forecast_hours: int = Field(default=12, ge=1, le=48)
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
        return "turin" if normalized == "torino" else normalized

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

    @field_validator("category_limits")
    @classmethod
    def validate_category_limits(cls, values: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for key, value in values.items():
            category = key.strip().lower().replace(" ", "_")
            if category not in DESTINATION_CATEGORIES:
                raise ValueError(f"Unsupported CityBuddy category limit: {key}")
            if not 1 <= value <= 10:
                raise ValueError("Category quantities must be between 1 and 10")
            normalized[category] = value
        return normalized

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            preference = " ".join(value.strip().split())
            if preference and preference not in normalized:
                normalized.append(preference)
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
    """Grounded response whose entities and claims can be validated exactly."""

    model_config = ConfigDict(extra="forbid")

    recommendations: list[GroundedRecommendation] = Field(max_length=10)
    claims: list[GroundedClaim] = Field(max_length=30)
    abstained: bool
    summary: str = Field(min_length=1, max_length=500)


class ToolGroundedClaim(BaseModel):
    """Machine-checkable support copied from bounded live-tool evidence."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=80)
    value: str | int | float | bool | None


class ToolGroundedResponse(BaseModel):
    """Grounded answer for weather or official-site tool evidence."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=1_000)
    claims: list[ToolGroundedClaim] = Field(default_factory=list, max_length=20)
    abstained: bool
