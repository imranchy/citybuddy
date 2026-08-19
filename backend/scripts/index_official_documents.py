import argparse

from app.core.config import settings
from app.db.database import SessionLocal
from app.llm.embeddings import OllamaEmbeddingProvider
from app.services.official_documents import (
    OFFICIAL_DOCUMENT_TOPICS,
    collect_official_document_candidates,
    pending_official_document_candidates,
    prune_superseded_official_chunks,
)
from app.services.rag import index_evidence_candidates


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Value must be positive.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Safely refresh stable RAG documents from reviewed places' stored official websites."
        )
    )
    parser.add_argument("--city", default="Torino")
    parser.add_argument("--place-limit", type=positive_integer)
    parser.add_argument("--batch-size", type=positive_integer, default=16)
    parser.add_argument(
        "--topic",
        action="append",
        choices=[topic.key for topic in OFFICIAL_DOCUMENT_TOPICS],
        help="Limit refresh to one or more stable official-document topics.",
    )
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    database = SessionLocal()
    try:
        collection = collect_official_document_candidates(
            database,
            city=arguments.city,
            place_limit=arguments.place_limit,
            topic_keys=arguments.topic,
        )
        pending = pending_official_document_candidates(
            database,
            candidates=collection.candidates,
        )
        print(f"Verified official document chunks collected: {len(collection.candidates)}")
        print(f"Official document chunks requiring embedding: {len(pending)}")
        if collection.failures:
            print(f"Isolated official-site retrieval failures/abstentions: {len(collection.failures)}")
            for failure in collection.failures[:20]:
                print(f"  {failure}")
        for candidate in pending[:30]:
            print(
                f"  PREVIEW place/{candidate.place_id} "
                f"{candidate.content_type}: {candidate.source_url}"
            )
        if not arguments.apply:
            print("Preview complete. No evidence or embeddings were changed.")
            return

        provider = OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            timeout_seconds=max(settings.ollama_timeout_seconds, 120),
        )
        indexed = index_evidence_candidates(
            database,
            candidates=pending,
            provider=provider,
            model=settings.ollama_embedding_model,
            batch_size=arguments.batch_size,
            progress=lambda completed, total: print(
                f"Indexed {completed}/{total} official document chunks...", flush=True
            ),
        )
        removed = prune_superseded_official_chunks(
            database,
            completed_topics=collection.completed_topics,
        )
        print(
            f"Indexed {indexed} changed official chunks with "
            f"{settings.ollama_embedding_model}; retired {removed} stale chunks."
        )
    finally:
        database.close()


if __name__ == "__main__":
    main()
