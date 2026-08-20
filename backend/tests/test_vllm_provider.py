import httpx
from pydantic import BaseModel

from app.llm.vllm import VLLMProvider


class PlannerOutput(BaseModel):
    task: str
    city: str
    category: str
    quantity: int
    needs_location: bool


def test_vllm_provider_parses_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-secret"

        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-0.6B",
                "choices": [
                    {
                        "message": {
                            "content": """```json
{
  "task": "Find two museums near me in Turin",
  "city": "Turin",
  "category": "museum",
  "quantity": 2,
  "needs_location": true
}
```"""
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 43,
                    "completion_tokens": 52,
                },
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://vllm.test",
    )

    provider = VLLMProvider(
        base_url="https://vllm.test",
        api_key="test-secret",
        client=client,
    )

    result = provider.generate_structured(
        model="Qwen/Qwen3-0.6B",
        system_prompt="Return JSON.",
        user_prompt="Find two museums near me in Turin.",
        output_schema=PlannerOutput,
    )

    assert result.output.city == "Turin"
    assert result.output.category == "museum"
    assert result.output.quantity == 2
    assert result.output.needs_location is True
    assert result.prompt_tokens == 43
    assert result.output_tokens == 52