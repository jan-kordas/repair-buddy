from datetime import datetime

from bs4 import BeautifulSoup

from scraper.models import Post, Thread


def thread_stub_from_url(url: str) -> Thread:
    return Thread(id=_extract_thread_id(url), title="", url=url, category="")


def parse_thread(html: str, thread: Thread) -> Thread:
    soup = BeautifulSoup(html, "lxml")

    title = _parse_title(soup)
    posts = _parse_posts(soup)
    ai_summary = _parse_ai_summary(soup)

    return thread.model_copy(update={"title": title, "posts": posts, "ai_summary": ai_summary})


def _parse_title(soup: BeautifulSoup) -> str:
    # elektroda.pl puts the thread title in <h1 class="thread-title"> or page <title>
    h1 = soup.select_one("h1.thread-title") or soup.select_one("h1")
    if h1:
        return h1.get_text(strip=True)
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


def _parse_posts(soup: BeautifulSoup) -> list[Post]:
    posts = []
    for article in soup.select("article.table-row"):

        content_tag = article.select_one(".text-wrap")
        content = content_tag.get_text(separator=" ", strip=True) if content_tag else ""

        time_tag = article.select_one("time[datetime]")
        posted_at = _parse_datetime(time_tag["datetime"]) if time_tag else None

        posts.append(Post(content=content, posted_at=posted_at))

    return posts


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
    
def _parse_ai_summary(soup: BeautifulSoup) -> str:
    summary_tag = soup.select_one("topic-summary")
    return summary_tag.get_text(strip=True) if summary_tag else ""


def _extract_thread_id(url: str) -> str:
    parts = [p for p in url.rstrip("/").split("/") if p]
    return parts[-1] if parts else url
