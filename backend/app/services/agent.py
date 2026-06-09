import httpx
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from app.schemas.dialog import DialogState
from app.services.conversation import PERSISTENT_SLOT_KEYS, merge_slots
from app.services.nlu import extract_slots
from app.services.rag import (
    CHAT_MODEL,
    build_user_prompt,
    contextualize_question,
    embed_question,
    extract_sources,
    generate_answer,
    search_context,
)

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


def _route_by_intent(state: DialogState) -> str:
    return "direct_answer" if state.get("intent") in DIRECT_REPLY_INTENTS else "contextualize"


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

    async def contextualize(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            search_query = await contextualize_question(
                state["question"], state.get("history") or [], client
            )
        return {"search_query": search_query}

    async def retrieve(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            vector = await embed_question(state["search_query"], client)
        chunks = search_context(
            qdrant,
            vector,
            car_make=state.get("car_make"),
            car_model=state.get("car_model"),
        )
        return {"chunks": chunks}

    async def generate(state: DialogState) -> dict:
        prompt = build_user_prompt(state["question"], state["chunks"])
        async with httpx.AsyncClient() as client:
            answer = await generate_answer(prompt, client, history=state.get("history"))
        return {
            "answer": answer,
            "sources": extract_sources(state["chunks"]),
            "model_used": CHAT_MODEL,
        }

    graph = StateGraph(DialogState)
    graph.add_node("nlu", nlu)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("contextualize", contextualize)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)

    graph.add_edge(START, "nlu")
    graph.add_conditional_edges(
        "nlu",
        _route_by_intent,
        {"direct_answer": "direct_answer", "contextualize": "contextualize"},
    )
    graph.add_edge("direct_answer", END)
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
