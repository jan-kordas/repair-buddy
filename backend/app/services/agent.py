import httpx
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from app.config import settings
from app.db import SessionLocal
from app.schemas.dialog import DialogState
from app.services.conversation import PERSISTENT_SLOT_KEYS, merge_slots
from app.services.llm import provider
from app.services.nlu import extract_slots
from app.services.rag import (
    build_user_prompt,
    contextualize_question,
    embed_question,
    extract_sources,
    generate_answer,
    search_context,
)
from app.services.reranker import reranker

CANNED_RESPONSES = {
    "greeting": (
        "Cześć! Jestem asystentem mechanika. "
        "Powiedz markę i model auta oraz opisz problem, a pomogę Ci go zdiagnozować."
    ),
    "off_topic": (
        "Pomagam wyłącznie z naprawami samochodów VW i Skoda. "
        "Zadaj pytanie związane z autem."
    ),
}

DIRECT_REPLY_INTENTS = frozenset(CANNED_RESPONSES.keys())

HISTORY_INTENTS = frozenset({"clarify", "recap"})

ASK_FOR_CAR_RESPONSE = ("Podaj markę i model swojego auta (VW Golf 4 lub Skoda Octavia I), żebym mógł dopasować odpowiedź do właściwego pojazdu.")


def _route_by_intent(state: DialogState) -> str:
    intent = state.get("intent")
    if intent in DIRECT_REPLY_INTENTS:
        return "direct_answer"
    if intent in HISTORY_INTENTS:
        return "history_answer"
    if intent == "provide_info":
        return "contextualize"
    if not state.get("car_make") and not state.get("car_model"):
        return "ask_for_car"
    return "contextualize"


def build_graph(qdrant: QdrantClient):
    async def nlu(state: DialogState) -> dict:
        extracted = await extract_slots(state["question"])
        merged = merge_slots(prior=state, new=extracted)
        return {**merged, "intent": extracted["intent"]}

    async def direct_answer(state: DialogState) -> dict:
        return {
            "answer": CANNED_RESPONSES[state["intent"]],
            "sources": [],
            "model_used": None,
        }
    
    async def history_answer(state: DialogState) -> dict:
        prompt = build_user_prompt(state["question"], [])
        answer = await generate_answer(prompt, history=state.get("history"))
        return {"answer": answer, "sources": [], "model_used": provider.model_name}
    
    async def ask_for_car(state: DialogState) -> dict:
        return {"answer": ASK_FOR_CAR_RESPONSE, "sources": [], "model_used": None}

    async def contextualize(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            search_query = await contextualize_question(
                state["question"], state.get("history") or [], client
            )
        return {"search_query": search_query}

    async def retrieve(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            vector = await embed_question(state["search_query"], client)
        async with SessionLocal() as session:
            chunks = await search_context(
                qdrant,
                session,
                vector,
                car_make=state.get("car_make"),
                car_model=state.get("car_model"),
            )
        ranked = reranker.rerank(state["search_query"], chunks, top_k=settings.reranker_top_k)
        return {"chunks": ranked}

    async def generate(state: DialogState) -> dict:
        prompt = build_user_prompt(state["question"], state["chunks"])
        answer = await generate_answer(prompt, history=state.get("history"))
        return {
            "answer": answer,
            "sources": extract_sources(state["chunks"]),
            "model_used": provider.model_name,
        }

    graph = StateGraph(DialogState)
    graph.add_node("nlu", nlu)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("history_answer", history_answer)
    graph.add_node("ask_for_car", ask_for_car)
    graph.add_node("contextualize", contextualize)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)

    graph.add_edge(START, "nlu")
    graph.add_conditional_edges(
        "nlu",
        _route_by_intent,
        {
            "direct_answer": "direct_answer",
            "history_answer": "history_answer",
            "ask_for_car": "ask_for_car",
            "contextualize": "contextualize",
        },
    )
    graph.add_edge("direct_answer", END)
    graph.add_edge("history_answer", END)
    graph.add_edge("ask_for_car", END)
    graph.add_edge("contextualize", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def ask(
    graph,
    question: str,
    history: list[dict] | None = None,
    prior_slots: dict | None = None,
) -> tuple[str, list[dict], dict, str | None]:
    initial_state: dict = {
        "question": question,
        "history": history or [],
        **(prior_slots or {}),
    }
    state = await graph.ainvoke(initial_state)
    merged_slots = {key: state.get(key) for key in PERSISTENT_SLOT_KEYS}
    merged_slots["symptoms"] = state.get("symptoms") or []
    return state["answer"], state["sources"], merged_slots, state.get("model_used")
