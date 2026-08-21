import unittest

from app.llm.capability_evaluation import capability_dataset_report, load_capability_cases


class CapabilityEvaluationTests(unittest.TestCase):
    def test_v1_capability_dataset_has_46_unique_cases(self) -> None:
        cases = load_capability_cases()
        self.assertEqual(len(cases), 46)
        self.assertEqual(len({case.case_id for case in cases}), 46)

    def test_capability_dataset_covers_core_production_paths(self) -> None:
        report = capability_dataset_report()
        capabilities = report["capabilities"]
        for required in (
            "semantic_retrieval",
            "rag_grounded_answer",
            "weather_tool_calling",
            "transport_tool_calling",
            "tool_selection",
            "fail_closed_grounding",
            "multi_tool_chaining",
        ):
            self.assertIn(required, capabilities)
        self.assertGreater(report["requirements"]["embedding_retrieval"], 0)
        self.assertGreater(report["requirements"]["tool_call_expected"], 0)


if __name__ == "__main__":
    unittest.main()
