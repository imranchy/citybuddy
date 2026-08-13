from dataclasses import asdict, dataclass
import json
from math import ceil
from pathlib import Path
from statistics import mean, median
from typing import Any

from app.llm.base import StructuredLLMProvider
from app.llm.evaluation import INTENT_CASES, IntentCase
from app.llm.prompts import INTENT_SYSTEM_PROMPT
from app.llm.schemas import DiscoveryIntent, RawDiscoveryIntent
from app.llm.tracing import TraceConfig, finish_trace, trace_evaluation_case
from app.schemas.assistant import AssistantChatRequest
from app.services.assistant import normalize_discovery_intent


@dataclass(frozen=True, slots=True)
class CategoryIntentCase:
    key: str
    query: str
    category: str
    language: str


def _load_category_cases() -> tuple[CategoryIntentCase, ...]:
    dataset_path = (
        Path(__file__).resolve().parents[2]
        / "evaluation_datasets"
        / "rag-v2.json"
    )
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    return tuple(
        CategoryIntentCase(
            key=f"taxonomy_{item['key']}",
            query=item["query"],
            category=item["relevant_ids"][0],
            language="it" if item["key"].endswith("_it") else "en",
        )
        for item in dataset["cases"]
    )


CATEGORY_INTENT_CASES = _load_category_cases()
INTENT_EVALUATION_CASES = (*INTENT_CASES, *CATEGORY_INTENT_CASES)

SMOKE_CASE_KEYS = {
    "museum_count",
    "italian_food",
    "quiet_reading",
    "outdoors",
    "nightlife",
    "market",
    "worship",
    "accommodation",
    "culture",
    "transport",
    "live_open",
    "unsupported_city",
    "unverified_rating",
    "taxonomy_restaurant_en",
    "taxonomy_restaurant_it",
    "taxonomy_museum_en",
    "taxonomy_museum_it",
    "taxonomy_park_en",
    "taxonomy_park_it",
    "taxonomy_library_en",
    "taxonomy_library_it",
    "taxonomy_nightclub_en",
    "taxonomy_nightclub_it",
    "taxonomy_hotel_en",
    "taxonomy_hotel_it",
}


def intent_cases_for_suite(
    suite: str = "full",
) -> tuple[IntentCase | CategoryIntentCase, ...]:
    if suite == "full":
        return INTENT_EVALUATION_CASES
    if suite == "smoke":
        selected = tuple(
            case for case in INTENT_EVALUATION_CASES if case.key in SMOKE_CASE_KEYS
        )
        missing = SMOKE_CASE_KEYS - {case.key for case in selected}
        if missing:
            raise RuntimeError(
                "Intent smoke suite references missing cases: "
                + ", ".join(sorted(missing))
            )
        return selected
    raise ValueError(f"Unknown intent evaluation suite: {suite}")


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(0.95 * len(ordered)) - 1)]


def _raw_semantic_checks(
    case: IntentCase | CategoryIntentCase,
    intent: RawDiscoveryIntent,
) -> dict[str, bool]:
    expected_categories = (
        [case.category]
        if isinstance(case, CategoryIntentCase)
        else list(case.categories)
    )
    return {"categories": set(intent.categories) == set(expected_categories)}


def _normalized_checks(
    case: IntentCase | CategoryIntentCase,
    intent: DiscoveryIntent,
) -> dict[str, bool]:
    if isinstance(case, CategoryIntentCase):
        return {
            "categories": intent.categories == [case.category],
            "language": intent.language == case.language,
        }
    return {
        "categories": set(intent.categories) == set(case.categories),
        "language": intent.language == case.language,
        "city": intent.city == case.city,
        "limit": intent.limit == case.limit,
        "nearby": intent.nearby == case.nearby,
        "radius_km": intent.radius_km == case.radius_km,
        "wants_transport": intent.wants_transport == case.wants_transport,
        "unsupported_constraints": set(intent.unsupported_constraints)
        == set(case.unsupported_constraints),
    }


def _error_kind(error: Exception) -> str:
    message = str(error).casefold()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "validation error" in message or "valid structured output" in message:
        return "schema_or_output"
    return "provider"


