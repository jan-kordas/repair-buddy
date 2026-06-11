from pathlib import Path

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

    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    retrieval_top_k: int = 80
    reranker_top_k: int = 10
    # Chunks with sigmoid relevance score below this are dropped before LLM generation.
    # Cross-encoder sigmoid output: >0.5 = model considers chunk relevant.
    # Hallucination guard for numeric specs is handled by system prompt + code-level
    # fallback (chunks=[] AND history=[] → hardcoded refusal), so the threshold can
    # be permissive here to avoid silently dropping relevant context.
    relevance_threshold: float = 0.5

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
