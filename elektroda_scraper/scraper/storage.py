import json
from pathlib import Path

from scraper.models import Thread


def append_thread(thread: Thread, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(thread.model_dump_json() + "\n")


def load_scraped_urls(path: Path) -> set[str]:
    urls: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                urls.add(json.loads(line)["url"])
    return urls


def load_threads(path: Path) -> list[Thread]:
    threads = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                threads.append(Thread(**json.loads(line)))
    return threads
