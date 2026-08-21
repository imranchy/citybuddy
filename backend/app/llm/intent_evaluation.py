from dataclasses import asdict, dataclass
import json
from math import ceil
from pathlib import Path
from statistics import mean, median
from typing import Any

from app.core.languages import SUPPORTED_LANGUAGE_CODES
from app.llm.base import StructuredLLMProvider
from app.llm.prompts import SEMANTIC_PLANNER_SYSTEM_PROMPT
from app.llm.schemas import DiscoveryIntent, SemanticPlan
from app.llm.tracing import TraceConfig, finish_trace, trace_evaluation_case
from app.schemas.assistant import AssistantChatRequest


EVALUATION_ROOT = Path(__file__).resolve().parents[2] / "evaluation"
DEFAULT_PLANNER_DATASET = EVALUATION_ROOT / "datasets" / "v1" / "planner_intent_v1.jsonl"


@dataclass(frozen=True, slots=True)
class PlannerIntentCase:
    case_id: str
    query: str
    language: str
    categories: tuple[str, ...]
    limit: int
    category_limits: dict[str, int]
    goal: str
    tool_intent: str
    nearby: bool
    radius_km: float | None
    target_place_name: str | None
    unsupported_constraints: tuple[str, ...]
    difficulty: str
    tags: tuple[str, ...]
    scorable: bool
    skip_reason: str | None = None

    @property
    def key(self) -> str:
        return self.case_id

    @property
    def ui_language(self) -> str:
        return self.language if self.language in SUPPORTED_LANGUAGE_CODES else "en"

    @property
    def expected_response_language(self) -> str:
        return self.ui_language

    @property
    def expected_goal(self) -> str:
        return {"directions": "answer", "inform": "answer"}.get(self.goal, self.goal)

    @property
    def expected_tool_intent(self) -> str:
        return "discovery" if self.tool_intent == "transport" else self.tool_intent

    @property
    def expected_wants_transport(self) -> bool:
        return self.tool_intent == "transport"


def _bool(value: object) -> bool:
    return str(value).strip().casefold() == "true"


def _split_pipe(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("|") if item)


def _compatibility(row: dict[str, Any]) -> tuple[bool, str | None]:
    goal = str(row.get("expected_goal", "recommend"))
    tool_intent = str(row.get("expected_tool_intent", "discovery"))
    constraints = _split_pipe(str(row.get("expected_unsupported_constraints", "")))

    if goal not in {"recommend", "describe", "compare", "itinerary", "answer", "directions", "inform"}:
        return False, f"planner schema does not support goal={goal!r}"
    if tool_intent not in {
        "discovery",
        "transport",
        "weather",
        "official_opening",
        "official_menu",
        "official_exhibitions",
        "official_prices",
        "official_info",
    }:
        return False, f"planner schema does not support tool_intent={tool_intent!r}"
    unsupported_by_normalizer = {
        value
        for value in constraints
        if value not in {"live_transport", "unsupported_city"}
    }
    if unsupported_by_normalizer:
        return False, (
            "normalizer does not expose dataset constraint(s): "
            + ", ".join(sorted(unsupported_by_normalizer))
        )
    if not _bool(row.get("expected_valid_plan", "true")):
        return False, "negative/invalid-plan cases require a dedicated rejection evaluator"
    return True, None


