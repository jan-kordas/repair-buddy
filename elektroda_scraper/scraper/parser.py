import re
from datetime import datetime

from bs4 import BeautifulSoup

from scraper.models import Post, Thread

_GOLF4_RE = re.compile(r"golf\s*(4|iv)\b", re.IGNORECASE)
_OCTAVIA_RE = re.compile(r"octavia\b", re.IGNORECASE)

_CAR_METADATA: dict[str, dict] = {
    "golf4":    {"car_make": "volkswagen", "car_models": ["golf"]},
    "octavia1": {"car_make": "skoda",      "car_models": ["octavia"]},
}
_QUOTE_REF_RE = re.compile(r">>\d+")
_URL_RE = re.compile(r"https?://\S+")
_EDIT_MARKER_RE = re.compile(r"Dodano po (\d+ \[\w+\] ?)+:")


def thread_stub_from_url(url: str) -> Thread:
    return Thread(id=_extract_thread_id(url), title="", url=url)


def parse_thread(html: str, thread: Thread) -> Thread:
    soup = BeautifulSoup(html, "lxml")

    title = _parse_title(soup)
    posts = _parse_posts(soup)
    ai_summary = _parse_ai_summary(soup)
    category = _detect_category(title, thread.url)

    metadata = _CAR_METADATA.get(category, {"car_make": None, "car_models": None})
    return thread.model_copy(
        update={"title": title, "posts": posts, "ai_summary": ai_summary, **metadata}
    )


def _parse_title(soup: BeautifulSoup) -> str:
    h1 = soup.select_one("h1.thread-title") or soup.select_one("h1")
    if h1:
        return h1.get_text(strip=True)
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


def _parse_posts(soup: BeautifulSoup) -> list[Post]:
    posts = []
    for article in soup.select("article.table-row"):
        content_tag = article.select_one(".text-wrap")
        if not content_tag:
            continue

        for quote in content_tag.select("blockquote.reply"):
            quote.decompose()

        content = _clean_content(content_tag.get_text(separator=" ", strip=True))
        if not content:
            continue

        time_tag = article.select_one("time[datetime]")
        posted_at = _parse_datetime(time_tag["datetime"]) if time_tag else None

        posts.append(Post(content=content, posted_at=posted_at))

    return posts


def _clean_content(text: str) -> str:
    text = _QUOTE_REF_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _EDIT_MARKER_RE.sub("", text)
    return re.sub(r" {2,}", " ", text).strip()


def _detect_category(title: str, url: str) -> str:
    text = f"{title} {url}"
    if _GOLF4_RE.search(text):
        return "golf4"
    if _OCTAVIA_RE.search(text):
        return "octavia1"
    return ""



def _parse_ai_summary(soup: BeautifulSoup) -> str:
    summary_tag = soup.select_one("#topic-summary")
    if not summary_tag:
        return ""
    text = summary_tag.get_text(strip=True)
    return text.replace("Wygenerowane przez model językowy.", "").strip()


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_thread_id(url: str) -> str:
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else url
