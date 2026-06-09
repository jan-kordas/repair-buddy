import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings

EMBEDDING_MODEL = settings.ollama_embedding_model
CHAT_MODEL = settings.ollama_chat_model
COLLECTION_PDF   = "repair_manuals"
COLLECTION_FORUM = "forum_posts"
TOP_K = 5
SNIPPET_LENGTH = 200

OLLAMA_BASE = f"http://{settings.ollama_host}:{settings.ollama_port}"

SYSTEM_PROMPT = (
    "You are an assistant for car mechanics. "
    "You will receive context from two types of sources: "
    "official repair manuals (precise, authoritative) "
    "and forum discussions (real-world user experience). "
    "Answer using ONLY the provided context. "
    "If the context does not contain the answer, say so clearly. "
    "Be concise and technical. Use markdown formatting (bold, lists) when helpful. "
    "Do not reference source labels or filenames — the system shows sources separately. "
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


CAR_MAKE_PAYLOAD_ALIASES = {
    "vw": "volkswagen",
}


def _normalize_car_make(car_make: str | None) -> str | None:
    if car_make is None:
        return None
    return CAR_MAKE_PAYLOAD_ALIASES.get(car_make, car_make)


def _normalize_car_model(car_model: str | None) -> str | None:
    """Strip trailing digits so 'golf4' matches payload value 'golf'."""
    if car_model is None:
        return None
    return car_model.rstrip("0123456789") or None


def _build_filter(car_make: str | None, car_model: str | None) -> Filter | None:
    conditions: list[FieldCondition] = []
    normalized_make = _normalize_car_make(car_make)
    if normalized_make:
        conditions.append(
            FieldCondition(key="car_make", match=MatchValue(value=normalized_make))
        )
    normalized_model = _normalize_car_model(car_model)
    if normalized_model:
        conditions.append(
            FieldCondition(key="car_models", match=MatchValue(value=normalized_model))
        )
    return Filter(must=conditions) if conditions else None


def search_context(
    qdrant: QdrantClient,
    vector: list[float],
    car_make: str | None = None,
    car_model: str | None = None,
) -> list[dict]:
    query_filter = _build_filter(car_make, car_model)
    pdf_hits = qdrant.query_points(
        collection_name=COLLECTION_PDF,
        query=vector,
        limit=TOP_K,
        with_payload=True,
        query_filter=query_filter,
    ).points
    forum_hits = qdrant.query_points(
        collection_name=COLLECTION_FORUM,
        query=vector,
        limit=TOP_K,
        with_payload=True,
        query_filter=query_filter,
    ).points
    merged = sorted(pdf_hits + forum_hits, key=lambda point: point.score, reverse=True)
    return [point.payload for point in merged[:TOP_K]]


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        if chunk["source"].startswith("http"):
            label = f"[Forum: {chunk.get('title') or chunk['source']}]"
        else:
            label = f"[Repair manual, page {chunk['page']}]"
        parts.append(f"{label}\n{chunk['text']}")
    context = "\n\n---\n\n".join(parts)
    return f"Context:\n{context}\n\nQuestion: {question}"


async def generate_answer(
    user_prompt: str, client: httpx.AsyncClient, history: list[dict] | None = None
) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    response = await client.post(
        f"{OLLAMA_BASE}/api/chat",
        json={"model": CHAT_MODEL, "messages": messages, "stream": False},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def extract_sources(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source": chunk["source"],
            "page": chunk.get("page"),
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
