from dataclasses import asdict, dataclass
from math import ceil
from statistics import mean, median
from typing import Any

from app.llm.base import StructuredLLMProvider
from app.llm.prompts import GROUNDED_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from app.llm.schemas import DiscoveryIntent, GroundedClaim, GroundedResponse
from app.llm.tracing import TraceConfig, finish_trace, trace_evaluation_case


@dataclass(frozen=True, slots=True)
class IntentCase:
    key: str
    query: str
    categories: tuple[str, ...]
    language: str
    city: str = "turin"
    limit: int = 5
    nearby: bool = False
    radius_km: float | None = None
    wants_transport: bool = False
    unsupported_constraints: tuple[str, ...] = ()


INTENT_CASES = (
    IntentCase("museum_count", "Find three museums in Turin.", ("museum",), "en", limit=3),
    IntentCase("italian_food", "Vorrei trovare un ristorante a Torino.", ("restaurant",), "it"),
    IntentCase("quiet_reading", "I want a quiet public place to read and borrow books.", ("library",), "en"),
    IntentCase("outdoors", "Show me parks and gardens around me within 2 km.", ("park", "garden"), "en", nearby=True, radius_km=2.0),
    IntentCase("nightlife", "Cerco una discoteca a Torino.", ("nightclub",), "it"),
    IntentCase("market", "Find a local market in Torino.", ("market",), "en"),
    IntentCase("worship", "Cerco una moschea a Torino.", ("mosque",), "it"),
    IntentCase("accommodation", "Show hotels and hostels in Turin.", ("hotel", "hostel"), "en"),
    IntentCase("culture", "I would like museums or galleries nearby.", ("museum", "gallery"), "en", nearby=True),
    IntentCase("transport", "Find a museum and tell me how to reach it by public transport.", ("museum",), "en", wants_transport=True, unsupported_constraints=("live_transport",)),
    IntentCase("live_open", "Quali musei sono aperti proprio adesso?", ("museum",), "it", unsupported_constraints=("live_opening_status",)),
    IntentCase("unsupported_city", "Find a cafe in Lisbon.", ("cafe",), "en", city="lisbon", unsupported_constraints=("unsupported_city",)),
    IntentCase("unverified_rating", "Find a Michelin-starred restaurant in Turin.", ("restaurant",), "en", unsupported_constraints=("unverified_rating",)),
)


@dataclass(frozen=True, slots=True)
class GroundingCase:
    key: str
    request: str
    records: tuple[dict[str, Any], ...]
    forbidden_phrases: tuple[str, ...] = ()
    should_abstain: bool = False

    @property
    def prompt(self) -> str:
        import json

        return (
            f"Request: {self.request}\nRetrieved records:\n"
            f"{json.dumps(self.records, ensure_ascii=False)}"
        )

    @property
    def allowed_place_ids(self) -> tuple[int, ...]:
        return tuple(int(record["id"]) for record in self.records)


GROUNDING_CASES = (
    GroundingCase(
        "retrieved_only",
        "Recommend two museums for art and cinema.",
        (
            {"id": 101, "name": "Cinema Museum", "category": "museum", "description": "Exhibits about cinema.", "address": "Via A 1", "opening_hours": None, "rating": None, "price_level": None},
            {"id": 102, "name": "Art Museum", "category": "museum", "description": "A collection of modern art.", "address": "Via B 2", "opening_hours": None, "rating": None, "price_level": None},
        ),
        ("open now", "five stars", "5 stars", "free entry", "€"),
    ),
    GroundingCase(
        "transport_safety",
        "Recommend this museum. I also asked for public transport, but do not "
        "supply route or departure facts; application code adds the Google Maps "
        "transit link and safety disclaimer.",
        ({"id": 201, "name": "City Museum", "category": "museum", "description": "Local history exhibits.", "address": "Piazza C 3", "opening_hours": None, "rating": None, "price_level": None},),
        ("bus 4", "every 10 minutes", "departs at", "arrives at", "on time"),
    ),
    GroundingCase(
        "missing_live_facts",
        "Which retrieved place is open now and has the best rating?",
        ({"id": 301, "name": "Riverside Gallery", "category": "gallery", "description": "Contemporary exhibitions.", "address": "Via D 4", "opening_hours": None, "rating": None, "price_level": None},),
        (
            "riverside gallery is open",
            "riverside gallery has a rating",
            "riverside gallery is rated",
            "rating is 5",
        ),
        should_abstain=True,
    ),
    GroundingCase(
        "no_retrieved_records",
        "Recommend a quiet cafe.",
        (),
        should_abstain=True,
    ),
)


