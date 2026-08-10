from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel


SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    """Validated model output and provider-reported performance metrics."""

    output: BaseModel
    model: str
    total_duration_ms: float
    load_duration_ms: float
    prompt_tokens: int
    output_tokens: int
    raw_content: str


class StructuredLLMProvider(Protocol):
    """Minimal provider contract used by CityBuddy application services."""

    def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[SchemaT],
    ) -> LLMCallResult:
        """Generate and validate one response against a Pydantic schema."""


def milliseconds(nanoseconds: Any) -> float:
    if not isinstance(nanoseconds, (int, float)):
        return 0.0
    return round(float(nanoseconds) / 1_000_000, 3)
