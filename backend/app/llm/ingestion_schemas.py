from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestionReviewOutput(BaseModel):
    """Advisory model output for one already-staged ingestion candidate.

    The verdict is never a production write authorization. Application code
    persists it as review metadata and the existing promotion service remains
    the only path that can change production records.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["approve", "reject", "escalate"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)
    concerns: list[str] = Field(default_factory=list, max_length=8)
