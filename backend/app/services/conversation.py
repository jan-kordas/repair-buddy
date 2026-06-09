from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message

DEFAULT_USER_ID = 1

PERSISTENT_SLOT_KEYS = ("car_make", "car_model", "system")


def merge_slots(prior: dict, new: dict) -> dict:
    merged: dict = {}
    for key in PERSISTENT_SLOT_KEYS:
        merged[key] = new.get(key) or prior.get(key)

    prior_symptoms = prior.get("symptoms") or []
    new_symptoms = new.get("symptoms") or []
    seen = {symptom.lower() for symptom in prior_symptoms}
    merged["symptoms"] = list(prior_symptoms) + [
        symptom for symptom in new_symptoms if symptom.lower() not in seen
    ]

    return merged


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
    model: str | None,
) -> None:
    db.add(Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        sources=sources,
        model=model,
    ))
