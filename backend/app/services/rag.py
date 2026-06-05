import httpx
from qdrant_client import QdrantClient

from app.config import settings

EMBEDDING_MODEL = "qwen3-embedding:0.6b"
CHAT_MODEL = "qwen3:8b"
COLLECTION = "repair_manuals"
TOP_K = 5
SNIPPET_LENGTH = 200

OLLAMA_BASE = f"http://{settings.ollama_host}:{settings.ollama_port}"

SYSTEM_PROMPT = (
    "You are an assistant for car mechanics. "
    "Answer using ONLY the provided context from repair manuals. "
    "If the context does not contain the answer, say so clearly. "
    "Be concise and technical. Use markdown formatting (bold, lists) when helpful. "
    "Do not mention page numbers, source files, or references to the manual - "
    "the system already shows sources separately. "
    "Respond in the same language the user used in their question."
)


async def embed_question(question: str, client: httpx.AsyncClient) -> list[float]:
    response = await client.post(
        f"{OLLAMA_BASE}/api/embed",
        json={"model": EMBEDDING_MODEL, "input": [question]},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embeddings"][0]


def search_context(qdrant: QdrantClient, vector: list[float]) -> list[dict]:
    results = qdrant.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=TOP_K,
        with_payload=True,
    )
    return [point.payload for point in results.points]


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(chunk["text"] for chunk in chunks)
    return (
        f"Context from repair manuals:\n{context}\n\n"
        f"Answer this question in the same language it is written in:\n{question}"
    )


async def generate_answer(user_prompt: str, client: httpx.AsyncClient) -> str:
    response = await client.post(
        f"{OLLAMA_BASE}/api/chat",
        json={
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def extract_sources(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source": chunk["source"],
            "page": chunk["page"],
            "snippet": chunk["text"][:SNIPPET_LENGTH],
        }
        for chunk in chunks
    ]


async def ask(question: str, qdrant: QdrantClient) -> tuple[str, list[dict]]:
    async with httpx.AsyncClient() as client:
        vector = await embed_question(question, client)
        chunks = search_context(qdrant, vector)
        user_prompt = build_user_prompt(question, chunks)
        answer = await generate_answer(user_prompt, client)

    sources = extract_sources(chunks)
    return answer, sources