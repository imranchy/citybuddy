from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:12b-it-qat"
    ollama_timeout_seconds: float = 45.0
    ollama_embedding_model: str = "bge-m3"
    rag_enabled: bool = True
    rag_evidence_limit: int = 8

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
