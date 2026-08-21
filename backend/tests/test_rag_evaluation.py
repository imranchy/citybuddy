import unittest
import json
from pathlib import Path

from app.llm.rag_evaluation import evaluate_rag_dataset
from app.core.place_catalog import DESTINATION_CATEGORIES


class FakeEmbeddingProvider:
    vectors = {
        "cinema collection": [1.0, 0.0],
        "green park": [0.0, 1.0],
        "film history": [0.9, 0.1],
        "parco verde": [0.1, 0.9],
    }

    def embed(self, *, model, texts):
        return [self.vectors[text] for text in texts]


class RagEvaluationTests(unittest.TestCase):
    def test_v2_dataset_covers_every_leaf_category_in_both_languages(self) -> None:
        dataset = json.loads(
            Path("evaluation/datasets/legacy/rag-v2.json").read_text(encoding="utf-8")
        )
        document_ids = {item["id"] for item in dataset["documents"]}
        self.assertEqual(document_ids, set(DESTINATION_CATEGORIES))
        case_keys = {item["key"] for item in dataset["cases"]}
        for category in DESTINATION_CATEGORIES:
            self.assertIn(f"{category}_en", case_keys)
            self.assertIn(f"{category}_it", case_keys)

    def test_recall_and_mrr_are_deterministic(self) -> None:
        dataset = {
            "name": "test-rag",
            "documents": [
                {"id": "cinema", "text": "cinema collection"},
                {"id": "park", "text": "green park"},
            ],
            "cases": [
                {"key": "en", "query": "film history", "relevant_ids": ["cinema"]},
                {"key": "it", "query": "parco verde", "relevant_ids": ["park"]},
            ],
        }

        report = evaluate_rag_dataset(
            FakeEmbeddingProvider(), model="fake", dataset=dataset, k=1
        )

        self.assertEqual(report["metrics"]["recall_at_k"], 1.0)
        self.assertEqual(report["metrics"]["mrr"], 1.0)
        self.assertEqual(report["metrics"]["passed_cases"], 2)


if __name__ == "__main__":
    unittest.main()
