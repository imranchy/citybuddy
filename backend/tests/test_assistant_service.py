import unittest

from app.core.maps import GOOGLE_MAPS_TRANSIT_DISCLAIMER
from app.llm.base import LLMCallResult
from app.llm.schemas import DiscoveryIntent, GroundedResponse, RawDiscoveryIntent
from app.schemas.assistant import AssistantChatRequest
from app.schemas.place import PlaceRead
from app.services.assistant import AssistantService
from app.services.place_types import RetrievedPlace
from app.services.rag import RetrievedEvidence


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
        self.models = []

    def generate_structured(self, **kwargs) -> LLMCallResult:
        self.models.append(kwargs["model"])
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


class FakeEmbeddingProvider:
    def embed(self, *, model, texts):
        return [[0.1, 0.2] for _ in texts]


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


def grounded(
    place_id: int = 10,
    *,
    reason: str = "A museum.",
    summary: str = "A museum recommendation.",
) -> GroundedResponse:
    return GroundedResponse.model_validate(
        {
            "recommendations": [
                {"place_id": place_id, "reason": reason}
            ],
            "claims": [
                {"place_id": place_id, "field": "category", "value": "museum"}
            ],
            "abstained": False,
            "summary": summary,
        }
    )


class AssistantServiceTests(unittest.TestCase):

    def test_raw_intent_repairs_translated_category_and_text_radius(self) -> None:
        raw_intent = RawDiscoveryIntent(
            categories=["parco"],
            nearby=False,
            radius_km=0,
            language="it",
        )
        retriever = RecordingRetriever([])
        service = AssistantService(
            provider=SequenceProvider([raw_intent]),
            model="fake",
            retriever=retriever,
        )

        response = service.respond(
            object(),
            AssistantChatRequest(
                message="Trova un parco vicino a me entro 2 km",
                language="it",
                latitude=45.0703,
                longitude=7.6869,
            ),
        )

        self.assertEqual(response.intent.categories, ["park"])
        self.assertTrue(response.intent.nearby)
        self.assertEqual(response.intent.radius_km, 2.0)
        self.assertEqual(retriever.calls[0]["categories"], ["park"])
        self.assertEqual(retriever.calls[0]["radius_km"], 2.0)

    def test_italian_explicit_count_is_application_owned(self) -> None:
        raw_intent = RawDiscoveryIntent(categories=["museo"], limit=9, language="it")
        service = AssistantService(
            provider=SequenceProvider([raw_intent]),
            model="fake",
            retriever=RecordingRetriever([]),
        )

        response = service.respond(
            object(),
            AssistantChatRequest(
                message="Consigliami due musei a Torino",
                language="it",
            ),
        )

        self.assertEqual(response.intent.categories, ["museum"])
        self.assertEqual(response.intent.limit, 2)

    def test_spurious_model_constraints_are_removed_deterministically(self) -> None:
        noisy_intent = intent(
            limit=1,
            nearby=True,
            wants_transport=True,
            unsupported_constraints=[
                "live_transport",
                "live_opening_status",
                "live_availability",
                "unverified_price",
                "unverified_rating",
                "unsupported_city",
            ],
        )
        service = AssistantService(
            provider=SequenceProvider([noisy_intent, grounded()]),
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend museums in Turin")
        )

        self.assertEqual(response.intent.unsupported_constraints, [])
        self.assertFalse(response.intent.wants_transport)
        self.assertFalse(response.intent.nearby)
        self.assertEqual(response.intent.limit, 5)
        self.assertEqual(response.warnings, [])

    def test_explicit_safety_constraints_are_derived_from_the_message(self) -> None:
        service = AssistantService(
            provider=SequenceProvider([intent(unsupported_constraints=[]), grounded()]),
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(),
            AssistantChatRequest(
                message=(
                    "Recommend one museum that is Michelin-starred and open right now, and tell "
                    "me how to reach it by public transport"
                )
            ),
        )

        self.assertEqual(
            response.intent.unsupported_constraints,
            ["live_transport", "live_opening_status", "unverified_rating"],
        )
        self.assertTrue(response.intent.wants_transport)
        self.assertEqual(response.intent.limit, 1)

    def test_routes_intent_and_grounding_to_separate_models(self) -> None:
        provider = SequenceProvider([intent(limit=1), grounded()])
        service = AssistantService(
            provider=provider,
            intent_model="small-intent-model",
            response_model="large-response-model",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend one museum")
        )

        self.assertEqual(response.provider_status, "available")
        self.assertEqual(
            provider.models, ["small-intent-model", "large-response-model"]
        )

    def test_response_model_recovers_failed_intent_model(self) -> None:
        provider = SequenceProvider(
            [RuntimeError("bad"), RuntimeError("bad"), intent(limit=1), grounded()]
        )
        service = AssistantService(
            provider=provider,
            intent_model="small-intent-model",
            response_model="large-response-model",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend one museum")
        )

        self.assertEqual(response.provider_status, "available")
        self.assertEqual(
            provider.models,
            [
                "small-intent-model",
                "small-intent-model",
                "large-response-model",
                "large-response-model",
            ],
        )
        self.assertIn("response model recovered", response.warnings[0])

    def test_semantic_evidence_is_validated_and_returned(self) -> None:
        evidence = RetrievedEvidence(
            id=31,
            place_id=10,
            title="Museo Test",
            content="Description: A reviewed cinema collection.",
            source_type="citybuddy_place",
            source_url="https://www.openstreetmap.org/node/10",
            attribution="OpenStreetMap contributors",
            license="ODbL",
            similarity=0.91,
        )
        grounded_output = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {
                        "place_id": 10,
                        "reason": "Its reviewed description highlights a cinema collection.",
                        "evidence_ids": [31],
                    }
                ],
                "claims": [
                    {
                        "place_id": 10,
                        "field": "description",
                        "value": "A reviewed cinema collection.",
                    }
                ],
                "abstained": False,
                "summary": "For cinema, Museo Test is the strongest match.",
            }
        )
        retriever = RecordingRetriever([place(), place(place_id=11)])
        service = AssistantService(
            provider=SequenceProvider([intent(limit=1), grounded_output]),
            model="fake",
            retriever=retriever,
            embedding_provider=FakeEmbeddingProvider(),
            evidence_retriever=lambda database, **kwargs: [evidence],
        )

        response = service.respond(
            object(), AssistantChatRequest(message="One museum for a cinema fan")
        )

        self.assertEqual(retriever.calls[0]["limit"], 1)
        self.assertEqual(retriever.calls[0]["place_ids"], [10])
        self.assertEqual(
            response.answer, "For cinema, Museo Test is the strongest match."
        )
        self.assertEqual(response.recommendations[0].evidence[0].id, 31)
        self.assertEqual(
            response.recommendations[0].reason,
            grounded_output.recommendations[0].reason,
        )

    def test_missing_explicit_category_is_retried(self) -> None:
        provider = SequenceProvider(
            [intent(categories=[]), intent(limit=1), grounded()]
        )
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

    def test_single_candidate_receives_a_conversational_grounded_answer(self) -> None:
        provider = SequenceProvider([intent(limit=1), grounded()])
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
            "A museum recommendation.",
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
        self.assertEqual(response.recommendations[0].reason, "A museum.")
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
        self.assertIn("verified filters", response.warnings[0])

    def test_long_grounded_description_is_bounded_for_api_schema(self) -> None:
        retrieved = place()
        retrieved.place.description = "Museum detail " * 30
        grounded_output = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 10, "reason": "R" * 240}
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
            provider=SequenceProvider([intent(), grounded()]),
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

    def test_model_failure_preserves_explicit_unsupported_city_safely(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider(
                [
                    RuntimeError("offline"),
                    RuntimeError("offline"),
                    RuntimeError("offline"),
                ]
            ),
            intent_model="small-intent-model",
            response_model="large-response-model",
            retriever=retriever,
        )

        response = service.respond(
            object(), AssistantChatRequest(message="Recommend a museum in Lisbon")
        )

        self.assertEqual(response.provider_status, "fallback")
        self.assertEqual(response.intent.city, "lisbon")
        self.assertIn("unsupported_city", response.intent.unsupported_constraints)
        self.assertEqual(response.recommendations, [])
        self.assertEqual(retriever.calls, [])

    def test_spurious_unsupported_flag_does_not_block_turin(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider(
                [
                    intent(unsupported_constraints=["unsupported_city"]),
                    grounded(),
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
            provider=SequenceProvider([intent(limit=5), grounded()]),
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
            provider=SequenceProvider([intent(nearby=True, limit=5), grounded()]),
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

    def test_explicit_language_overrides_model_language(self) -> None:
        service = AssistantService(
            provider=SequenceProvider(
                [
                    intent(language="en", limit=1),
                    grounded(
                        reason="Una collezione cinematografica verificata.",
                        summary="Ecco un luogo che potrebbe fare al caso tuo.",
                    ),
                ]
            ),
            model="fake",
            retriever=RecordingRetriever([place()]),
        )

        response = service.respond(
            object(),
            AssistantChatRequest(message="Consigliami un museo", language="it"),
        )

        self.assertEqual(response.intent.language, "it")
        self.assertEqual(response.answer, "Ecco un luogo che potrebbe fare al caso tuo.")
        self.assertEqual(
            response.recommendations[0].reason,
            "Una collezione cinematografica verificata.",
        )

    def test_referential_follow_up_is_constrained_to_previous_places(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([intent(categories=[]), grounded()]),
            model="fake",
            retriever=retriever,
        )

        service.respond(
            object(),
            AssistantChatRequest(
                message="Which one is best for cinema?",
                context_place_ids=[10, 11],
            ),
        )

        self.assertEqual(retriever.calls[0]["place_ids"], [10, 11])

    def test_new_topic_is_not_constrained_to_previous_places(self) -> None:
        retriever = RecordingRetriever([place()])
        service = AssistantService(
            provider=SequenceProvider([intent(categories=["park"]), grounded()]),
            model="fake",
            retriever=retriever,
        )

        service.respond(
            object(),
            AssistantChatRequest(
                message="Show me a park",
                context_place_ids=[10, 11],
            ),
        )

        self.assertIsNone(retriever.calls[0]["place_ids"])


if __name__ == "__main__":
    unittest.main()
