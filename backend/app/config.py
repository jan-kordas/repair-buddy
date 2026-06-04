from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    ollama_host: str = "localhost"
    ollama_port: int = 11434

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
