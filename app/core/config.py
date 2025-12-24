"""
Application Configuration
Pydantic Settings for environment-based configuration
"""

from typing import Literal
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings from environment variables
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "KHW"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # API
    api_v1_prefix: str = "/api/v1"
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",  # Vite default port
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # Database (PostgreSQL)
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/khw",
        description="PostgreSQL connection URL with asyncpg driver",
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_echo: bool = False  # SQLAlchemy logging

    # VectorStore
    vectorstore_type: Literal["mock", "pgvector", "pinecone", "qdrant"] = "mock"
    vectorstore_dimension: int = 384  # E5 embedding dimension (was 1536 for OpenAI)

    # PGVector specific (when vectorstore_type == "pgvector")
    pgvector_table_consultation: str = "consultation_vectors"
    pgvector_table_manual: str = "manual_vectors"

    # Embedding Service (E5 Model)
    # Unit Spec v1.1: ASYNC SAFETY, E5 USAGE RULES, LIFECYCLE INTEGRATION
    embedding_model: Literal["e5"] = "e5"
    e5_model_name: str = "dragonkue/multilingual-e5-small-ko-v2"
    embedding_device: Literal["cpu", "cuda"] = "cpu"  # GPU if available, otherwise CPU
    embedding_max_concurrency: int = 4  # Max concurrent embedding operations (threadpool limit)

    # LLM Configuration
    llm_provider: Literal["openai", "anthropic", "mock", "ollama"] = "mock"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2000

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: float = 300.0  # 요청 타임아웃 (초)

    # API Keys (loaded from environment)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Queue Configuration
    queue_broker_url: str = "redis://localhost:6379/0"
    queue_result_backend: str = "redis://localhost:6379/1"
    queue_retry_max_attempts: int = 3
    queue_retry_backoff_seconds: int = 60

    # Search Configuration
    search_top_k: int = 10
    search_similarity_threshold: float = 0.7
    search_timeout_seconds: int = 5

    # Manual Review Configuration
    manual_similarity_threshold: float = 0.85  # Higher threshold for manual updates
    keyword_compression_min_overlap: int = 2
    keyword_compression_bonus_weight: float = 0.1
    keyword_compression_forbidden_keywords: tuple[str, ...] = (
        "오류",
        "에러",
        "error",
        "실패",
        "fail",
        "문제",
        "issue",
        "확인",
        "체크",
        "check",
        "조치",
        "처리",
        "해결",
    )

    # Security
    secret_key: str = Field(
        default="changeme-in-production-please-use-secure-random-string",
        description="Secret key for JWT tokens",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False  # Structured JSON logging

    # Admin Bootstrap
    admin_id: str | None = None
    admin_pw: str | None = None

    @property
    def async_database_url(self) -> str:
        """Get database URL as string for SQLAlchemy"""
        return str(self.database_url)


# Global settings instance
settings = Settings()
