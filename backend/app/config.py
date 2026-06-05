from pathlib import Path

from pydantic_settings import BaseSettings

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    ollama_host: str = "localhost"
    ollama_port: int = 11434

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


settings = Settings()
