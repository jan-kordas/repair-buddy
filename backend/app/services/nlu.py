from typing import Literal

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

from app.config import settings

NLU_MODEL = settings.ollama_nlu_model

SYSTEM_PROMPT = """You are a natural language understanding component for a car repair assistant.

Extract these slots from the user's question:
- intent: one of ["question", "clarify", "provide_info", "recap", "greeting", "off_topic"]
  - question: user asks a technical car repair question
  - clarify: user asks the assistant to explain or elaborate on something it said
  - provide_info: user provides requested information (car model, symptoms, details) in response to the assistant
  - recap: user asks for a summary of the conversation
  - greeting: greeting or small talk
  - off_topic: unrelated to car repair
- car_make: one of ["vw", "skoda"] or null
- car_model: one of ["golf4", "octavia1"] or null
- system: one of ["engine", "brakes", "ac", "suspension", "electrical", "transmission"] or null
- symptoms: short Polish phrases describing what's broken (empty list if none)

Use null/empty when you cannot extract with high confidence. Do not guess.

Examples:
"jak wymienic termostat w golf 4" -> intent=question, car_make=vw, car_model=golf4, system=engine, symptoms=[]
"czesc" -> intent=greeting, all others null/empty
"octavia nie zapala, kontrolka oleju swieci" -> intent=question, car_make=skoda, car_model=octavia1, system=engine, symptoms=["nie zapala", "kontrolka oleju swieci"]
"jaka bedzie pogoda jutro" -> intent=off_topic, all others null/empty
"opowiedz mi zart" -> intent=off_topic, all others null/empty
"co ustalilismy?" -> intent=recap, all others null/empty
"przypomnij mi co mialem sprawdzic" -> intent=recap, all others null/empty
"co masz na mysli?" -> intent=clarify, all others null/empty
"mozesz rozwinac?" -> intent=clarify, all others null/empty
"jest to golf 4 z silnikiem 1.6 AKL" -> intent=provide_info, car_make=vw, car_model=golf4, all others null/empty
"mam skode octavie pierwsza generacja" -> intent=provide_info, car_make=skoda, car_model=octavia1, all others null/empty
"silnik benzynowy, auto ma 180 tys km" -> intent=provide_info, all others null/empty
"""


class Slots(BaseModel):
    intent: Literal["question", "clarify", "provide_info", "recap", "greeting", "off_topic"] = Field(
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