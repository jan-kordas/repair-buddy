from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services import conversation as conversation_service

router = APIRouter(tags=["conversations"])


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    conversation = await conversation_service.get(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await conversation_service.list_messages(db, conversation_id)
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "sources": message.sources,
            "created_at": message.created_at.isoformat(),
        }
        for message in messages
    ]
