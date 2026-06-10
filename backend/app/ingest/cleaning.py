import re
from collections import Counter

URL = re.compile(r"https?://\S+", re.IGNORECASE)
PAGE_REF = re.compile(r"\s*[=>→\->]+\s*(?:see\s+)?page\s+[\w.-]+", re.IGNORECASE)
PAGE_COUNTER = re.compile(
    r"\b(?:p[aá]gina|strona|page|seite)\s+\d+\s*(?:de|z|of|von)\s+\d+\b",
    re.IGNORECASE,
)
HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")

REPEAT_FRACTION = 0.3
REPEAT_MAX_LEN = 120


def dehyphenate(text: str) -> str:
    return HYPHEN_BREAK.sub(r"\1\2", text)


def repeating_lines(pages: list[str]) -> set[str]:
    counts: Counter[str] = Counter()
    for page in pages:
        unique = {line.strip() for line in page.splitlines() if line.strip()}
        unique = {line for line in unique if len(line) <= REPEAT_MAX_LEN}
        counts.update(unique)
    cutoff = max(2, int(len(pages) * REPEAT_FRACTION))
    return {line for line, count in counts.items() if count >= cutoff}


def strip_noise(text: str, repeating: set[str]) -> str:
    text = URL.sub(" ", text)
    text = PAGE_REF.sub(" ", text)
    text = PAGE_COUNTER.sub(" ", text)
    kept = [line for line in text.splitlines() if line.strip() and line.strip() not in repeating]
    return "\n".join(kept)