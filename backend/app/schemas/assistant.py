from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm.schemas import DiscoveryIntent
from app.schemas.place import PlaceRead


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2_000)


class AssistantChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2_000)
    language: Literal["en", "it"] = "en"
    history: list[ConversationMessage] = Field(default_factory=list, max_length=10)
    context_place_ids: list[int] = Field(default_factory=list, max_length=10)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=20)

    @model_validator(mode="after")
    def validate_location(self) -> "AssistantChatRequest":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if self.radius_km is not None and self.latitude is None:
            raise ValueError("radius_km requires latitude and longitude")
        if any(place_id <= 0 for place_id in self.context_place_ids):
            raise ValueError("context_place_ids must contain positive IDs")
        self.context_place_ids = list(dict.fromkeys(self.context_place_ids))
        return self



class AssistantRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: PlaceRead
    reason: str = Field(min_length=1, max_length=240)
    distance_km: float | None = None
    transit_url: str | None = None


class AssistantChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    intent: DiscoveryIntent
    recommendations: list[AssistantRecommendation] = Field(max_length=10)
    grounded: bool
    provider_status: Literal["available", "fallback"]
    transport_disclaimer: str | None = None
    warnings: list[str] = Field(default_factory=list)
