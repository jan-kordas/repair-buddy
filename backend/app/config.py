from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_chat_model: str = "gemma3:4b"
    ollama_nlu_model: str = "gemma3:4b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"

    generate_provider: str = "ollama"  # "ollama" | "groq" | "openai"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # "llamacpp" mode falls back to Qdrant vector order if the server is
    # unreachable; "off" skips reranking entirely and ignores relevance_threshold.
    reranker_mode: Literal["local", "llamacpp", "off"] = "local"
    llamacpp_host: str = "localhost"
    llamacpp_port: int = 8081
    # Alternative: "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1" (lighter, weaker on Polish).
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    retrieval_top_k: int = 24
    reranker_top_k: int = 10
    # Min reranker score to reach the LLM — scale depends on the model, tune in .env.
    # BAAI/bge-reranker-v2-m3: 1e-3 | cross-encoder/mmarco-*: 0.5
    relevance_threshold: float = 1e-3

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "repair_buddy"
    postgres_password: str = "repair_buddy_dev_only"
    postgres_db: str = "repair_buddy"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
