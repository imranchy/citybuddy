import unittest

from app.core.maps import GOOGLE_MAPS_TRANSIT_DISCLAIMER
from app.llm.base import LLMCallResult
from app.llm.schemas import DiscoveryIntent, GroundedResponse
from app.schemas.assistant import AssistantChatRequest
from app.schemas.place import PlaceRead
from app.services.assistant import AssistantService
from app.services.place_types import RetrievedPlace


def place(place_id: int = 10) -> RetrievedPlace:
    return RetrievedPlace(
        place=PlaceRead(
            id=place_id,
            name="Museo Test",
            category="museum",
            description="A reviewed cinema collection.",
            address="Via Test 1",
            city="Torino",
            country_code="IT",
            latitude=45.07,
            longitude=7.68,
            price_level=None,
            rating=None,
            dietary_options=[],
            opening_hours=None,
            website=None,
            operator=None,
        ),
        distance_km=1.2,
    )


def result(output, model="fake") -> LLMCallResult:
    return LLMCallResult(
        output=output,
        model=model,
        total_duration_ms=1,
        load_duration_ms=0,
        prompt_tokens=1,
        output_tokens=1,
        raw_content=output.model_dump_json(),
    )


class SequenceProvider:
    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)

    def generate_structured(self, **kwargs) -> LLMCallResult:
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return result(output)


class RecordingRetriever:
    def __init__(self, places=None) -> None:
        self.places = list(places or [])
        self.calls = []

    def __call__(self, database, **kwargs):
        self.calls.append(kwargs)
        return self.places


def intent(**updates) -> DiscoveryIntent:
    values = {
        "city": "turin",
        "categories": ["museum"],
        "limit": 5,
        "nearby": False,
        "radius_km": None,
        "wants_transport": False,
        "language": "en",
        "unsupported_constraints": [],
    }
    values.update(updates)
    return DiscoveryIntent.model_validate(values)


def grounded(place_id: int = 10) -> GroundedResponse:
    return GroundedResponse.model_validate(
        {
            "recommendations": [
                {"place_id": place_id, "reason": "A museum."}
            ],
            "claims": [
                {"place_id": place_id, "field": "category", "value": "museum"}
            ],
            "abstained": False,
            "summary": "A museum recommendation.",
        }
    )


