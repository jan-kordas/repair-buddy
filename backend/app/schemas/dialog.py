from typing import TypedDict


class DialogState(TypedDict):
    question: str

    # Slots extracted by NLU node
    intent: str | None
    car_make: str | None
    car_model: str | None
    system: str | None
    symptoms: list[str]

    # Conversation history from prior turns: [{"role": "user"|"assistant", "content": str}]
    history: list[dict]

    # Retrieved by RAG
    chunks: list[dict]

    # Produced by generate node
    answer: str
    sources: list[dict]