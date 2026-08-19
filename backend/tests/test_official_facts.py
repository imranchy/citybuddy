import unittest
from types import SimpleNamespace

from app.llm.base import LLMCallResult
from app.llm.ingestion_schemas import OfficialFactExtractionOutput
from app.services.official_facts import (
    _claim_is_supported,
    _excerpt_is_grounded,
    extract_fact_candidates_from_evidence,
)


class _Provider:
    def __init__(self, payload):
        self.output = OfficialFactExtractionOutput.model_validate(payload)
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return LLMCallResult(
            output=self.output,
            model="qwen3:8b",
            total_duration_ms=0,
            load_duration_ms=0,
            prompt_tokens=0,
            output_tokens=0,
            raw_content="{}",
        )


class OfficialFactTests(unittest.TestCase):
    def test_target_place_validation_accepts_existing_and_rejects_unknown_id(self) -> None:
        from scripts.index_official_facts import require_reviewed_place

        class _ScopeDatabase:
            def __init__(self, value):
                self.value = value

            def scalar(self, statement):
                return self.value

        require_reviewed_place(_ScopeDatabase(3386), place_id=3386, city="Torino")
        with self.assertRaises(SystemExit):
            require_reviewed_place(_ScopeDatabase(None), place_id=999999, city="Torino")

    def test_excerpt_grounding_normalizes_whitespace_only(self) -> None:
        evidence = "Wheelchair access\nis available at the main entrance."
        self.assertTrue(_excerpt_is_grounded("Wheelchair access is available", evidence))
        self.assertFalse(_excerpt_is_grounded("Wheelchair access is guaranteed everywhere", evidence))

    def test_positive_accessibility_claim_is_promotable(self) -> None:
        provider = _Provider({"claims": [{
            "fact_type": "wheelchair_accessible",
            "value": "yes",
            "evidence_excerpt": "Wheelchair access is available at the main entrance.",
        }]})
        candidates, completed = extract_fact_candidates_from_evidence(
            place_id=5,
            place_name="Armeria Reale",
            content_type="accessibility",
            source_url="https://official.example/accessibility",
            source_fetched_at=None,
            evidence_text="Wheelchair access is available at the main entrance.",
            provider=provider,
            model="qwen3:8b",
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].fact_type, "wheelchair_accessible")
        self.assertIn("accessible_toilet", completed)

    def test_model_cannot_promote_fact_outside_evidence_type(self) -> None:
        provider = _Provider({"claims": [{
            "fact_type": "vegetarian_options",
            "value": "yes",
            "evidence_excerpt": "Wheelchair access is available.",
        }]})
        candidates, _ = extract_fact_candidates_from_evidence(
            place_id=1,
            place_name="Museum",
            content_type="accessibility",
            source_url="https://official.example",
            source_fetched_at=None,
            evidence_text="Wheelchair access is available.",
            provider=provider,
            model="qwen3:8b",
        )
        self.assertEqual(candidates, [])

    def test_model_cannot_invent_positive_fact_from_unrelated_excerpt(self) -> None:
        provider = _Provider({"claims": [{
            "fact_type": "parking_available",
            "value": "yes",
            "evidence_excerpt": "Families can visit every weekend.",
        }]})
        candidates, _ = extract_fact_candidates_from_evidence(
            place_id=2,
            place_name="Place",
            content_type="visitor_services",
            source_url="https://official.example",
            source_fetched_at=None,
            evidence_text="Families can visit every weekend.",
            provider=provider,
            model="qwen3:8b",
        )
        self.assertEqual(candidates, [])

    def test_halal_status_requires_explicit_support(self) -> None:
        self.assertTrue(_claim_is_supported("halal_status", "verified_halal", "Our kitchen is halal certified."))
        self.assertTrue(_claim_is_supported("halal_status", "explicitly_not_halal", "We are not halal certified."))
        self.assertFalse(_claim_is_supported("halal_status", "verified_halal", "Middle Eastern cuisine."))

    def test_unknown_facts_are_omitted_instead_of_stored(self) -> None:
        provider = _Provider({"claims": []})
        candidates, completed = extract_fact_candidates_from_evidence(
            place_id=7,
            place_name="Restaurant",
            content_type="dietary_policy",
            source_url="https://restaurant.example/menu",
            source_fetched_at=None,
            evidence_text="Our menu changes seasonally.",
            provider=provider,
            model="qwen3:8b",
        )
        self.assertEqual(candidates, [])
        self.assertEqual(completed, {"vegetarian_options", "vegan_options", "halal_status"})


if __name__ == "__main__":
    unittest.main()
