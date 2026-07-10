import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from tokenizers import Tokenizer

MACRO_MAX_TOKENS = 1200
MICRO_MAX_TOKENS = 250
MICRO_OVERLAP_TOKENS = 30

PARAGRAPH_BREAK = re.compile(r"\n\s*\n+")
SENTENCE_END = re.compile(r"(?<=[.?!])\s+")

_tokenizer: Tokenizer | None = None


def tokenizer() -> Tokenizer:
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = Tokenizer.from_pretrained("Qwen/Qwen3-Embedding-0.6B")
    return _tokenizer


def count_tokens(text: str) -> int:
    return len(tokenizer().encode(text).ids)


@dataclass
class Macro:
    id: UUID
    text: str


@dataclass
class Micro:
    parent_id: UUID
    text: str


def split_macros(text: str) -> list[Macro]:
    paragraphs = [part.strip() for part in PARAGRAPH_BREAK.split(text) if part.strip()]
    macros: list[Macro] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for paragraph in paragraphs:
        paragraph_tokens = count_tokens(paragraph)
        if buffer and buffer_tokens + paragraph_tokens > MACRO_MAX_TOKENS:
            macros.append(Macro(id=uuid4(), text="\n\n".join(buffer)))
            buffer = []
            buffer_tokens = 0
        buffer.append(paragraph)
        buffer_tokens += paragraph_tokens

    if buffer:
        macros.append(Macro(id=uuid4(), text="\n\n".join(buffer)))
    return macros


def split_micros(macro: Macro) -> list[Micro]:
    sentences = SENTENCE_END.split(macro.text)
    micros: list[Micro] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if buffer and buffer_tokens + sentence_tokens > MICRO_MAX_TOKENS:
            micros.append(Micro(parent_id=macro.id, text=" ".join(buffer)))
            overlap, overlap_tokens = _tail(buffer, MICRO_OVERLAP_TOKENS)
            buffer = overlap
            buffer_tokens = overlap_tokens
        buffer.append(sentence)
        buffer_tokens += sentence_tokens

    if buffer:
        micros.append(Micro(parent_id=macro.id, text=" ".join(buffer)))
    return micros


def _tail(sentences: list[str], max_tokens: int) -> tuple[list[str], int]:
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        sentence_tokens = count_tokens(sentence)
        if total + sentence_tokens > max_tokens:
            break
        tail.insert(0, sentence)
        total += sentence_tokens
    return tail, total