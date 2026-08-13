from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.rag import EMBEDDING_DIMENSIONS


class EmbeddingError(RuntimeError):
    """Raised when an embedding provider cannot return valid vectors."""


class EmbeddingProvider(Protocol):
    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in input order."""


class OllamaEmbeddingProvider:
    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    def embed(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": model, "input": list(texts), "truncate": True}
        try:
            if self._client is None:
                response = httpx.post(
                    f"{self.base_url}/api/embed",
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self._client.post("/api/embed", json=payload)
            response.raise_for_status()
            body = response.json()
            embeddings = body["embeddings"]
            if len(embeddings) != len(texts):
                raise ValueError("embedding count did not match input count")
            vectors = [[float(value) for value in vector] for vector in embeddings]
            if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
                raise ValueError(
                    f"embedding dimension must be {EMBEDDING_DIMENSIONS}"
                )
            return vectors
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingError(
                f"Ollama embedding model '{model}' failed: {error}"
            ) from error