def _intent_checks(case: IntentCase, intent: DiscoveryIntent) -> dict[str, bool]:
    return {
        "categories": set(intent.categories) == set(case.categories),
        "language": intent.language == case.language,
        "city": intent.city == case.city,
        "limit": intent.limit == case.limit,
        "nearby": intent.nearby == case.nearby,
        "radius_km": intent.radius_km == case.radius_km,
        "wants_transport": intent.wants_transport == case.wants_transport,
        "unsupported_constraints": set(intent.unsupported_constraints) == set(case.unsupported_constraints),
    }


def _claim_status(case: GroundingCase, claim: GroundedClaim) -> str:
    record = next((item for item in case.records if item["id"] == claim.place_id), None)
    if record is None:
        return "unknown_entity"
    if claim.field not in record or record[claim.field] is None:
        return "unsupported_attribute"
    expected = record[claim.field]
    if isinstance(expected, (int, float)) and isinstance(claim.value, (int, float)):
        return "supported" if float(expected) == float(claim.value) else "contradiction"
    return "supported" if claim.value == expected else "contradiction"


def _grounding_checks(case: GroundingCase, response: GroundedResponse) -> tuple[dict[str, bool], dict[str, int]]:
    place_ids = [item.place_id for item in response.recommendations]
    combined_text = " ".join([response.summary, *(item.reason for item in response.recommendations)]).casefold()
    statuses = [_claim_status(case, claim) for claim in response.claims]
    supported_ids = {
        claim.place_id
        for claim, status in zip(response.claims, statuses, strict=True)
        if status == "supported"
    }
    counts = {status: statuses.count(status) for status in ("supported", "unknown_entity", "unsupported_attribute", "contradiction")}
    checks = {
        "retrieved_place_ids_only": set(place_ids).issubset(case.allowed_place_ids),
        "unique_place_ids": len(place_ids) == len(set(place_ids)),
        "no_forbidden_claims": not any(phrase.casefold() in combined_text for phrase in case.forbidden_phrases),
        "machine_checkable_claims_supported": bool(response.claims) and all(status == "supported" for status in statuses) if place_ids else not response.claims,
        "recommendations_have_evidence": set(place_ids).issubset(supported_ids),
        "correct_abstention": response.abstained == case.should_abstain,
        "recommendation_presence_matches_abstention": (
            not response.recommendations
            if case.should_abstain
            else bool(response.recommendations)
        ),
    }
    return checks, counts


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, ceil(0.95 * len(ordered)) - 1)]


def _error_kind(error: Exception) -> str:
    message = str(error).casefold()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if any(
        phrase in message
        for phrase in (
            "connection refused",
            "connection reset",
            "connecterror",
            "server error",
            "http status",
        )
    ):
        return "provider"
    if "validation error" in message or "did not return valid structured output" in message:
        return "schema_or_output"
    return "provider"


