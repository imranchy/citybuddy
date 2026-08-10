import unittest

from pydantic import ValidationError

from app.llm.schemas import DiscoveryIntent, GroundedResponse


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
