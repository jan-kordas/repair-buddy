import httpx
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from app.schemas.dialog import DialogState
from app.services.conversation import PERSISTENT_SLOT_KEYS, merge_slots
from app.services.nlu import extract_slots
from app.services.rag import (
    build_user_prompt,
    embed_question,
    extract_sources,
    generate_answer,
    search_context,
)


def build_graph(qdrant: QdrantClient):
    async def nlu(state: DialogState) -> dict:
        extracted = await extract_slots(state["question"])
        merged = merge_slots(prior=state, new=extracted)
        return {**merged, "intent": extracted["intent"]}

    async def retrieve(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            vector = await embed_question(state["question"], client)
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
        return {"answer": answer, "sources": extract_sources(state["chunks"])}

    graph = StateGraph(DialogState)
    graph.add_node("nlu", nlu)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "nlu")
    graph.add_edge("nlu", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def ask(
    graph,
    question: str,
    history: list[dict] | None = None,
    prior_slots: dict | None = None,
) -> tuple[str, list[dict], dict]:
    initial_state: dict = {
        "question": question,
        "history": history or [],
        **(prior_slots or {}),
    }
    state = await graph.ainvoke(initial_state)
    merged_slots = {key: state.get(key) for key in PERSISTENT_SLOT_KEYS}
    merged_slots["symptoms"] = state.get("symptoms") or []
    return state["answer"], state["sources"], merged_slots
