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


class OfficialFactClaim(BaseModel):
    """One proposed durable fact grounded in a verbatim official-evidence excerpt."""

    model_config = ConfigDict(extra="forbid")

    fact_type: Literal[
        "wheelchair_accessible",
        "accessible_toilet",
        "parking_available",
        "family_facilities",
        "vegetarian_options",
        "vegan_options",
        "halal_status",
    ]
    value: Literal["yes", "verified_halal", "explicitly_not_halal"]
    evidence_excerpt: str = Field(min_length=3, max_length=700)


class OfficialFactExtractionOutput(BaseModel):
    """Bounded extractor output. Unknown/unsupported facts are omitted."""

    model_config = ConfigDict(extra="forbid")

    claims: list[OfficialFactClaim] = Field(default_factory=list, max_length=12)
