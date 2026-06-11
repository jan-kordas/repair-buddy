from pydantic import BaseModel


class Source(BaseModel):
    source: str
    page: int | None
    snippet: str
    relevance_score: float | None = None


class ChatRequest(BaseModel):
    question: str
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    conversation_id: int