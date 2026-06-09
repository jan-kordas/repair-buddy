from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.services import conversation as conversation_service
from app.services.agent import ask

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
    answer, sources, merged_slots, model_used = await ask(
        request.app.state.graph,
        body.question,
        history,
        prior_slots=conversation.slots,
    )
    conversation.slots = merged_slots
    flag_modified(conversation, "slots")
    conversation_service.append_assistant_turn(
        db, conversation.id, answer, sources, model_used
    )

    await db.commit()

    return ChatResponse(
        answer=answer,
        sources=[Source(**source) for source in sources],
        conversation_id=conversation.id,
    )
