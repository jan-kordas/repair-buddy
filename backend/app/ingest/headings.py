import re
from collections import Counter
from dataclasses import dataclass

import fitz

HEADING_RATIO = 1.3
HEADING_MAX_LEN = 120

DOT_LEADER = re.compile(r"[.\-_]{4,}")
REAL_WORD = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŻŹąćęłńóśżźÄÖÜäöüß]{3,}")


@dataclass
class Heading:
    text: str
    page: int
    size: float


def body_font_size(doc: fitz.Document) -> float:
    counter: Counter[int] = Counter()
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    counter[round(span["size"])] += len(span["text"])
    if not counter:
        return 0.0
    return float(counter.most_common(1)[0][0])


def extract_headings(doc: fitz.Document, body_size: float) -> list[Heading]:
    cutoff = body_size * HEADING_RATIO
    headings: list[Heading] = []
    for page_index, page in enumerate(doc, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text, size = _line_text_and_size(line)
                if size >= cutoff and len(text) <= HEADING_MAX_LEN and _looks_like_heading(text):
                    headings.append(Heading(text=text, page=page_index, size=size))
    return headings


def _line_text_and_size(line: dict) -> tuple[str, float]:
    spans = line.get("spans", [])
    text = " ".join(span["text"].strip() for span in spans).strip()
    if not spans:
        return text, 0.0
    max_size = max(span["size"] for span in spans)
    return text, max_size


def _looks_like_heading(text: str) -> bool:
    if len(text) < 3:
        return False
    if DOT_LEADER.search(text):
        return False
    if not REAL_WORD.search(text):
        return False
    alpha = sum(1 for char in text if char.isalpha())
    return alpha / len(text) >= 0.5