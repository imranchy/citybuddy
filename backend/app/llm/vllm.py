import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.llm.base import LLMCallResult, SchemaT


class VLLMError(RuntimeError):
    """Raised when the vLLM service cannot return valid structured output."""


class VLLMProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
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
        payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "max_tokens": 512,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.__name__,
                "schema": output_schema.model_json_schema(),
            },
        },
    }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.perf_counter()

        try:
            if self._client is None:
                response = httpx.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._client.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )

            response.raise_for_status()
            body: dict[str, Any] = response.json()

            content = body["choices"][0]["message"]["content"]

            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            parsed = json.loads(cleaned)
            output = output_schema.model_validate(parsed)

        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raw_response = ""

            try:
                if "content" in locals():
                    raw_response = str(content)[:2000]
                elif "response" in locals():
                    raw_response = response.text[:2000]
            except Exception:
                raw_response = "<unable to read response>"

            raise VLLMError(
                f"vLLM model '{model}' did not return valid structured output. "
                f"Cause: {type(error).__name__}: {error}. "
                f"Raw model content: {raw_response}"
            ) from error

        total_duration_ms = round(
            (time.perf_counter() - started) * 1000,
            3,
        )

        usage = body.get("usage") or {}

        return LLMCallResult(
            output=output,
            model=str(body.get("model", model)),
            total_duration_ms=total_duration_ms,
            load_duration_ms=0.0,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            raw_content=content,
        )