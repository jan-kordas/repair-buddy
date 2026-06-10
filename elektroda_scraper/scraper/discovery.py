import logging
import re
from dataclasses import dataclass
from urllib.parse import urlencode

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

SEARCH_BASE = "https://www.elektroda.pl/rtvforum/find.php"

# Waits for any topic link to appear on the search results page.
# If elektroda changes their layout, adjust this selector.
LISTING_READY_SELECTOR = 'a[href*="/rtvforum/topic"]'

SEARCH_QUERIES = [
    "golf 4 usterka",
    "golf iv naprawa",
    "golf 4 diagnoza",
    "octavia 1 usterka",
    "octavia I naprawa",
    "octavia 1 diagnoza",
    "skoda octavia 1 usterka",
]

DIAGNOSTIC_KEYWORDS = [
    "diagnoza",
    "diagnostyka",
    "sprawdź",
    "sprawdzic",
    "przyczyna",
    "rozwiązanie",
    "naprawa",
    "usterka",
    "błąd",
    "objaw",
    "czujnik",
    "sterownik",
    "wtrysk",
    "ciśnienie",
    "pomiar",
]

_SOLVED_RE = re.compile(r"\[rozwiązano\]|\[solved\]", re.IGNORECASE)
# Match Golf 4 / Golf IV — word boundary after 4/iv prevents Golf 5, Golf 45, etc.
_GOLF4_RE = re.compile(r"\bgolf\s*(4|iv)\b", re.IGNORECASE)
# Match Octavia 1 / Octavia I — \b after single I rejects II, III
_OCTAVIA1_RE = re.compile(r"\boctavia\s*(1|I)\b", re.IGNORECASE)


@dataclass
class ThreadInfo:
    url: str
    title: str
    reply_count: int = 0
    is_solved: bool = False
    snippet: str = ""


def build_search_url(query: str, page: int = 1) -> str:
    params: dict[str, str | int] = {"q": query}
    if page > 1:
        params["start"] = (page - 1) * 30
    return f"{SEARCH_BASE}?{urlencode(params)}"


def parse_listing(html: str) -> list[ThreadInfo]:
    """Parse elektroda find.php search results.

    Results are post-level (same thread can appear multiple times if multiple
    posts match). Structure per result row:
      <tr class="above">
        <td class="col-b-i hidden-xs">          ← desktop column (skip mobile duplicate)
          <h2><a class="sneak-peak">TITLE</a>   ← thread title
          <section>...<a href="/rtvforum/topicN.html">DATE</a>  ← thread URL
        <td class="col-b-iv"><span>N</span>     ← reply count
    """
    soup = BeautifulSoup(html, "lxml")
    threads: list[ThreadInfo] = []
    seen: set[str] = set()

    for row in soup.select("tr.above"):
        desktop_col = row.select_one("td.col-b-i.hidden-xs")
        if not desktop_col:
            continue

        title_tag = desktop_col.select_one("h2 > a.sneak-peak")
        if not title_tag:
            continue
        title = title_tag.get_text(separator=" ", strip=True)
        if len(title) < 5:
            continue

        # Date link in section has href like "/rtvforum/topic12345.html".
        # Avoid matching "viewtopic.php" (contains "topic" but starts with "/rtvforum/view").
        topic_link = desktop_col.select_one('a[href^="/rtvforum/topic"]')
        if not topic_link:
            continue
        href = topic_link.get("href", "")
        url = f"https://www.elektroda.pl{href}"
        url = url.split("?")[0].split("#")[0]

        if url in seen:
            continue
        seen.add(url)

        reply_span = row.select_one("td.col-b-iv > span")
        try:
            reply_count = int(reply_span.get_text(strip=True)) if reply_span else 0
        except ValueError:
            reply_count = 0

        threads.append(
            ThreadInfo(
                url=url,
                title=title,
                is_solved=bool(_SOLVED_RE.search(title)),
                reply_count=reply_count,
            )
        )

    log.info("Parsed %d thread(s) from listing page.", len(threads))
    return threads


def is_target_car(thread: ThreadInfo) -> bool:
    """Return True only if title explicitly mentions Golf 4 or Octavia 1/I."""
    return bool(_GOLF4_RE.search(thread.title) or _OCTAVIA1_RE.search(thread.title))


def meets_criteria(thread: ThreadInfo, min_replies: int = 5) -> bool:
    if not is_target_car(thread):
        return False
    if thread.is_solved:
        return True
    if thread.reply_count > min_replies:
        return True
    text = (thread.title + " " + thread.snippet).lower()
    matching = sum(1 for kw in DIAGNOSTIC_KEYWORDS if kw in text)
    if matching >= 2:
        return True
    return False