def load_planner_cases(dataset_path: Path = DEFAULT_PLANNER_DATASET) -> tuple[PlannerIntentCase, ...]:
    cases: list[PlannerIntentCase] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(dataset_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        case_id = str(row["case_id"])
        if case_id in seen_ids:
            raise ValueError(f"Duplicate planner evaluation case_id: {case_id}")
        seen_ids.add(case_id)
        scorable, skip_reason = _compatibility(row)
        categories = _split_pipe(str(row.get("expected_categories", "")))
        category_limits = json.loads(str(row.get("expected_category_limits", "{}")) or "{}")
        radius_raw = row.get("expected_radius_km", "")
        radius_km = None if radius_raw in (None, "") else float(radius_raw)
        cases.append(
            PlannerIntentCase(
                case_id=case_id,
                query=str(row["prompt"]),
                language=str(row.get("language", "en")),
                categories=categories,
                limit=int(row.get("expected_limit", 5)),
                category_limits={str(key): int(value) for key, value in category_limits.items()},
                goal=str(row.get("expected_goal", "recommend")),
                tool_intent=str(row.get("expected_tool_intent", "discovery")),
                nearby=_bool(row.get("expected_nearby", "false")),
                radius_km=radius_km,
                target_place_name=(str(row.get("expected_target_place_name", "")).strip() or None),
                unsupported_constraints=_split_pipe(str(row.get("expected_unsupported_constraints", ""))),
                difficulty=str(row.get("difficulty", "unknown")),
                tags=_split_pipe(str(row.get("tags", ""))),
                scorable=scorable,
                skip_reason=skip_reason,
            )
        )
    if not cases:
        raise ValueError(f"Planner evaluation dataset is empty: {dataset_path}")
    return tuple(cases)


PLANNER_INTENT_CASES = load_planner_cases()

# Keep a fast, deterministic smoke subset spanning known regression risks.
SMOKE_CASE_IDS = {
    "INT-0001",  # attraction
    "INT-0016",  # fast food
    "INT-0046",  # mosque
    "INT-0049",  # museum
    "INT-0058",  # park
    "INT-0076",  # supermarket
    "INT-0082",  # theatre
    "INT-0085",  # viewpoint
    "INT-0088",  # Italian museum
    "INT-0089",  # Italian mosque
    "INT-0095",  # Bangla museum
    "INT-0096",  # Bangla mosque
    "INT-0099",  # multi-category quantity
    "INT-0105",  # nearby/radius
    "INT-0108",  # transport
    "INT-0109",  # weather
}


def intent_cases_for_suite(
    suite: str = "production",
    *,
    dataset_path: Path = DEFAULT_PLANNER_DATASET,
) -> tuple[PlannerIntentCase, ...]:
    cases = PLANNER_INTENT_CASES if dataset_path == DEFAULT_PLANNER_DATASET else load_planner_cases(dataset_path)
    if suite == "all":
        return cases
    if suite == "production":
        return tuple(case for case in cases if case.scorable)
    if suite == "smoke":
        selected = tuple(case for case in cases if case.case_id in SMOKE_CASE_IDS and case.scorable)
        missing = SMOKE_CASE_IDS - {case.case_id for case in selected}
        if missing:
            raise RuntimeError(
                "Planner smoke suite references missing or unscorable cases: "
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


def _plan_checks(case: PlannerIntentCase, intent: DiscoveryIntent) -> dict[str, bool]:
    checks = {
        "categories": set(intent.categories) == set(case.categories),
        "response_language": intent.language == case.expected_response_language,
        "request_language": intent.request_language.casefold().startswith(case.language.casefold()),
        "limit": intent.limit == case.limit,
        "category_limits": intent.category_limits == case.category_limits,
        "nearby": intent.nearby == case.nearby,
        "radius_km": intent.radius_km == case.radius_km,
        "goal": intent.goal == case.expected_goal,
        "tool_intent": intent.tool_intent == case.expected_tool_intent,
        "wants_transport": intent.wants_transport == case.expected_wants_transport,
        "target_place_name": intent.target_place_name == case.target_place_name,
    }
    if case.unsupported_constraints:
        checks["unsupported_constraints"] = set(intent.unsupported_constraints) == set(
            case.unsupported_constraints
        )
    return checks


def _error_kind(error: Exception) -> str:
    message = str(error).casefold()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if (
        "validation error" in message
        or "valid structured output" in message
        or "unsupported citybuddy category" in message
    ):
        return "schema_or_output"
    return "provider"


def evaluate_intent_model(
    provider: StructuredLLMProvider,
    *,
    model: str,
    trace_config: TraceConfig | None = None,
    suite: str = "production",
    dataset_path: Path = DEFAULT_PLANNER_DATASET,
) -> dict[str, Any]:
    """Evaluate the production planner against the frozen v1 intent dataset."""

    tracing = trace_config or TraceConfig()
    all_cases = intent_cases_for_suite("all", dataset_path=dataset_path)
    cases = intent_cases_for_suite(suite, dataset_path=dataset_path)
    skipped_cases = [case for case in all_cases if not case.scorable] if suite == "all" else []
    case_results: list[dict[str, Any]] = []
    durations: list[float] = []
    load_durations: list[float] = []

    for case in cases:
        if not case.scorable:
            case_results.append(
                {
                    "key": case.key,
                    "passed": None,
                    "skipped": True,
                    "skip_reason": case.skip_reason,
                }
            )
            continue
        trace = None
        try:
            with trace_evaluation_case(
                tracing,
                name=f"CityBuddy intent routing evaluation: {case.key}",
                inputs={"prompt": case.query, "expected": asdict(case)},
                metadata={
                    "model": model,
                    "case_kind": "intent",
                    "case_key": case.key,
                    "suite": suite,
                    "dataset": str(dataset_path),
                },
            ) as trace:
                call = provider.generate_structured(
                    model=model,
                    system_prompt=SEMANTIC_PLANNER_SYSTEM_PROMPT,
                    user_prompt=json.dumps(
                        {
                            "conversation_history": [],
                            "current_user_message": case.query,
                            "ui_language": case.ui_language,
                            "supported_response_languages": list(SUPPORTED_LANGUAGE_CODES),
                        },
                        ensure_ascii=False,
                    ),
                    output_schema=SemanticPlan,
                )
                plan_payload = call.output.model_dump() if hasattr(call.output, "model_dump") else call.output
                plan = SemanticPlan.model_validate(plan_payload)
                if len(plan.tasks) != 1:
                    raise ValueError("Intent evaluation cases require one planner task")
                from app.services.assistant import _planned_task_intent

                request = AssistantChatRequest(message=case.query, language=case.ui_language)
                normalized_output = _planned_task_intent(request, plan, plan.tasks[0])
                checks = _plan_checks(case, normalized_output)

                result = {
                    "key": case.key,
                    "passed": all(checks.values()),
                    "skipped": False,
                    "response_received": True,
                    "schema_valid": True,
                    "checks": checks,
                    "plan": plan.model_dump(),
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
                "skipped": False,
                "response_received": False,
                "schema_valid": False if error_kind == "schema_or_output" else None,
                "error_kind": error_kind,
                "error": str(error),
            }
            case_results.append(result)

    scored_results = [result for result in case_results if not result.get("skipped")]
    passed_cases = sum(result["passed"] is True for result in scored_results)
    field_checks = [
        passed
        for result in scored_results
        for passed in result.get("checks", {}).values()
    ]
    warm_durations = durations[1:]
    error_counts = {
        kind: sum(result.get("error_kind") == kind for result in scored_results)
        for kind in ("timeout", "schema_or_output", "provider")
    }
    schema_results = [
        result["schema_valid"]
        for result in scored_results
        if result.get("schema_valid") is not None
    ]

    return {
        "model": model,
        "suite": suite,
        "dataset": str(dataset_path),
        "dataset_cases": len(all_cases),
        "scored_cases": len(scored_results),
        "skipped_cases": len(case_results) - len(scored_results),
        "dataset_unscorable_cases": len([case for case in all_cases if not case.scorable]),
        "passed_cases": passed_cases,
        "total_cases": len(scored_results),
        "metrics": {
            "strict_case_accuracy_percent": _percent(passed_cases, len(scored_results)),
            "field_accuracy_percent": _percent(sum(field_checks), len(field_checks)),
            "response_success_percent": _percent(
                sum(result.get("response_received") is True for result in scored_results),
                len(scored_results),
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
        "unscorable": [
            {"key": case.key, "reason": case.skip_reason}
            for case in (skipped_cases or [case for case in all_cases if not case.scorable])
        ],
    }
