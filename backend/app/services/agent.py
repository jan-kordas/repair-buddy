import httpx
from langgraph.graph import END, START, StateGraph
from qdrant_client import QdrantClient

from app.schemas.dialog import DialogState
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
        return await extract_slots(state["question"])

    async def retrieve(state: DialogState) -> dict:
        async with httpx.AsyncClient() as client:
            vector = await embed_question(state["question"], client)
        chunks = search_context(qdrant, vector)
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


async def ask(graph, question: str, history: list[dict] | None = None) -> tuple[str, list[dict]]:
    state = await graph.ainvoke({"question": question, "history": history or []})
    return state["answer"], state["sources"]