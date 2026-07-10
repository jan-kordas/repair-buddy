import asyncio
import logging
from typing import Protocol

import httpx
from openai import APIStatusError, AsyncOpenAI

from app.config import settings

log = logging.getLogger(__name__)

_OPENAI_RETRY_STATUSES = (408, 425, 429, 431, 500, 502, 503, 504)
_OPENAI_MAX_ATTEMPTS = 3


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


class OpenAIProvider:
    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when GENERATE_PROVIDER=openai")
        self.model_name = model
        self._client = AsyncOpenAI(api_key=api_key, max_retries=3)

    async def generate(self, messages: list[dict], max_tokens: int = 800) -> str:
        last_error: APIStatusError | None = None
        for attempt in range(_OPENAI_MAX_ATTEMPTS):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content
            except APIStatusError as error:
                if error.status_code not in _OPENAI_RETRY_STATUSES:
                    raise
                last_error = error
                backoff = 0.5 * (2 ** attempt)
                log.warning(
                    "OpenAI %s on attempt %d/%d, retrying in %.1fs",
                    error.status_code, attempt + 1, _OPENAI_MAX_ATTEMPTS, backoff,
                )
                await asyncio.sleep(backoff)
        assert last_error is not None
        raise last_error


def _build_provider() -> GenerateProvider:
    if settings.generate_provider == "groq":
        return GroqProvider(model=settings.groq_model, api_key=settings.groq_api_key)
    if settings.generate_provider == "openai":
        return OpenAIProvider(model=settings.openai_model, api_key=settings.openai_api_key)
    return OllamaProvider(
        model=settings.ollama_chat_model,
        host=settings.ollama_host,
        port=settings.ollama_port,
    )


provider: GenerateProvider = _build_provider()
