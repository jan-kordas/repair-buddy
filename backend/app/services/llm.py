from typing import Protocol

import httpx

from app.config import settings


class GenerateProvider(Protocol):
    model_name: str

    async def generate(self, messages: list[dict], max_tokens: int = 800) -> str: ...


class OllamaProvider:
    def __init__(self, model: str, host: str, port: int):
        self.model_name = model
        self._base_url = f"http://{host}:{port}"

    async def generate(self, messages: list[dict], max_tokens: int = 800) -> str:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]


class GroqProvider:
    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise ValueError("GROQ_API_KEY is required when GENERATE_PROVIDER=groq")
        self.model_name = model
        self._api_key = api_key
        self._base_url = "https://api.groq.com/openai/v1"

    async def generate(self, messages: list[dict], max_tokens: int = 800) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]


def _build_provider() -> GenerateProvider:
    if settings.generate_provider == "groq":
        return GroqProvider(model=settings.groq_model, api_key=settings.groq_api_key)
    return OllamaProvider(
        model=settings.ollama_chat_model,
        host=settings.ollama_host,
        port=settings.ollama_port,
    )


provider: GenerateProvider = _build_provider()
