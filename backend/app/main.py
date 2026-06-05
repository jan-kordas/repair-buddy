from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    yield
    app.state.qdrant.close()
    await engine.dispose()


app = FastAPI(title="repair-buddy", lifespan=lifespan)
app.include_router(chat.router)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/qdrant")
def qdrant_health():
    try:
        app.state.qdrant.get_collections()
        return {"status": "ok"}
    except Exception:
        return {"status": "unavailable"}


@app.get("/health/ollama")
async def ollama_health():
    try:
        async with httpx.AsyncClient() as http_client:
            await http_client.get(f"http://{settings.ollama_host}:{settings.ollama_port}/api/tags")
            return {"status": "ok"}
    except Exception:
        return {"status": "unavailable"}


@app.get("/health/postgres")
async def postgres_health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        return {"status": "unavailable"}
