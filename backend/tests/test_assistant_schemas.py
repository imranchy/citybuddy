import unittest

from pydantic import ValidationError

from app.schemas.assistant import AssistantChatRequest


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


if __name__ == "__main__":
    unittest.main()
