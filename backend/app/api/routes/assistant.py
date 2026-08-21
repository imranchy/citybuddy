from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.llm.embeddings import VLLMEmbeddingProvider
from app.llm.vllm import VLLMProvider
from app.schemas.assistant import AssistantChatRequest, AssistantChatResponse
from app.services.assistant import AssistantService


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


def _require_vllm_setting(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise RuntimeError(
            f"{name} must be configured before the CityBuddy assistant starts."
        )
    return value


@lru_cache
def get_assistant_service() -> AssistantService:
    base_url = _require_vllm_setting(settings.vllm_base_url, "VLLM_BASE_URL")
    api_key = _require_vllm_setting(settings.vllm_api_key, "VLLM_API_KEY")

    planner_provider = VLLMProvider(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=settings.vllm_timeout_seconds,
    )
    response_provider = VLLMProvider(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=settings.vllm_timeout_seconds,
    )

    embedding_provider = None
    if settings.rag_enabled:
        embedding_provider = VLLMEmbeddingProvider(
            base_url=settings.vllm_embedding_base_url or base_url,
            api_key=settings.vllm_embedding_api_key or api_key,
            timeout_seconds=max(settings.vllm_timeout_seconds, 120),
        )

    return AssistantService(
        planner_provider=planner_provider,
        response_provider=response_provider,
        planner_model=settings.vllm_planner_model,
        response_model=settings.vllm_response_model or settings.vllm_planner_model,
        embedding_provider=embedding_provider,
        embedding_model=settings.vllm_embedding_model,
        evidence_limit=settings.rag_evidence_limit,
    )


@router.post("/chat", response_model=AssistantChatResponse)
def chat(
    request: AssistantChatRequest,
    database: Annotated[Session, Depends(get_db)],
    service: Annotated[AssistantService, Depends(get_assistant_service)],
) -> AssistantChatResponse:
    return service.respond(database, request)
