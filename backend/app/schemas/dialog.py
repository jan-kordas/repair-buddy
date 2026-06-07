from typing import TypedDict


class DialogState(TypedDict):
    question: str
    chunks: list[dict]
    answer: str
    sources: list[dict]