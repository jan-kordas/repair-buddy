from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services.rag import ask

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    answer, sources = await ask(req.question, qdrant=request.app.state.qdrant)
    return ChatResponse(
        answer=answer,
        sources=[Source(**source) for source in sources],
    )