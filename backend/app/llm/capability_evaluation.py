from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


EVALUATION_ROOT = Path(__file__).resolve().parents[2] / "evaluation"
DEFAULT_CAPABILITY_DATASET = EVALUATION_ROOT / "datasets" / "v1" / "capability_suite_v1.jsonl"


@dataclass(frozen=True, slots=True)
class CapabilityCase:
    case_id: str
    prompt: str
    capability: str
    expected_language: str
    expected_tool: str
    expected_categories: tuple[str, ...]
    requires_rag: bool
    requires_embedding_retrieval: bool
    requires_web_search: bool
    requires_weather_api: bool
    requires_transport_tool: bool
    expected_tool_call: bool
    expected_grounded: bool
    difficulty: str
    risk_level: str
    implementation_status: str


def _bool(value: object) -> bool:
    return str(value).strip().casefold() == "true"


def _split_pipe(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split("|") if item)


def load_capability_cases(
    dataset_path: Path = DEFAULT_CAPABILITY_DATASET,
) -> tuple[CapabilityCase, ...]:
    cases: list[CapabilityCase] = []
    seen_ids: set[str] = set()
    for raw_line in dataset_path.read_text(encoding="utf-8-sig").splitlines():
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        case_id = str(row["case_id"])
        if case_id in seen_ids:
            raise ValueError(f"Duplicate capability evaluation case_id: {case_id}")
        seen_ids.add(case_id)
        cases.append(
            CapabilityCase(
                case_id=case_id,
                prompt=str(row["prompt"]),
                capability=str(row["capability"]),
                expected_language=str(row.get("expected_language", "en")),
                expected_tool=str(row.get("expected_tool", "none")),
                expected_categories=_split_pipe(str(row.get("expected_categories", ""))),
                requires_rag=_bool(row.get("requires_rag", "false")),
                requires_embedding_retrieval=_bool(
                    row.get("requires_bge_embedding_retrieval", "false")
                ),
                requires_web_search=_bool(row.get("requires_web_search", "false")),
                requires_weather_api=_bool(row.get("requires_weather_api", "false")),
                requires_transport_tool=_bool(row.get("requires_transport_tool", "false")),
                expected_tool_call=_bool(row.get("expected_tool_call", "false")),
                expected_grounded=_bool(row.get("expected_grounded", "true")),
                difficulty=str(row.get("difficulty", "unknown")),
                risk_level=str(row.get("risk_level", "unknown")),
                implementation_status=str(row.get("implementation_status", "ready")),
            )
        )
    if not cases:
        raise ValueError(f"Capability evaluation dataset is empty: {dataset_path}")
    return tuple(cases)


def capability_dataset_report(
    dataset_path: Path = DEFAULT_CAPABILITY_DATASET,
) -> dict[str, Any]:
    """Validate and summarize the frozen capability suite before live-model execution.

    The later live runner will plug into this same loader. Keeping dataset validation
    independent prevents model/provider failures from being confused with malformed
    benchmark fixtures.
    """

    cases = load_capability_cases(dataset_path)
    capability_counts = Counter(case.capability for case in cases)
    tool_counts = Counter(case.expected_tool for case in cases)
    difficulty_counts = Counter(case.difficulty for case in cases)
    risk_counts = Counter(case.risk_level for case in cases)
    return {
        "dataset": str(dataset_path),
        "total_cases": len(cases),
        "capabilities": dict(sorted(capability_counts.items())),
        "expected_tools": dict(sorted(tool_counts.items())),
        "difficulty": dict(sorted(difficulty_counts.items())),
        "risk": dict(sorted(risk_counts.items())),
        "requirements": {
            "rag": sum(case.requires_rag for case in cases),
            "embedding_retrieval": sum(case.requires_embedding_retrieval for case in cases),
            "web_search": sum(case.requires_web_search for case in cases),
            "weather": sum(case.requires_weather_api for case in cases),
            "transport": sum(case.requires_transport_tool for case in cases),
            "tool_call_expected": sum(case.expected_tool_call for case in cases),
            "grounded_answer_expected": sum(case.expected_grounded for case in cases),
        },
        "cases": [asdict(case) for case in cases],
    }
