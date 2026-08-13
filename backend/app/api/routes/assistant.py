from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.llm.ollama import OllamaProvider
from app.llm.embeddings import OllamaEmbeddingProvider
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant import AssistantService


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@lru_cache
def get_assistant_service() -> AssistantService:
    return AssistantService(
        provider=OllamaProvider(
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        ),
        model=settings.ollama_model,
        embedding_provider=(
            OllamaEmbeddingProvider(
                base_url=settings.ollama_base_url,
                timeout_seconds=max(settings.ollama_timeout_seconds, 120),
            )
            if settings.rag_enabled
            else None
        ),
        embedding_model=settings.ollama_embedding_model,
        evidence_limit=settings.rag_evidence_limit,
    )


@router.post("/chat", response_model=AssistantChatResponse)
def chat(
    request: AssistantChatRequest,
    database: Annotated[Session, Depends(get_db)],
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantChatResponse:
    return service.respond(database, request)
