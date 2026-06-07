from typing import Literal

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from app.config import settings

NLU_MODEL = "qwen3:8b"

SYSTEM_PROMPT = """You are a natural language understanding component for a car repair assistant.

Extract these slots from the user's question:
- intent: one of ["question", "clarify", "greeting", "off_topic"]
- car_make: one of ["vw", "skoda"] or null
- car_model: one of ["golf4", "octavia1"] or null
- system: one of ["engine", "brakes", "ac", "suspension", "electrical", "transmission"] or null
- symptoms: short Polish phrases describing what's broken (empty list if none)

Use null/empty when you cannot extract with high confidence. Do not guess.

Examples:
"jak wymienic termostat w golf 4" -> intent=question, car_make=vw, car_model=golf4, system=engine, symptoms=[]
"czesc" -> intent=greeting, all others null/empty
"octavia nie zapala, kontrolka oleju swieci" -> intent=question, car_make=skoda, car_model=octavia1, system=engine, symptoms=["nie zapala", "kontrolka oleju swieci"]
"""


class Slots(BaseModel):
    intent: Literal["question", "clarify", "greeting", "off_topic"] = Field(
        description="Type of user message"
    )
    car_make: Literal["vw", "skoda"] | None = Field(default=None)
    car_model: Literal["golf4", "octavia1"] | None = Field(default=None)
    system: Literal[
        "engine", "brakes", "ac", "suspension", "electrical", "transmission"
    ] | None = Field(default=None)
    symptoms: list[str] = Field(default_factory=list)


_llm = ChatOllama(
    model=NLU_MODEL,
    base_url=f"http://{settings.ollama_host}:{settings.ollama_port}",
    temperature=0,
).with_structured_output(Slots)


async def extract_slots(question: str) -> dict:
    result: Slots = await _llm.ainvoke(
        [
            ("system", SYSTEM_PROMPT),
            ("human", question),
        ]
    )
    return result.model_dump()