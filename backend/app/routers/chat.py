from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.agent import ask

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    answer, sources = await ask(request.app.state.graph, body.question)
    return ChatResponse(
        answer=answer,
        sources=[Source(**source) for source in sources],
    )