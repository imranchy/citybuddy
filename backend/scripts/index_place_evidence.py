import argparse

from app.core.config import settings
from app.db.database import SessionLocal
from app.llm.embeddings import OllamaEmbeddingProvider
from app.services.rag import index_evidence_candidates, pending_evidence_candidates


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be positive.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or index changed reviewed CityBuddy place evidence."
    )
    parser.add_argument("--city", default="Torino")
    parser.add_argument("--category")
    parser.add_argument("--limit", type=positive_integer)
    parser.add_argument("--batch-size", type=positive_integer, default=16)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        candidates = pending_evidence_candidates(
            database,
            city=arguments.city,
            category=arguments.category,
            limit=arguments.limit,
        )
        print(f"Evidence candidates requiring indexing: {len(candidates)}")
        for candidate in candidates[:30]:
            print(f"  PREVIEW place/{candidate.place_id}: {candidate.title}")
        if len(candidates) > 30:
            print(f"  ...and {len(candidates) - 30} more")
        if not arguments.apply:
            print("Preview complete. No evidence or embeddings were changed.")
            return
        provider = OllamaEmbeddingProvider(
            base_url=settings.ollama_embedding_base_url or settings.ollama_base_url,
            timeout_seconds=max(settings.ollama_timeout_seconds, 120),
        )
        indexed = index_evidence_candidates(
            database,
            candidates=candidates,
            provider=provider,
            model=settings.ollama_embedding_model,
            batch_size=arguments.batch_size,
            progress=lambda completed, total: print(
                f"Indexed {completed}/{total} evidence records...", flush=True
            ),
        )
        print(f"Indexed {indexed} evidence records with {settings.ollama_embedding_model}.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
