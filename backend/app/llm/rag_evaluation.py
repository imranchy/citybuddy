from __future__ import annotations

from math import sqrt
from typing import Any

from app.llm.embeddings import EmbeddingProvider


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = sqrt(sum(a * a for a in left)) * sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


def evaluate_rag_dataset(
    provider: EmbeddingProvider,
    *,
    model: str,
    dataset: dict[str, Any],
    k: int = 3,
) -> dict[str, Any]:
    documents = dataset["documents"]
    cases = dataset["cases"]
    document_vectors = provider.embed(
        model=model, texts=[item["text"] for item in documents]
    )
    query_vectors = provider.embed(
        model=model, texts=[item["query"] for item in cases]
    )
    results = []
    for case, query_vector in zip(cases, query_vectors, strict=True):
        ranked = sorted(
            zip(documents, document_vectors, strict=True),
            key=lambda item: cosine_similarity(query_vector, item[1]),
            reverse=True,
        )
        ranked_ids = [item[0]["id"] for item in ranked]
        relevant = set(case["relevant_ids"])
        top_k = ranked_ids[:k]
        recall = len(relevant.intersection(top_k)) / len(relevant)
        first_rank = next(
            (index + 1 for index, item_id in enumerate(ranked_ids) if item_id in relevant),
            None,
        )
        results.append(
            {
                "key": case["key"],
                "top_k": top_k,
                "recall_at_k": round(recall, 4),
                "reciprocal_rank": round(1 / first_rank, 4) if first_rank else 0.0,
                "passed": recall == 1.0,
            }
        )
    count = len(results)
    return {
        "dataset": dataset["name"],
        "model": model,
        "k": k,
        "cases": results,
        "metrics": {
            "recall_at_k": round(sum(item["recall_at_k"] for item in results) / count, 4),
            "mrr": round(sum(item["reciprocal_rank"] for item in results) / count, 4),
            "passed_cases": sum(item["passed"] for item in results),
            "total_cases": count,
        },
    }
