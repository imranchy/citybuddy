import unittest

from pydantic import ValidationError

from app.schemas.assistant import AssistantChatRequest, AssistantEvidence


class AssistantRequestSchemaTests(unittest.TestCase):
    def test_coordinates_must_be_supplied_together(self) -> None:
        with self.assertRaisesRegex(ValidationError, "provided together"):
            AssistantChatRequest(message="Nearby museums", latitude=45.0)

    def test_radius_requires_coordinates(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires latitude"):
            AssistantChatRequest(message="Nearby museums", radius_km=2)

    def test_history_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            AssistantChatRequest.model_validate(
                {
                    "message": "Continue",
                    "history": [
                        {"role": "user", "content": str(index)}
                        for index in range(11)
                    ],
                }
            )

    def test_language_and_context_are_validated(self) -> None:
        request = AssistantChatRequest(
            message="Quale preferisci?",
            language="it",
            context_place_ids=[10, 10, 11],
        )
        self.assertEqual(request.language, "it")
        self.assertEqual(request.context_place_ids, [10, 11])

        with self.assertRaises(ValidationError):
            AssistantChatRequest(message="Hello", language="fr")

    def test_evidence_requires_a_bounded_excerpt(self) -> None:
        evidence = AssistantEvidence(
            id=1,
            title="Museo Test",
            excerpt="Reviewed evidence.",
            source_type="citybuddy_place",
            attribution="OpenStreetMap contributors",
            license="ODbL",
        )
        self.assertEqual(evidence.license, "ODbL")
        with self.assertRaises(ValidationError):
            AssistantEvidence(
                id=1,
                title="Museo Test",
                excerpt="x" * 501,
                source_type="citybuddy_place",
            )


if __name__ == "__main__":
    unittest.main()