class AssistantServiceTests(unittest.TestCase):
    def test_missing_explicit_category_is_retried(self) -> None:
        provider = SequenceProvider([intent(categories=[]), intent(limit=1)])
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=provider,
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend one museum in Turin")
        )

        self.assertEqual(response.provider_status, "available")
        self.assertEqual(response.intent.categories, ["museum"])
        self.assertEqual(response.intent.limit, 1)
        self.assertIn("one model retry", response.warnings[0])

    def test_repeated_intent_failure_recovers_category_count_and_transport(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([RuntimeError("bad"), RuntimeError("bad")]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(),
            AssistantChatRequest(
                message=(
                    "Recommend one museum in Turin and tell me how to reach it "
                    "by public transport."
                )
            ),
        )

        self.assertEqual(response.provider_status, "fallback")
        self.assertEqual(response.intent.categories, ["museum"])
        self.assertEqual(response.intent.limit, 1)
        self.assertTrue(response.intent.wants_transport)
        self.assertEqual(retriever.calls[0]["categories"], ["museum"])
        self.assertEqual(retriever.calls[0]["limit"], 1)

    def test_single_candidate_skips_unnecessary_grounding_call(self) -> None:
        provider = SequenceProvider([intent(limit=1)])
        service = AssistantService(
            provider=provider,
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend a museum")
        )

        self.assertEqual(response.provider_status, "available")
        self.assertEqual(response.recommendations[0].place.id, 10)
        self.assertEqual(provider.outputs, [])
        self.assertEqual(
            response.answer,
            "I found 1 reviewed place in the CityBuddy database.",
        )

    def test_returns_only_validated_retrieved_recommendations(self) -> None:
        retriever = RecordingRetriever([place(), place(place_id=11)])
        service = AssistantService(
            provider=SequenceProvider([intent(), grounded()]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(object(), AssistantChatRequest(message="A museum"))

        self.assertEqual(response.provider_status, "available")
        self.assertTrue(response.grounded)
        self.assertEqual(response.recommendations[0].place.id, 10)
        self.assertEqual(response.recommendations[0].reason, "Category: museum.")
        self.assertEqual(retriever.calls[0]["categories"], ["museum"])

    def test_unretrieved_model_place_triggers_deterministic_fallback(self) -> None:
        service = AssistantService(
            provider=SequenceProvider([intent(), grounded(place_id=999)]),
            model="fake",
            retriever=RecordingRetriever([place(), place(place_id=11)]),
        )

        response = service.respond(object(), AssistantChatRequest(message="A museum"))

        self.assertEqual(response.provider_status, "fallback")
        self.assertEqual(response.recommendations[0].place.id, 10)
        self.assertIn("could not be validated", response.warnings[0])

    def test_long_grounded_description_is_bounded_for_api_schema(self) -> None:
        retrieved = place()
        retrieved.place.description = "Museum detail " * 30
        grounded_output = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 10, "reason": "A museum."}
                ],
                "claims": [
                    {
                        "place_id": 10,
                        "field": "description",
                        "value": retrieved.place.description,
                    }
                ],
                "abstained": False,
                "summary": "A museum recommendation.",
            }
        )
        service = AssistantService(
            provider=SequenceProvider([intent(), grounded_output]),
            model="fake",
            retriever=RecordingRetriever([retrieved, place(place_id=11)]),
        )

        response = service.respond(object(), AssistantChatRequest(message="A museum"))

        self.assertEqual(len(response.recommendations[0].reason), 240)

    def test_transport_is_detected_and_rendered_deterministically(self) -> None:
        service = AssistantService(
            provider=SequenceProvider([intent()]),
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(),
            AssistantChatRequest(message="How do I reach this by public transport?"),
        )

        self.assertTrue(response.intent.wants_transport)
        self.assertEqual(
            response.transport_disclaimer,
            GOOGLE_MAPS_TRANSIT_DISCLAIMER,
        )
        self.assertIn("travelmode=transit", response.recommendations[0].transit_url)

    def test_model_unavailability_returns_reviewed_database_places(self) -> None:
        service = AssistantService(
            provider=SequenceProvider([RuntimeError("offline")]),
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(object(), AssistantChatRequest(message="Help me"))

        self.assertEqual(response.provider_status, "fallback")
        self.assertEqual(response.recommendations[0].place.id, 10)
        self.assertIn("unavailable", response.warnings[0])

    def test_unsupported_city_does_not_query_places(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider(
                [intent(city="lisbon", unsupported_constraints=["unsupported_city"])]
            ),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="A museum in Lisbon")
        )

        self.assertEqual(response.recommendations, [])
        self.assertEqual(retriever.calls, [])
        self.assertIn("Torino only", response.answer)

    def test_spurious_unsupported_flag_does_not_block_turin(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider(
                [
                    intent(unsupported_constraints=["unsupported_city"]),
                ]
            ),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="A museum in Turin")
        )

        self.assertEqual(response.recommendations[0].place.id, 10)
        self.assertNotIn("unsupported_city", response.intent.unsupported_constraints)

    def test_explicit_singular_request_overrides_model_default_limit(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([intent(limit=5)]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend a museum")
        )

        self.assertEqual(response.intent.limit, 1)
        self.assertEqual(retriever.calls[0]["limit"], 1)

    def test_radius_is_not_mistaken_for_result_count(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([intent(nearby=True, limit=5)]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(),
            AssistantChatRequest(
                message="Find museums near me within 2 kilometres",
                latitude=45.07,
                longitude=7.68,
                radius_km=2,
            ),
        )

        self.assertEqual(response.intent.limit, 5)
        self.assertEqual(response.intent.radius_km, 2)
        self.assertEqual(retriever.calls[0]["radius_km"], 2)

    def test_nearby_request_requires_location(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([intent(nearby=True)]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="A museum near me")
        )

        self.assertEqual(response.recommendations, [])
        self.assertEqual(retriever.calls, [])
        self.assertIn("Share your location", response.answer)


if __name__ == "__main__":
    unittest.main()
