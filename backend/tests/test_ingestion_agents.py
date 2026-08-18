import unittest

try:
    import langgraph  # noqa: F401
except ImportError:
    langgraph = None

from app.llm.base import LLMCallResult
from app.llm.ingestion_schemas import IngestionReviewOutput

if langgraph is not None:
    from app.services.ingestion_agents import build_review_graph, review_candidate


class FakeProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.models = []

    def generate_structured(self, *, model, system_prompt, user_prompt, output_schema):
        self.models.append(model)
        output = self.outputs.pop(0)
        self.assert_schema(output_schema, output)
        return LLMCallResult(
            output=output,
            model=model,
            total_duration_ms=1.0,
            load_duration_ms=0.0,
            prompt_tokens=10,
            output_tokens=5,
            raw_content=output.model_dump_json(),
        )

    @staticmethod
    def assert_schema(output_schema, output):
        if not isinstance(output, output_schema):
            raise AssertionError("Fake output does not match requested schema")


@unittest.skipIf(langgraph is None, "langgraph dependency is not installed in this environment")
class IngestionAgentTests(unittest.TestCase):
    def test_valid_candidate_skips_models(self):
        provider = FakeProvider([])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=1,
            validation_status="valid",
            candidate={"name": "Museum"},
        )

        self.assertEqual(result.verdict, "approve")
        self.assertEqual(result.reviewer_model, "deterministic")
        self.assertEqual(provider.models, [])

    def test_invalid_candidate_skips_models_and_rejects(self):
        provider = FakeProvider([])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="image",
            candidate_id=2,
            validation_status="invalid",
            candidate={"source": "unknown"},
        )

        self.assertEqual(result.verdict, "reject")
        self.assertEqual(provider.models, [])

    def test_review_required_uses_qwen_without_unneeded_escalation(self):
        provider = FakeProvider([
            IngestionReviewOutput(
                verdict="approve",
                confidence=0.9,
                reason="Metadata is consistent.",
                concerns=[],
            )
        ])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=3,
            validation_status="review_required",
            candidate={"name": "Museum", "address": "Address unavailable"},
        )

        self.assertEqual(result.verdict, "approve")
        self.assertFalse(result.escalated)
        self.assertEqual(provider.models, ["qwen"])

    def test_qwen_can_escalate_once_to_gemma(self):
        provider = FakeProvider([
            IngestionReviewOutput(
                verdict="escalate",
                confidence=0.5,
                reason="Identity is ambiguous.",
                concerns=["identity"],
            ),
            IngestionReviewOutput(
                verdict="reject",
                confidence=0.8,
                reason="The metadata is not strong enough to approve.",
                concerns=["identity"],
            ),
        ])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="image",
            candidate_id=4,
            validation_status="review_required",
            candidate={"source_image_id": "File:Ambiguous.jpg"},
        )

        self.assertEqual(result.verdict, "reject")
        self.assertTrue(result.escalated)
        self.assertEqual(provider.models, ["qwen", "gemma"])

    def test_second_escalation_terminates_conservatively(self):
        provider = FakeProvider([
            IngestionReviewOutput(
                verdict="escalate",
                confidence=0.4,
                reason="Needs stronger review.",
                concerns=[],
            ),
            IngestionReviewOutput(
                verdict="escalate",
                confidence=0.4,
                reason="Still ambiguous.",
                concerns=[],
            ),
        ])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=5,
            validation_status="review_required",
            candidate={"name": "Temporary Museum"},
        )

        self.assertEqual(result.verdict, "reject")
        self.assertIn("unresolved_after_escalation", result.concerns)
        self.assertEqual(provider.models, ["qwen", "gemma"])

    def test_missing_address_only_new_place_is_deterministically_approved(self):
        provider = FakeProvider([])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=6,
            validation_status="review_required",
            candidate={
                "staged_candidate_id": 6,
                "candidate_kind": "new",
                "validation_findings": ["missing_address_review_required"],
            },
        )

        self.assertEqual(result.verdict, "approve")
        self.assertEqual(result.reviewer_model, "deterministic_policy")
        self.assertEqual(provider.models, [])

    def test_safe_enrichment_is_deterministically_approved(self):
        provider = FakeProvider([])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=7,
            validation_status="review_required",
            candidate={
                "staged_candidate_id": 7,
                "candidate_kind": "enrichment",
                "validation_findings": [
                    "missing_address_review_required",
                    "existing_record_enrichment",
                ],
                "safe_enrichment_updates": {"website": "https://example.org"},
            },
        )

        self.assertEqual(result.verdict, "approve")
        self.assertEqual(result.reviewer_model, "deterministic_policy")
        self.assertEqual(provider.models, [])

    def test_duplicate_warning_still_requires_model_review(self):
        provider = FakeProvider([
            IngestionReviewOutput(
                verdict="reject",
                confidence=0.9,
                reason="Duplicate identity remains ambiguous.",
                concerns=["duplicate_identity"],
            )
        ])
        graph = build_review_graph(provider=provider, qwen_model="qwen", gemma_model="gemma")

        result = review_candidate(
            graph,
            candidate_type="place",
            candidate_id=8,
            validation_status="review_required",
            candidate={
                "staged_candidate_id": 8,
                "candidate_kind": "new",
                "validation_findings": [
                    "missing_address_review_required",
                    "possible_existing_duplicate",
                ],
            },
        )

        self.assertEqual(result.verdict, "reject")
        self.assertEqual(provider.models, ["qwen"])


if __name__ == "__main__":
    unittest.main()
