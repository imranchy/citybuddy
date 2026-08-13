import unittest

import httpx

from app.llm.embeddings import EmbeddingError, OllamaEmbeddingProvider
from app.core.rag import EMBEDDING_DIMENSIONS


class OllamaEmbeddingProviderTests(unittest.TestCase):
    def test_embeddings_are_requested_in_input_order(self) -> None:
        vector = [0.25] * EMBEDDING_DIMENSIONS

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/embed")
            self.assertEqual(request.read(), b'{"model":"bge-m3","input":["one","two"],"truncate":true}')
            return httpx.Response(200, json={"embeddings": [vector, vector]})

        client = httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://ollama.test"
        )
        provider = OllamaEmbeddingProvider(client=client)

        result = provider.embed(model="bge-m3", texts=["one", "two"])

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), EMBEDDING_DIMENSIONS)

    def test_invalid_dimensions_raise_provider_error(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"embeddings": [[1.0, 2.0]]})
            ),
            base_url="http://ollama.test",
        )

        with self.assertRaises(EmbeddingError):
            OllamaEmbeddingProvider(client=client).embed(model="bge-m3", texts=["x"])


if __name__ == "__main__":
    unittest.main()
