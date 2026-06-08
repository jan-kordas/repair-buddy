from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services import conversation as conversation_service
from app.services.agent import ask
from app.services.rag import CHAT_MODEL

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    if body.conversation_id is None:
        conversation = await conversation_service.create(db)
    else:
        conversation = await conversation_service.get(db, body.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

    history = await conversation_service.load_history(db, conversation.id)

    conversation_service.append_user_turn(db, conversation.id, body.question)
    answer, sources = await ask(request.app.state.graph, body.question, history)
    conversation_service.append_assistant_turn(
        db, conversation.id, answer, sources, CHAT_MODEL
    )

    await db.commit()

    return ChatResponse(
        answer=answer,
        sources=[Source(**source) for source in sources],
        conversation_id=conversation.id,
    )
