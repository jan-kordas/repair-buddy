from datetime import datetime

from pydantic import BaseModel


class Post(BaseModel):
    content: str
    posted_at: datetime | None


class Thread(BaseModel):
    id: str
    title: str
    url: str
    category: str
    posts: list[Post] = []
    ai_summary: str = ""
