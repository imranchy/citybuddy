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
from app.llm.vllm import VLLMProvider


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@lru_cache
def get_assistant_service() -> AssistantService:
    if settings.vllm_base_url and settings.vllm_api_key:
        planner_provider = VLLMProvider(
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key,
            timeout_seconds=settings.vllm_timeout_seconds,
        )
        planner_model = settings.vllm_planner_model
    else:
        planner_provider = OllamaProvider(
            base_url=settings.ollama_planner_base_url or settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
        planner_model = settings.ollama_planner_model

    return AssistantService(
        planner_provider=planner_provider,
        response_provider=OllamaProvider(
            base_url=settings.ollama_response_base_url or settings.ollama_base_url,
            timeout_seconds=settings.ollama_timeout_seconds,
        ),
        planner_model=planner_model,
        response_model=settings.ollama_response_model,
        embedding_provider=(
            OllamaEmbeddingProvider(
                base_url=settings.ollama_embedding_base_url or settings.ollama_base_url,
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