def evaluate_intent_model(
    provider: StructuredLLMProvider,
    *,
    model: str,
    trace_config: TraceConfig | None = None,
    suite: str = "full",
) -> dict[str, Any]:
    """Evaluate intent extraction and the normalized production intent separately."""

    tracing = trace_config or TraceConfig()
    case_results: list[dict[str, Any]] = []
    durations: list[float] = []
    load_durations: list[float] = []

    for case in intent_cases_for_suite(suite):
        trace = None
        try:
            with trace_evaluation_case(
                tracing,
                name=f"CityBuddy intent routing evaluation: {case.key}",
                inputs={
                    "prompt": case.query,
                    "expected": (
                        asdict(case)
                        if isinstance(case, IntentCase)
                        else {"category": case.category, "language": case.language}
                    ),
                },
                metadata={
                    "model": model,
                    "case_kind": "intent",
                    "case_key": case.key,
                    "suite": suite,
                },
            ) as trace:
                call = provider.generate_structured(
                    model=model,
                    system_prompt=INTENT_SYSTEM_PROMPT,
                    user_prompt=json.dumps(
                        {
                            "conversation_history": [],
                            "current_user_message": case.query,
                            "required_response_language": case.language,
                        },
                        ensure_ascii=False,
                    ),
                    output_schema=RawDiscoveryIntent,
                )
                raw_payload = (
                    call.output.model_dump()
                    if hasattr(call.output, "model_dump")
                    else call.output
                )
                raw_output = RawDiscoveryIntent.model_validate(raw_payload)
                request = AssistantChatRequest(message=case.query, language=case.language)
                normalized_output = normalize_discovery_intent(request, raw_output)
                raw_checks = _raw_semantic_checks(case, raw_output)
                checks = _normalized_checks(case, normalized_output)

                result = {
                    "key": case.key,
                    "passed": all(checks.values()),
                    "response_received": True,
                    "schema_valid": True,
                    "raw_checks": raw_checks,
                    "checks": checks,
                    "raw_output": raw_output.model_dump(),
                    "output": normalized_output.model_dump(),
                    "duration_ms": call.total_duration_ms,
                    "load_duration_ms": call.load_duration_ms,
                    "prompt_tokens": call.prompt_tokens,
                    "output_tokens": call.output_tokens,
                }
                case_results.append(result)
                durations.append(call.total_duration_ms)
                load_durations.append(call.load_duration_ms)
                finish_trace(trace, outputs=result)
        except Exception as error:
            error_kind = _error_kind(error)
            result = {
                "key": case.key,
                "passed": False,
                "response_received": False,
                "schema_valid": False if error_kind == "schema_or_output" else None,
                "error_kind": error_kind,
                "error": str(error),
            }
            case_results.append(result)

    passed_cases = sum(result["passed"] for result in case_results)
    field_checks = [
        passed
        for result in case_results
        for passed in result.get("checks", {}).values()
    ]
    raw_semantic_checks = [
        passed
        for result in case_results
        for passed in result.get("raw_checks", {}).values()
    ]
    warm_durations = durations[1:]
    error_counts = {
        kind: sum(result.get("error_kind") == kind for result in case_results)
        for kind in ("timeout", "schema_or_output", "provider")
    }
    schema_results = [
        result["schema_valid"]
        for result in case_results
        if result.get("schema_valid") is not None
    ]

    return {
        "model": model,
        "suite": suite,
        "passed_cases": passed_cases,
        "total_cases": len(case_results),
        "metrics": {
            "strict_case_accuracy_percent": _percent(passed_cases, len(case_results)),
            "field_accuracy_percent": _percent(sum(field_checks), len(field_checks)),
            "raw_semantic_accuracy_percent": _percent(
                sum(raw_semantic_checks), len(raw_semantic_checks)
            ),
            "response_success_percent": _percent(
                sum(result["response_received"] for result in case_results),
                len(case_results),
            ),
            "schema_validity_percent": _percent(sum(schema_results), len(schema_results)),
        },
        "latency": {
            "cold_first_call_ms": durations[0] if durations else None,
            "cold_load_ms": load_durations[0] if load_durations else None,
            "warm_average_ms": round(mean(warm_durations), 1) if warm_durations else None,
            "warm_median_ms": round(median(warm_durations), 1) if warm_durations else None,
            "warm_p95_ms": _p95(warm_durations),
        },
        "errors": {**error_counts, "total": sum(error_counts.values())},
        "cases": case_results,
    }
