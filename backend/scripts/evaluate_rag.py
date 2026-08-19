import argparse
import json
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.llm.embeddings import OllamaEmbeddingProvider
from app.llm.rag_evaluation import evaluate_rag_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CityBuddy multilingual RAG retrieval.")
    parser.add_argument("--model", default=settings.ollama_embedding_model)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation_datasets/rag-v2.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    arguments = parser.parse_args()
    dataset = json.loads(arguments.dataset.read_text(encoding="utf-8"))
    provider = OllamaEmbeddingProvider(
        base_url=settings.ollama_embedding_base_url or settings.ollama_base_url,
        timeout_seconds=max(settings.ollama_timeout_seconds, 120),
    )
    report = evaluate_rag_dataset(provider, model=arguments.model, dataset=dataset)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    output = arguments.output_dir / f"rag-evaluation-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    metrics = report["metrics"]
    print(
        f"RAG {metrics['passed_cases']}/{metrics['total_cases']} passed; "
        f"Recall@{report['k']} {metrics['recall_at_k']:.1%}; MRR {metrics['mrr']:.3f}"
    )
    print(f"JSON report: {output}")


if __name__ == "__main__":
    main()
