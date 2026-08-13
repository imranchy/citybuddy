import unittest

from pydantic import ValidationError

from app.llm.schemas import DiscoveryIntent, GroundedResponse, RawDiscoveryIntent


class DiscoveryIntentSchemaTests(unittest.TestCase):
    def test_categories_and_torino_are_normalized(self) -> None:
        intent = DiscoveryIntent(
            city="Torino",
            categories=["Fast Food", "museum", "museum"],
            nearby=True,
            radius_km=2,
        )
        self.assertEqual(intent.city, "turin")
        self.assertEqual(intent.categories, ["fast_food", "museum"])

    def test_unknown_category_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Unsupported CityBuddy"):
            DiscoveryIntent(categories=["train_station"])

    def test_radius_requires_nearby_intent(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires nearby"):
            DiscoveryIntent(categories=["park"], radius_km=2)

    def test_extra_model_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DiscoveryIntent.model_validate(
                {"categories": ["museum"], "raw_sql": "SELECT * FROM places"}
            )


class RawDiscoveryIntentSchemaTests(unittest.TestCase):
    def test_raw_intent_allows_repairable_model_output(self) -> None:
        intent = RawDiscoveryIntent(
            categories=["parco"],
            nearby=False,
            radius_km=2,
            language="italiano",
            unsupported_constraints=["made_up_flag"],
        )
        self.assertEqual(intent.categories, ["parco"])
        self.assertEqual(intent.radius_km, 2)

    def test_raw_intent_accepts_semantic_routing_flags(self) -> None:
        intent = RawDiscoveryIntent(
            wants_transport=True,
            refers_to_context=True,
            needs_semantic_retrieval=True,
        )
        self.assertTrue(intent.wants_transport)
        self.assertTrue(intent.refers_to_context)
        self.assertTrue(intent.needs_semantic_retrieval)

    def test_raw_intent_still_rejects_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            RawDiscoveryIntent.model_validate(
                {"categories": ["museum"], "raw_sql": "SELECT * FROM places"}
            )


class GroundedResponseSchemaTests(unittest.TestCase):
    def test_grounded_response_has_bounded_recommendations(self) -> None:
        response = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 10, "reason": "Matches the museum request."}
                ],
                "claims": [
                    {"place_id": 10, "field": "category", "value": "museum"}
                ],
                "abstained": False,
                "summary": "One retrieved match.",
            }
        )
        self.assertEqual(response.recommendations[0].place_id, 10)
        self.assertEqual(response.claims[0].field, "category")

    def test_recommendations_claims_and_abstention_are_required(self) -> None:
        with self.assertRaises(ValidationError):
            GroundedResponse.model_validate(
                {
                    "summary": "Incomplete response.",
                }
            )

    def test_claims_and_abstention_are_required(self) -> None:
        with self.assertRaises(ValidationError):
            GroundedResponse.model_validate({"summary": "Incomplete response."})

    def test_unknown_claim_field_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            GroundedResponse.model_validate(
                {
                    "claims": [
                        {"place_id": 10, "field": "bus_departure", "value": "10:00"}
                    ],
                    "summary": "Unsupported claim.",
                }
            )


if __name__ == "__main__":
    unittest.main()
