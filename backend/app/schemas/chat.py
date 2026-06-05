from pydantic import BaseModel


class Source(BaseModel):
    source: str
    page: int
    snippet: str


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]