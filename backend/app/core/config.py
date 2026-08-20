from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str | None = None

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_planner_base_url: str | None = None
    ollama_response_base_url: str | None = None
    ollama_embedding_base_url: str | None = None
    ollama_planner_model: str = "qwen3:8b"
    ollama_response_model: str = "gemma3:12b-it-qat"
    ollama_ingestion_model: str = "qwen3:4b"
    ollama_ingestion_base_url: str | None = None
    ollama_timeout_seconds: float = 45.0
    ollama_embedding_model: str = "bge-m3"
    rag_enabled: bool = True
    rag_evidence_limit: int = 8

    vllm_base_url: str | None = None
    vllm_api_key: str | None = None
    vllm_planner_model: str = "Qwen/Qwen3-0.6B"
    vllm_response_model: str | None = None
    vllm_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
