import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMCallResult, SchemaT, milliseconds


class OllamaError(RuntimeError):
    """Raised when the local Ollama service cannot return valid output."""


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def generate_structured(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[SchemaT],
    ) -> LLMCallResult:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": output_schema.model_json_schema(),
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": 4096,
            },
        }

        try:
            if self._client is None:
                response = httpx.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            body: dict[str, Any] = response.json()
            content = body["message"]["content"]
            parsed = json.loads(content)
            output = output_schema.model_validate(parsed)
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise OllamaError(
                f"Ollama model '{model}' did not return valid structured output: "
                f"{error}"
            ) from error

        return LLMCallResult(
            output=output,
            model=str(body.get("model", model)),
            total_duration_ms=milliseconds(body.get("total_duration")),
            load_duration_ms=milliseconds(body.get("load_duration")),
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            output_tokens=int(body.get("eval_count", 0)),
            raw_content=content,
        )

    def unload_model(self, model: str) -> None:
        """Release a model after one evaluation batch."""

        payload = {"model": model, "keep_alive": 0}
        try:
            if self._client is None:
                response = httpx.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._client.post("/api/generate", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise OllamaError(f"Could not unload Ollama model '{model}': {error}") from error