def evaluate_model(provider: StructuredLLMProvider, *, model: str, trace_config: TraceConfig | None = None) -> dict[str, Any]:
    tracing = trace_config or TraceConfig()
    case_results: list[dict[str, Any]] = []
    durations: list[float] = []
    load_durations: list[float] = []

    def run_case(*, kind: str, key: str, prompt: str, schema: type[DiscoveryIntent] | type[GroundedResponse], expected: Any) -> None:
        trace = None
        try:
            with trace_evaluation_case(
                tracing,
                name=f"CityBuddy {kind} evaluation: {key}",
                inputs={"prompt": prompt, "expected": asdict(expected)},
                metadata={"model": model, "case_kind": kind, "case_key": key},
            ) as trace:
                call = provider.generate_structured(model=model, system_prompt=INTENT_SYSTEM_PROMPT if kind == "intent" else GROUNDED_SYSTEM_PROMPT, user_prompt=prompt, output_schema=schema)
                output = schema.model_validate(call.output)
                if kind == "intent":
                    checks = _intent_checks(expected, output)
                    claim_counts = None
                else:
                    checks, claim_counts = _grounding_checks(expected, output)
                result = {
                    "kind": kind,
                    "key": key,
                    "passed": all(checks.values()),
                    "response_received": True,
                    "schema_valid": True,
                    "checks": checks,
                    "output": output.model_dump(),
                    "duration_ms": call.total_duration_ms,
                    "load_duration_ms": call.load_duration_ms,
                    "prompt_tokens": call.prompt_tokens,
                    "output_tokens": call.output_tokens,
                }
                if claim_counts is not None:
                    result["claim_counts"] = claim_counts
                durations.append(call.total_duration_ms)
                load_durations.append(call.load_duration_ms)
                case_results.append(result)
                finish_trace(trace, outputs=result)
        except Exception as error:
            error_kind = _error_kind(error)
            result = {
                "kind": kind,
                "key": key,
                "passed": False,
                "response_received": False,
                "schema_valid": False if error_kind == "schema_or_output" else None,
                "error_kind": error_kind,
                "error": str(error),
            }
            case_results.append(result)

    for case in INTENT_CASES:
        run_case(kind="intent", key=case.key, prompt=case.query, schema=DiscoveryIntent, expected=case)
    for case in GROUNDING_CASES:
        run_case(kind="grounding", key=case.key, prompt=case.prompt, schema=GroundedResponse, expected=case)

    passed = sum(result["passed"] for result in case_results)
    all_checks = [passed for result in case_results for passed in result.get("checks", {}).values()]
    intent_checks = [passed for result in case_results if result["kind"] == "intent" for passed in result.get("checks", {}).values()]
    grounding_checks = [passed for result in case_results if result["kind"] == "grounding" for passed in result.get("checks", {}).values()]
    claim_totals = {key: sum(result.get("claim_counts", {}).get(key, 0) for result in case_results) for key in ("supported", "unknown_entity", "unsupported_attribute", "contradiction")}
    total_claims = sum(claim_totals.values())
    grounding_results = [
        result for result in case_results if result["kind"] == "grounding"
    ]
    recommendation_total = sum(
        len(result.get("output", {}).get("recommendations", []))
        for result in grounding_results
    )
    recommendations_with_evidence = sum(
        1
        for result in grounding_results
        for recommendation in result.get("output", {}).get("recommendations", [])
        if any(
            claim["place_id"] == recommendation["place_id"]
            and _claim_status(
                next(case for case in GROUNDING_CASES if case.key == result["key"]),
                GroundedClaim.model_validate(claim),
            )
            == "supported"
            for claim in result.get("output", {}).get("claims", [])
        )
    )
    warm_durations = durations[1:]
    abstention_checks = [result["checks"]["correct_abstention"] for result in case_results if result["kind"] == "grounding" and "checks" in result]

    schema_results = [
        result["schema_valid"]
        for result in case_results
        if result.get("schema_valid") is not None
    ]
    error_counts = {
        kind: sum(result.get("error_kind") == kind for result in case_results)
        for kind in ("timeout", "schema_or_output", "provider")
    }

    return {
        "model": model,
        "passed_cases": passed,
        "total_cases": len(case_results),
        "score_percent": _percent(passed, len(case_results)),
        "metrics": {
            "strict_case_accuracy_percent": _percent(passed, len(case_results)),
            "response_success_percent": _percent(
                sum("error" not in result for result in case_results),
                len(case_results),
            ),
            "schema_validity_percent": _percent(
                sum(schema_results), len(schema_results)
            ),
            "field_accuracy_percent": _percent(sum(all_checks), len(all_checks)),
            "intent_field_accuracy_percent": _percent(sum(intent_checks), len(intent_checks)),
            "grounding_check_accuracy_percent": _percent(sum(grounding_checks), len(grounding_checks)),
            "supported_claim_rate_percent": _percent(claim_totals["supported"], total_claims),
            "entity_hallucination_rate_percent": _percent(claim_totals["unknown_entity"], total_claims),
            "attribute_hallucination_rate_percent": _percent(claim_totals["unsupported_attribute"], total_claims),
            "contradiction_rate_percent": _percent(claim_totals["contradiction"], total_claims),
            "abstention_accuracy_percent": _percent(sum(abstention_checks), len(abstention_checks)),
            "recommendation_evidence_coverage_percent": _percent(
                recommendations_with_evidence, recommendation_total
            ),
        },
        "latency": {
            "cold_first_call_ms": durations[0] if durations else None,
            "cold_load_ms": load_durations[0] if load_durations else None,
            "warm_average_ms": round(mean(warm_durations), 1) if warm_durations else None,
            "warm_median_ms": round(median(warm_durations), 1) if warm_durations else None,
            "warm_p95_ms": round(_p95(warm_durations), 1) if warm_durations else None,
        },
        "claim_totals": claim_totals,
        "claim_evidence": {
            "total_claims": total_claims,
            "supported_claims": claim_totals["supported"],
            "recommendations": recommendation_total,
            "recommendations_with_evidence": recommendations_with_evidence,
        },
        "errors": {
            "total": sum(error_counts.values()),
            **error_counts,
        },
        "cases": case_results,
        "evaluation_definition": {"intent_cases": [asdict(case) for case in INTENT_CASES], "grounding_cases": [asdict(case) for case in GROUNDING_CASES]},
    }
