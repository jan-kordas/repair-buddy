from datetime import datetime

from pydantic import BaseModel


class Post(BaseModel):
    content: str
    posted_at: datetime | None


class Thread(BaseModel):
    id: str
    title: str
    url: str
    car_make: str | None = None
    car_models: list[str] | None = None
    posts: list[Post] = []
    ai_summary: str = ""
