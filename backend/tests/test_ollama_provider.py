import json
import unittest

import httpx

from app.llm.ollama import OllamaError, OllamaProvider
from app.llm.schemas import DiscoveryIntent


class OllamaProviderTests(unittest.TestCase):
    def test_provider_requests_schema_and_disables_thinking(self) -> None:
        captured_payload = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_payload.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "model": "qwen3:8b",
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "city": "turin",
                                "categories": ["museum"],
                                "limit": 3,
                                "nearby": False,
                                "radius_km": None,
                                "wants_transport": False,
                                "language": "en",
                                "unsupported_constraints": [],
                            }
                        ),
                    },
                    "total_duration": 2_500_000,
                    "load_duration": 500_000,
                    "prompt_eval_count": 20,
                    "eval_count": 10,
                },
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="http://ollama.test",
        )
        provider = OllamaProvider(client=client)
        result = provider.generate_structured(
            model="qwen3:8b",
            system_prompt="system",
            user_prompt="Find three museums.",
            output_schema=DiscoveryIntent,
        )

        self.assertFalse(captured_payload["think"])
        self.assertFalse(captured_payload["stream"])
        self.assertEqual(captured_payload["options"]["temperature"], 0)
        self.assertEqual(captured_payload["format"]["type"], "object")
        self.assertEqual(result.output.categories, ["museum"])
        self.assertEqual(result.total_duration_ms, 2.5)

    def test_invalid_structured_output_is_reported(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"message": {"content": "not-json"}},
                )
            ),
            base_url="http://ollama.test",
        )

        with self.assertRaisesRegex(OllamaError, "valid structured output"):
            OllamaProvider(client=client).generate_structured(
                model="test",
                system_prompt="system",
                user_prompt="user",
                output_schema=DiscoveryIntent,
            )


if __name__ == "__main__":
    unittest.main()
