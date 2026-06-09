import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import settings

EMBEDDING_MODEL = settings.ollama_embedding_model
CONTEXTUALIZE_MODEL = settings.ollama_chat_model
COLLECTION_PDF   = "repair_manuals"
COLLECTION_FORUM = "forum_posts"
TOP_K = 3
SNIPPET_LENGTH = 200
HISTORY_WINDOW = 4  # last N messages passed to LLM (2 user/assistant pairs)
HISTORY_MESSAGE_MAX_CHARS = 500  # truncate each history message to avoid context bloat

OLLAMA_BASE = f"http://{settings.ollama_host}:{settings.ollama_port}"

CONTEXTUALIZE_PROMPT = """Rewrite the user's latest question into a standalone form, using context from the conversation history to resolve references ("it", "this", "that", pronouns, ellipsis).

Rules:
- Preserve the language of the original question.
- Use ONLY information present in the history — do NOT invent details, prices, model versions, or anything not explicitly mentioned.
- If the question is already standalone, return it verbatim.
- Output ONLY the rewritten question — no preamble, no quotes, no explanation, no thinking.

Examples:
History: User asked "jak wymienić rozrusznik w golf 4". Question: "ile to kosztuje?" -> "ile kosztuje wymiana rozrusznika w golf 4?"
History: User asked "octavia nie odpala". Question: "co sprawdzić?" -> "co sprawdzić gdy octavia nie odpala?"
History: empty. Question: "jak wymienić termostat" -> "jak wymienić termostat"
"""


SYSTEM_PROMPT = """You are a diagnostic assistant for car mechanics specializing in Skoda Octavia I and VW Golf IV.

Sources you receive:
- Official repair manuals (authoritative, precise) — prefer these for procedures and specs.
- Forum discussions (community experience) — useful for symptoms, anecdotes, common issues.

Conversation:
- The user message may include the current question AND retrieved context chunks.
- Previous turns are in the message history — refer to them when the user uses pronouns or asks follow-ups.
- If asked about the conversation itself ("what did we talk about"), answer from history, not from context chunks.

Answering:
- Ground answers in the provided context when possible.
- If context contains relevant information, use it even if it does not perfectly match the question.
- If context is unrelated or empty, say so briefly and offer general guidance based on car mechanics knowledge.
- When manual and forum sources conflict, prefer the manual.
- Do NOT cite source labels or filenames — the UI shows sources separately.

Style:
- Be direct and technical, like talking to another mechanic.
- Use short paragraphs, not nested lists, unless the user explicitly asks for steps.
- Match the language of the user's question.
- Skip preambles ("Aby odpowiedzieć...", "Oto..."), get straight to the point.
"""


def _trim_history(history: list[dict]) -> list[dict]:
    return [
        {"role": message["role"], "content": message["content"][:HISTORY_MESSAGE_MAX_CHARS]}
        for message in history[-HISTORY_WINDOW:]
    ]


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
    user_prompt: str, history: list[dict] | None = None
) -> str:
    from app.services.llm import provider

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(_trim_history(history))
    messages.append({"role": "user", "content": user_prompt})

    return await provider.generate(messages, max_tokens=800)


async def contextualize_question(
    question: str, history: list[dict], client: httpx.AsyncClient
) -> str:
    if not history:
        return question

    messages = [{"role": "system", "content": CONTEXTUALIZE_PROMPT}]
    messages.extend(_trim_history(history))
    messages.append({"role": "user", "content": question})

    response = await client.post(
        f"{OLLAMA_BASE}/api/chat",
        json={
            "model": CONTEXTUALIZE_MODEL,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0, "num_predict": 100},
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


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
