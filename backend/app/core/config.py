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

    rag_enabled: bool = True
    rag_evidence_limit: int = 8

    vllm_base_url: str | None = None
    vllm_api_key: str | None = None
    vllm_planner_model: str = "Qwen/Qwen3-1.7B"
    vllm_response_model: str | None = None
    vllm_ingestion_model: str = "Qwen/Qwen3-1.7B"
    vllm_ingestion_base_url: str | None = None
    vllm_ingestion_api_key: str | None = None
    vllm_embedding_model: str = "BAAI/bge-m3"
    vllm_embedding_base_url: str | None = None
    vllm_embedding_api_key: str | None = None
    vllm_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
