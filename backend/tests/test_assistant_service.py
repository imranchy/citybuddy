import unittest
from datetime import datetime, timezone

from app.llm.base import LLMCallResult
from app.llm.schemas import (
    GroundedResponse,
    PlanSynthesisResponse,
    SemanticPlan,
    ToolGroundedResponse,
)
from app.schemas.assistant import AssistantChatRequest
from app.schemas.place import PlaceRead
from app.services.assistant import AssistantService
from app.services.official_site import OfficialSiteEvidence
from app.services.place_types import RetrievedPlace
from app.services.weather import WeatherForecast, WeatherPoint


def place(place_id=10, name="Museo Test", category="museum"):
    return RetrievedPlace(
        place=PlaceRead(
            id=place_id,
            name=name,
            category=category,
            description=f"Reviewed {category} in Turin.",
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


def plan(*, language="en", city="turin", tasks, mode="single", continuation=False):
    return SemanticPlan.model_validate(
        {
            "request_language": language,
            "response_language": language,
            "city": city,
            "is_continuation": continuation,
            "mode": mode,
            "tasks": tasks,
        }
    )


def discovery_task(*, query, category="museum", quantity=1, **updates):
    task = {
        "task_type": "discovery",
        "goal": "recommend",
        "query": query,
        "categories": [] if category is None else [{"category": category, "quantity": quantity}],
        "preferences": [],
        "refers_to_context": False,
        "nearby": False,
        "wants_transport": False,
        "forecast_hours": 12,
    }
    task.update(updates)
    return task


def grounded(place_ids, summary="Here are grounded recommendations."):
    return GroundedResponse.model_validate(
        {
            "recommendations": [
                {"place_id": place_id, "reason": "A grounded choice.", "evidence_ids": []}
                for place_id in place_ids
            ],
            "claims": [],
            "abstained": False,
            "summary": summary,
        }
    )


def tool_answer(answer, *, field=None, value=None, abstained=False):
    return ToolGroundedResponse.model_validate(
        {
            "answer": answer,
            "claims": [] if field is None else [{"field": field, "value": value}],
            "abstained": abstained,
        }
    )


def result(output, model="fake"):
    return LLMCallResult(
        output=output,
        model=model,
        total_duration_ms=1,
        load_duration_ms=0,
        prompt_tokens=1,
        output_tokens=1,
        raw_content=output.model_dump_json(),
    )


class QueueProvider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return result(output, kwargs["model"])


class SmartRetriever:
    def __init__(self, places):
        self.places = list(places)
        self.calls = []

    def __call__(self, database, **kwargs):
        self.calls.append(kwargs)
        rows = self.places
        categories = kwargs.get("categories") or []
        if categories:
            rows = [item for item in rows if item.place.category in categories]
        place_ids = kwargs.get("place_ids")
        if place_ids:
            rows = [item for item in rows if item.place.id in place_ids]
        name_query = kwargs.get("name_query")
        if name_query:
            q = name_query.casefold()
            rows = [item for item in rows if q in item.place.name.casefold()]
        return rows[: kwargs.get("limit", 5)]


class FakeEmbeddingProvider:
    def __init__(self):
        self.calls = []

    def embed(self, *, model, texts):
        self.calls.append({"model": model, "texts": list(texts)})
        return [[0.1, 0.2] for _ in texts]


def weather_forecast():
    now = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)
    return WeatherForecast(
        city="Torino",
        latitude=45.0703,
        longitude=7.6869,
        timezone="Europe/Rome",
        forecast_hours=12,
        fetched_at=now,
        source_updated_at=now,
        source="MET Norway Locationforecast",
        attribution="Data from MET Norway",
        license="NLOD 2.0 / CC BY 4.0",
        current=WeatherPoint(
            time=now,
            air_temperature_c=24.5,
            relative_humidity_percent=45.0,
            wind_speed_mps=2.0,
            precipitation_amount_mm=0.0,
            symbol_code="clearsky_day",
        ),
        forecast=[],
    )


def official_evidence(page_type="menu", verified=True):
    return OfficialSiteEvidence(
        place_id=10,
        place_name="Museo Test",
        page_type=page_type,
        official_host="example.org",
        source_url="https://example.org/menu",
        fetched_at=datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc),
        verified=verified,
        reason=None if verified else "no_readable_static_content",
        title="Official information",
        text="Lunch menu: pasta and salad." if verified else None,
        truncated=False,
    )


