import unittest

from app.llm.base import LLMCallResult
from app.llm.evaluation import (
    GROUNDING_CASES,
    INTENT_CASES,
    _grounding_checks,
    _error_kind,
    evaluate_model,
)
from app.llm.schemas import GroundedResponse, SemanticPlan


class PassingProvider:
    def __init__(self) -> None:
        self.call_index = 0

    def generate_structured(
        self,
        *,
        model,
        system_prompt,
        user_prompt,
        output_schema,
    ) -> LLMCallResult:
        if output_schema is SemanticPlan:
            case = INTENT_CASES[self.call_index]
            quantity = case.limit if len(case.categories) == 1 and case.limit != 5 else None
            output = SemanticPlan.model_validate(
                {
                    "request_language": case.language,
                    "response_language": case.language,
                    "city": case.city,
                    "mode": "single",
                    "tasks": [
                        {
                            "task_type": "official_opening" if case.key == "live_open" else "discovery",
                            "goal": "recommend",
                            "query": case.query,
                            "categories": [
                                {"category": category, "quantity": quantity}
                                for category in case.categories
                            ],
                            "preferences": [],
                            "nearby": case.nearby,
                            "radius_km": case.radius_km,
                            "wants_transport": case.wants_transport,
                        }
                    ],
                }
            )
        else:
            grounding_index = self.call_index - len(INTENT_CASES)
            case = GROUNDING_CASES[grounding_index]
            if case.should_abstain:
                recommendations = []
                claims = []
            else:
                record = case.records[0]
                recommendations = [
                    {
                        "place_id": record["id"],
                        "reason": "Matches a supplied category and description.",
                    }
                ]
                claims = [
                    {
                        "place_id": record["id"],
                        "field": "category",
                        "value": record["category"],
                    }
                ]
            output = GroundedResponse.model_validate(
                {
                    "recommendations": recommendations,
                    "claims": claims,
                    "abstained": case.should_abstain,
                    "summary": "Recommendation based only on retrieved records.",
                }
            )
        self.call_index += 1
        return LLMCallResult(
            output=output,
            model=model,
            total_duration_ms=100,
            load_duration_ms=0,
            prompt_tokens=10,
            output_tokens=10,
            raw_content=output.model_dump_json(),
        )


class EvaluationTests(unittest.TestCase):
    def test_passing_provider_receives_every_case(self) -> None:
        report = evaluate_model(PassingProvider(), model="fake-model")
        self.assertEqual(report["passed_cases"], report["total_cases"])
        self.assertEqual(
            report["total_cases"],
            len(INTENT_CASES) + len(GROUNDING_CASES),
        )
        self.assertEqual(report["score_percent"], 100.0)
        self.assertEqual(report["metrics"]["field_accuracy_percent"], 100.0)
        self.assertEqual(report["metrics"]["supported_claim_rate_percent"], 100.0)
        self.assertEqual(report["metrics"]["entity_hallucination_rate_percent"], 0.0)
        self.assertEqual(
            report["metrics"]["recommendation_evidence_coverage_percent"],
            100.0,
        )
        self.assertEqual(report["errors"]["total"], 0)
        self.assertEqual(report["latency"]["warm_p95_ms"], 100)

    def test_grounding_claim_failures_are_classified(self) -> None:
        case = GROUNDING_CASES[0]
        response = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 101, "reason": "A retrieved museum."}
                ],
                "claims": [
                    {"place_id": 999, "field": "name", "value": "Invented"},
                    {"place_id": 101, "field": "rating", "value": 5},
                    {"place_id": 101, "field": "name", "value": "Wrong name"},
                ],
                "abstained": False,
                "summary": "A recommendation.",
            }
        )

        checks, counts = _grounding_checks(case, response)

        self.assertFalse(checks["machine_checkable_claims_supported"])
        self.assertEqual(counts["unknown_entity"], 1)
        self.assertEqual(counts["unsupported_attribute"], 1)
        self.assertEqual(counts["contradiction"], 1)

    def test_timeout_is_not_classified_as_invalid_schema(self) -> None:
        self.assertEqual(_error_kind(TimeoutError("request timed out")), "timeout")

    def test_connection_failure_is_classified_as_provider_error(self) -> None:
        self.assertEqual(
            _error_kind(RuntimeError("connection refused")),
            "provider",
        )

    def test_safe_transport_refusal_is_not_a_forbidden_claim(self) -> None:
        case = next(case for case in GROUNDING_CASES if case.key == "transport_safety")
        response = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {
                        "place_id": 201,
                        "reason": "Local history exhibits; departure information is unavailable.",
                    }
                ],
                "claims": [
                    {"place_id": 201, "field": "category", "value": "museum"}
                ],
                "abstained": False,
                "summary": "Use the application-provided transit link for current information.",
            }
        )

        checks, _ = _grounding_checks(case, response)

        self.assertTrue(checks["no_forbidden_claims"])
        self.assertTrue(checks["recommendation_presence_matches_abstention"])


if __name__ == "__main__":
    unittest.main()
