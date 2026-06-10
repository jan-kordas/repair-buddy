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
SHORT_TOKEN_RATIO = 0.5
MIN_TOKENS_FOR_RATIO_CHECK = 4


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
    kept = [line for line in text.splitlines() if _keep_line(line, repeating)]
    return "\n".join(kept)


def _keep_line(line: str, repeating: set[str]) -> bool:
    stripped = line.strip()
    if not stripped or stripped in repeating:
        return False
    tokens = stripped.split()
    if len(tokens) >= MIN_TOKENS_FOR_RATIO_CHECK:
        short = sum(1 for token in tokens if len(token) <= 2)
        if short / len(tokens) > SHORT_TOKEN_RATIO:
            return False
    return True