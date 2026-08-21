import unittest

import httpx

from app.core.rag import EMBEDDING_DIMENSIONS
from app.llm.embeddings import EmbeddingError, VLLMEmbeddingProvider


class VLLMEmbeddingProviderTests(unittest.TestCase):
    def test_embeddings_are_requested_and_returned_in_input_order(self) -> None:
        first = [0.25] * EMBEDDING_DIMENSIONS
        second = [0.5] * EMBEDDING_DIMENSIONS

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/embeddings")
            self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
            self.assertEqual(
                request.read(),
                b'{"model":"BAAI/bge-m3","input":["one","two"]}',
            )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": second},
                        {"index": 0, "embedding": first},
                    ]
                },
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://vllm.test"
        )
        provider = VLLMEmbeddingProvider(
            base_url="https://vllm.test", api_key="test-secret", client=client
        )

        result = provider.embed(model="BAAI/bge-m3", texts=["one", "two"])

        self.assertEqual(result[0][0], 0.25)
        self.assertEqual(result[1][0], 0.5)
        self.assertEqual(len(result[0]), EMBEDDING_DIMENSIONS)

    def test_invalid_dimensions_raise_provider_error(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]}
                )
            ),
            base_url="https://vllm.test",
        )

        with self.assertRaises(EmbeddingError):
            VLLMEmbeddingProvider(
                base_url="https://vllm.test", api_key="test-secret", client=client
            ).embed(model="BAAI/bge-m3", texts=["x"])


if __name__ == "__main__":
    unittest.main()
