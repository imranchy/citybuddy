import unittest

import httpx
from pydantic import BaseModel

from app.llm.vllm import VLLMError, VLLMProvider


class PlannerOutput(BaseModel):
    task: str
    city: str
    category: str
    quantity: int
    needs_location: bool


class VLLMProviderTests(unittest.TestCase):
    def test_provider_requests_schema_and_parses_structured_output(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
            body = __import__("json").loads(request.read())
            self.assertEqual(body["temperature"], 0)
            self.assertEqual(body["response_format"]["type"], "json_schema")
            return httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-1.7B",
                    "choices": [{"message": {"content": '{"task":"Find two museums near me in Turin","city":"Turin","category":"museum","quantity":2,"needs_location":true}'}}],
                    "usage": {"prompt_tokens": 43, "completion_tokens": 52},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://vllm.test")
        result = VLLMProvider(
            base_url="https://vllm.test", api_key="test-secret", client=client
        ).generate_structured(
            model="Qwen/Qwen3-1.7B",
            system_prompt="Return JSON.",
            user_prompt="Find two museums near me in Turin.",
            output_schema=PlannerOutput,
        )

        self.assertEqual(result.output.quantity, 2)
        self.assertTrue(result.output.needs_location)
        self.assertEqual(result.prompt_tokens, 43)
        self.assertEqual(result.output_tokens, 52)

    def test_invalid_structured_output_is_reported(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "model": "Qwen/Qwen3-1.7B",
                        "choices": [{"message": {"content": "not-json"}}],
                    },
                )
            ),
            base_url="https://vllm.test",
        )
        with self.assertRaisesRegex(VLLMError, "valid structured output"):
            VLLMProvider(
                base_url="https://vllm.test", api_key="test-secret", client=client
            ).generate_structured(
                model="Qwen/Qwen3-1.7B",
                system_prompt="Return JSON.",
                user_prompt="Test",
                output_schema=PlannerOutput,
            )


if __name__ == "__main__":
    unittest.main()
