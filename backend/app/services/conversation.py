from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message

DEFAULT_USER_ID = 1


async def get(db: AsyncSession, conversation_id: int) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    return result.scalar_one_or_none()


async def create(db: AsyncSession, user_id: int = DEFAULT_USER_ID) -> Conversation:
    conversation = Conversation(user_id=user_id)
    db.add(conversation)
    await db.flush()
    return conversation


async def list_messages(db: AsyncSession, conversation_id: int) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def load_history(db: AsyncSession, conversation_id: int) -> list[dict]:
    messages = await list_messages(db, conversation_id)
    return [{"role": message.role, "content": message.content} for message in messages]


def append_user_turn(db: AsyncSession, conversation_id: int, content: str) -> None:
    db.add(Message(conversation_id=conversation_id, role="user", content=content))


def append_assistant_turn(
    db: AsyncSession,
    conversation_id: int,
    content: str,
    sources: list[dict],
    model: str,
) -> None:
    db.add(Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        sources=sources,
        model=model,
    ))
