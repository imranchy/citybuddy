import unittest

from app.llm.base import LLMCallResult
from app.llm.evaluation import IntentCase
from app.llm.intent_evaluation import (
    INTENT_EVALUATION_CASES,
    CategoryIntentCase,
    evaluate_intent_model,
    intent_cases_for_suite,
)
from app.llm.schemas import DiscoveryIntent


class PassingIntentProvider:
    def __init__(self) -> None:
        self.cases = iter(INTENT_EVALUATION_CASES)
        self.user_prompts = []

    def generate_structured(self, **kwargs) -> LLMCallResult:
        self.user_prompts.append(kwargs["user_prompt"])
        case = next(self.cases)
        if isinstance(case, CategoryIntentCase):
            output = DiscoveryIntent(
                categories=[case.category], language=case.language
            )
        else:
            assert isinstance(case, IntentCase)
            output = DiscoveryIntent(
                city=case.city,
                categories=list(case.categories),
                limit=case.limit,
                nearby=case.nearby,
                radius_km=case.radius_km,
                wants_transport=case.wants_transport,
                language=case.language,
                unsupported_constraints=list(case.unsupported_constraints),
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
    def test_suite_contains_13_capability_cases_and_68_taxonomy_cases(self) -> None:
        self.assertEqual(len(INTENT_EVALUATION_CASES), 81)
        self.assertEqual(
            sum(isinstance(case, IntentCase) for case in INTENT_EVALUATION_CASES),
            13,
        )
        self.assertEqual(
            sum(
                isinstance(case, CategoryIntentCase)
                for case in INTENT_EVALUATION_CASES
            ),
            68,
        )


    def test_smoke_suite_is_smaller_than_full_suite(self) -> None:
        smoke = intent_cases_for_suite("smoke")
        full = intent_cases_for_suite("full")

        self.assertEqual(len(smoke), 25)
        self.assertLess(len(smoke), len(full))

    def test_smoke_suite_keeps_safety_critical_cases(self) -> None:
        keys = {case.key for case in intent_cases_for_suite("smoke")}
        self.assertTrue(
            {
                "transport",
                "live_open",
                "unsupported_city",
                "unverified_rating",
            }.issubset(keys)
        )

    def test_passing_provider_scores_every_intent_case(self) -> None:
        report = evaluate_intent_model(PassingIntentProvider(), model="fake")

        self.assertEqual(report["passed_cases"], len(INTENT_EVALUATION_CASES))
        self.assertEqual(report["metrics"]["field_accuracy_percent"], 100.0)
        self.assertEqual(report["metrics"]["raw_semantic_accuracy_percent"], 100.0)
        self.assertEqual(report["metrics"]["schema_validity_percent"], 100.0)
        self.assertEqual(report["errors"]["total"], 0)


    def test_evaluator_uses_the_same_language_envelope_as_the_assistant(self) -> None:
        import json

        provider = PassingIntentProvider()
        evaluate_intent_model(provider, model="fake")

        first = json.loads(provider.user_prompts[0])
        italian = json.loads(provider.user_prompts[1])
        self.assertEqual(first["conversation_history"], [])
        self.assertEqual(first["required_response_language"], "en")
        self.assertEqual(italian["required_response_language"], "it")
        self.assertIn("current_user_message", first)

    def test_provider_failures_are_reported_without_crashing(self) -> None:
        report = evaluate_intent_model(FailingIntentProvider(), model="fake")

        self.assertEqual(report["passed_cases"], 0)
        self.assertEqual(
            report["errors"]["provider"], len(INTENT_EVALUATION_CASES)
        )
        self.assertEqual(report["metrics"]["response_success_percent"], 0.0)
        self.assertIsNone(report["metrics"]["schema_validity_percent"])


if __name__ == "__main__":
    unittest.main()
