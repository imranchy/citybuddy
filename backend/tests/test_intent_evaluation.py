import json
import unittest

from app.core.languages import SUPPORTED_LANGUAGE_CODES
from app.llm.base import LLMCallResult
from app.llm.intent_evaluation import (
    PLANNER_INTENT_CASES,
    PlannerIntentCase,
    evaluate_intent_model,
    intent_cases_for_suite,
)
from app.llm.schemas import SemanticPlan


class PassingIntentProvider:
    def __init__(self, cases=None) -> None:
        self.cases = iter(cases or intent_cases_for_suite("production"))
        self.user_prompts = []

    def generate_structured(self, **kwargs) -> LLMCallResult:
        self.user_prompts.append(kwargs["user_prompt"])
        case: PlannerIntentCase = next(self.cases)
        task_type = case.expected_tool_intent
        categories = [
            {"category": category, "quantity": case.category_limits.get(category)}
            for category in case.categories
        ]
        output = SemanticPlan.model_validate(
            {
                "request_language": case.language,
                "response_language": case.expected_response_language,
                "city": "turin",
                "mode": "single",
                "tasks": [
                    {
                        "task_type": task_type,
                        "goal": case.expected_goal,
                        "query": case.query,
                        "categories": categories,
                        "preferences": [],
                        "target_place_name": case.target_place_name,
                        "nearby": case.nearby,
                        "radius_km": case.radius_km,
                        "wants_transport": case.expected_wants_transport,
                    }
                ],
            }
        )
        return LLMCallResult(
            output=output,
            model=kwargs["model"],
            total_duration_ms=10,
            load_duration_ms=1,
            prompt_tokens=5,
            output_tokens=5,
            raw_content=output.model_dump_json(),
        )


class FailingIntentProvider:
    def generate_structured(self, **kwargs) -> LLMCallResult:
        raise RuntimeError("provider unavailable")


class IntentEvaluationTests(unittest.TestCase):
    def test_v1_dataset_contains_115_cases(self) -> None:
        self.assertEqual(len(PLANNER_INTENT_CASES), 115)
        self.assertEqual(len({case.case_id for case in PLANNER_INTENT_CASES}), 115)

    def test_production_suite_excludes_contract_mismatches(self) -> None:
        production = intent_cases_for_suite("production")
        self.assertTrue(production)
        self.assertTrue(all(case.scorable for case in production))
        self.assertLess(len(production), len(PLANNER_INTENT_CASES))

    def test_smoke_suite_is_small_and_scorable(self) -> None:
        smoke = intent_cases_for_suite("smoke")
        self.assertGreaterEqual(len(smoke), 10)
        self.assertLess(len(smoke), len(intent_cases_for_suite("production")))
        self.assertTrue(all(case.scorable for case in smoke))

    def test_passing_provider_scores_every_production_case(self) -> None:
        production = intent_cases_for_suite("production")
        report = evaluate_intent_model(
            PassingIntentProvider(production), model="fake", suite="production"
        )
        self.assertEqual(report["passed_cases"], len(production))
        self.assertEqual(report["metrics"]["field_accuracy_percent"], 100.0)
        self.assertEqual(report["metrics"]["schema_validity_percent"], 100.0)
        self.assertEqual(report["errors"]["total"], 0)

    def test_evaluator_uses_production_language_envelope(self) -> None:
        smoke = intent_cases_for_suite("smoke")
        provider = PassingIntentProvider(smoke)
        evaluate_intent_model(provider, model="fake", suite="smoke")
        first = json.loads(provider.user_prompts[0])
        self.assertEqual(first["conversation_history"], [])
        self.assertEqual(first["supported_response_languages"], list(SUPPORTED_LANGUAGE_CODES))
        self.assertIn("current_user_message", first)

    def test_all_suite_records_unscorable_cases_as_skipped(self) -> None:
        scorable = [case for case in PLANNER_INTENT_CASES if case.scorable]
        provider = PassingIntentProvider(scorable)
        report = evaluate_intent_model(provider, model="fake", suite="all")
        self.assertEqual(report["dataset_cases"], 115)
        self.assertEqual(report["scored_cases"], len(scorable))
        self.assertEqual(report["skipped_cases"], 115 - len(scorable))

    def test_provider_failures_are_reported_without_crashing(self) -> None:
        production = intent_cases_for_suite("production")
        report = evaluate_intent_model(
            FailingIntentProvider(), model="fake", suite="production"
        )
        self.assertEqual(report["passed_cases"], 0)
        self.assertEqual(report["errors"]["provider"], len(production))
        self.assertEqual(report["metrics"]["response_success_percent"], 0.0)
        self.assertIsNone(report["metrics"]["schema_validity_percent"])


if __name__ == "__main__":
    unittest.main()
