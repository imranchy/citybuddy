from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.rag import EMBEDDING_DIMENSIONS


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot return valid vectors."""


class EmbeddingProvider(Protocol):
    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in input order."""


class VLLMEmbeddingProvider:
    """OpenAI-compatible embedding client for a vLLM-served embedding model."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._client = client

    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": model, "input": list(texts)}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is None:
                response = httpx.post(
                    f"{self.base_url}/v1/embeddings",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._client.post(
                    "/v1/embeddings", json=payload, headers=headers
                )
            response.raise_for_status()
            body = response.json()
            data = body["data"]
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
            if len(ordered) != len(texts):
                raise ValueError("embedding count did not match input count")
            vectors = [
                [float(value) for value in item["embedding"]]
                for item in ordered
            ]
            if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
                raise ValueError(
                    f"embedding dimension must be {EMBEDDING_DIMENSIONS}"
                )
            return vectors
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingError(
                f"vLLM embedding model '{model}' failed: {error}"
            ) from error
