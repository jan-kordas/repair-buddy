from typing import TypedDict


class DialogState(TypedDict):
    question: str

    # Slots extracted by NLU node
    intent: str | None
    car_make: str | None
    car_model: str | None
    system: str | None
    symptoms: list[str]

    # Retrieved by RAG
    chunks: list[dict]

    # Produced by generate node
    answer: str
    sources: list[dict]