class AssistantServiceTests(unittest.TestCase):
    def service(self, planner_outputs, response_outputs, *, retriever=None, **kwargs):
        return AssistantService(
            planner_provider=QueueProvider(planner_outputs),
            response_provider=QueueProvider(response_outputs),
            planner_model="qwen-test",
            response_model="gemma-test",
            retriever=retriever or SmartRetriever([place()]),
            **kwargs,
        )

    def test_qwen_plan_owns_german_quantity(self):
        p = plan(language="de", tasks=[discovery_task(query="Empfiehl mir zwei Museen", quantity=2)])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei")])
        response = self.service([p], [grounded([10, 11], "Zwei Museen.")], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Empfiehl mir zwei Museen", language="en")
        )
        self.assertEqual(response.intent.language, "de")
        self.assertEqual(response.intent.limit, 2)
        self.assertEqual(len(response.recommendations), 2)

    def test_qwen_plan_owns_bangla_quantity(self):
        p = plan(language="bn", tasks=[discovery_task(query="দুটি জাদুঘর দেখাও", quantity=2)])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei")])
        response = self.service([p], [grounded([10, 11], "দুটি জাদুঘর।")], retriever=retriever).respond(
            object(), AssistantChatRequest(message="দুটি জাদুঘর দেখাও", language="en")
        )
        self.assertEqual(response.intent.language, "bn")
        self.assertEqual(response.intent.limit, 2)

    def test_current_message_language_overrides_page_default(self):
        p = plan(language="de", tasks=[discovery_task(query="Ein Museum", quantity=1)])
        response = self.service([p], [grounded([10], "Ein Museum.")]).respond(
            object(), AssistantChatRequest(message="Ein Museum", language="it")
        )
        self.assertEqual(response.intent.language, "de")

    def test_explicit_response_language_is_planner_owned(self):
        p = plan(language="en", tasks=[discovery_task(query="Answer in English. Zwei Museen", quantity=2)])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei")])
        response = self.service([p], [grounded([10, 11], "Two museums.")], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Answer in English. Zwei Museen", language="de")
        )
        self.assertEqual(response.intent.language, "en")
        self.assertEqual(response.intent.limit, 2)

    def test_multi_category_quantities_are_executed_independently(self):
        task = discovery_task(query="Two museums and one park", category=None)
        task["categories"] = [
            {"category": "museum", "quantity": 2},
            {"category": "park", "quantity": 1},
        ]
        p = plan(tasks=[task])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei"), place(20, "Parco Test", "park")])
        response = self.service([p], [grounded([10, 11, 20])], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Two museums and one park")
        )
        self.assertEqual(response.intent.category_limits, {"museum": 2, "park": 1})
        self.assertEqual([r.place.category for r in response.recommendations], ["museum", "museum", "park"])

    def test_grounding_repairs_duplicate_and_unretrieved_recommendations(self):
        p = plan(tasks=[discovery_task(query="Two museums", quantity=2)])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei")])
        malformed = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 10, "reason": "First.", "evidence_ids": []},
                    {"place_id": 10, "reason": "Duplicate.", "evidence_ids": []},
                    {"place_id": 999, "reason": "Unknown.", "evidence_ids": []},
                    {"place_id": 11, "reason": "Second.", "evidence_ids": []},
                ],
                "claims": [],
                "abstained": False,
                "summary": "Model summary that should be discarded after repair.",
            }
        )
        response = self.service([p], [malformed], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Two museums")
        )
        self.assertEqual(response.provider_status, "available")
        self.assertEqual([item.place.id for item in response.recommendations], [10, 11])
        self.assertNotEqual(response.answer, malformed.summary)

    def test_grounding_repairs_unsupported_claim_without_discarding_selection(self):
        p = plan(tasks=[discovery_task(query="One museum", quantity=1)])
        malformed = GroundedResponse.model_validate(
            {
                "recommendations": [
                    {"place_id": 10, "reason": "Grounded choice.", "evidence_ids": []}
                ],
                "claims": [
                    {"place_id": 10, "field": "rating", "value": 5.0}
                ],
                "abstained": False,
                "summary": "It has a five-star rating.",
            }
        )
        response = self.service([p], [malformed]).respond(
            object(), AssistantChatRequest(message="One museum")
        )
        self.assertEqual(response.provider_status, "available")
        self.assertEqual([item.place.id for item in response.recommendations], [10])
        self.assertNotIn("five-star", response.answer.casefold())

    def test_category_quota_shortfall_is_filled_from_retrieved_places(self):
        task = discovery_task(query="Two museums and one park", category=None)
        task["categories"] = [
            {"category": "museum", "quantity": 2},
            {"category": "park", "quantity": 1},
        ]
        p = plan(tasks=[task])
        retriever = SmartRetriever([place(10), place(11, "Museum Zwei"), place(20, "Parco Test", "park")])
        incomplete = grounded([10], "Only one model-selected result.")
        response = self.service([p], [incomplete], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Two museums and one park")
        )
        self.assertEqual(response.provider_status, "available")
        self.assertEqual([r.place.category for r in response.recommendations], ["museum", "museum", "park"])

    def test_preferences_trigger_semantic_embedding(self):
        task = discovery_task(query="A quiet museum", quantity=1, preferences=["quiet", "indoors"])
        p = plan(tasks=[task])
        embeddings = FakeEmbeddingProvider()
        service = self.service(
            [p], [grounded([10])], embedding_provider=embeddings,
            evidence_retriever=lambda database, **kwargs: [],
        )
        service.respond(object(), AssistantChatRequest(message="A quiet museum"))
        self.assertEqual(len(embeddings.calls), 1)
        self.assertIn("quiet", embeddings.calls[0]["texts"][0])

    def test_weather_task_bypasses_place_retrieval(self):
        p = plan(tasks=[{
            "task_type": "weather", "goal": "answer", "query": "Weather in Turin",
            "categories": [], "preferences": [], "refers_to_context": False,
            "nearby": False, "wants_transport": False, "forecast_hours": 12,
        }])
        retriever = SmartRetriever([place()])
        service = self.service(
            [p], [tool_answer("It is 24.5°C.", field="current.air_temperature_c", value=24.5)],
            retriever=retriever, weather_tool=lambda request: weather_forecast(),
        )
        response = service.respond(object(), AssistantChatRequest(message="Weather in Turin"))
        self.assertEqual(response.intent.tool_intent, "weather")
        self.assertEqual(retriever.calls, [])

    def test_official_menu_uses_named_reviewed_place(self):
        p = plan(tasks=[{
            "task_type": "official_menu", "goal": "answer", "query": "Menu at Museo Test",
            "categories": [{"category": "museum", "quantity": 1}], "preferences": [],
            "target_place_name": "Museo Test", "refers_to_context": False,
            "nearby": False, "wants_transport": False, "forecast_hours": 12,
        }])
        calls = []
        def official(database, **kwargs):
            calls.append(kwargs)
            return official_evidence()
        response = self.service(
            [p], [tool_answer("The menu lists pasta and salad.", field="text_excerpt", value="Lunch menu: pasta and salad.")],
            official_site_tool=official,
        ).respond(object(), AssistantChatRequest(message="Menu at Museo Test"))
        self.assertEqual(response.intent.tool_intent, "official_menu")
        self.assertEqual(calls[0]["place_id"], 10)

    def test_context_reference_scopes_retrieval(self):
        p = plan(continuation=True, tasks=[discovery_task(
            query="Tell me more about the second one", category=None, quantity=None,
            goal="describe", refers_to_context=True, reference_position=2,
        )])
        retriever = SmartRetriever([place(10), place(11, "Second Museum")])
        self.service([p], [grounded([11])], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Tell me more about the second one", context_place_ids=[10, 11])
        )
        self.assertEqual(retriever.calls[-1]["place_ids"], [11])

    def test_named_place_is_not_confused_with_supported_city(self):
        p = plan(tasks=[discovery_task(query="Museums in Turin", quantity=1, target_place_name="Turin")])
        retriever = SmartRetriever([place()])
        response = self.service([p], [grounded([10])], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Museums in Turin")
        )
        self.assertIsNone(response.intent.target_place_name)
        self.assertIsNone(retriever.calls[-1]["name_query"])

    def test_unsupported_city_is_rejected_without_retrieval(self):
        p = plan(city="milan", tasks=[discovery_task(query="Museum in Milan", quantity=1)])
        retriever = SmartRetriever([place()])
        response = self.service([p], [], retriever=retriever).respond(
            object(), AssistantChatRequest(message="Museum in Milan")
        )
        self.assertEqual(response.recommendations, [])
        self.assertEqual(retriever.calls, [])
        self.assertIn("Torino", response.answer)

    def test_invalid_planner_category_is_retried(self):
        bad = plan(tasks=[discovery_task(query="Museum", category="not_a_category", quantity=1)])
        good = plan(tasks=[discovery_task(query="Museum", quantity=1)])
        planner = QueueProvider([bad, good])
        response_provider = QueueProvider([grounded([10])])
        service = AssistantService(
            planner_provider=planner, response_provider=response_provider,
            planner_model="qwen-test", response_model="gemma-test",
            retriever=SmartRetriever([place()]),
        )
        response = service.respond(object(), AssistantChatRequest(message="Museum"))
        self.assertEqual(response.provider_status, "available")
        self.assertEqual(len(planner.calls), 2)

    def test_planner_failure_fails_closed_without_handwritten_nlp(self):
        planner = QueueProvider([RuntimeError(), RuntimeError()])
        response_provider = QueueProvider([RuntimeError()])
        retriever = SmartRetriever([place()])
        service = AssistantService(
            planner_provider=planner, response_provider=response_provider,
            planner_model="qwen-test", response_model="gemma-test", retriever=retriever,
        )
        response = service.respond(object(), AssistantChatRequest(message="Recommend a museum"))
        self.assertEqual(response.provider_status, "fallback")
        self.assertEqual(response.recommendations, [])
        self.assertEqual(retriever.calls, [])

    def test_compound_plan_is_synthesized_by_gemma(self):
        p = plan(mode="compound", tasks=[
            discovery_task(query="One museum", quantity=1),
            discovery_task(query="One park", category="park", quantity=1),
        ])
        retriever = SmartRetriever([place(10), place(20, "Parco Test", "park")])
        service = self.service(
            [p],
            [grounded([10], "Museum result."), grounded([20], "Park result."), PlanSynthesisResponse(answer="Museum then park.")],
            retriever=retriever,
        )
        response = service.respond(object(), AssistantChatRequest(message="One museum and one park"))
        self.assertEqual(response.answer, "Museum then park.")
        self.assertEqual({r.place.id for r in response.recommendations}, {10, 20})

    def test_comparison_goal_uses_semantic_context(self):
        p = plan(mode="comparison", continuation=True, tasks=[discovery_task(
            query="Which is better for a family?", category=None, quantity=None,
            goal="compare", refers_to_context=True,
        )])
        embeddings = FakeEmbeddingProvider()
        retriever = SmartRetriever([place(10), place(11, "Second Museum")])
        service = self.service(
            [p], [grounded([10, 11], "The first is better for a family.")],
            retriever=retriever, embedding_provider=embeddings,
            evidence_retriever=lambda database, **kwargs: [],
        )
        response = service.respond(
            object(), AssistantChatRequest(message="Which is better for a family?", context_place_ids=[10, 11])
        )
        self.assertEqual(response.intent.goal, "compare")
        self.assertEqual(len(embeddings.calls), 1)

    def test_nearby_without_location_returns_location_request(self):
        p = plan(tasks=[discovery_task(query="Museum near me", quantity=1, nearby=True, radius_km=2)])
        response = self.service([p], []).respond(object(), AssistantChatRequest(message="Museum near me"))
        self.assertIn("location", response.answer.casefold())


if __name__ == "__main__":
    unittest.main()
