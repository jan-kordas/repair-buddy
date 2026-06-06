import json
from pathlib import Path

from scraper.models import Thread


def save_threads(threads: list[Thread], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for thread in threads:
            f.write(thread.model_dump_json() + "\n")


def load_threads(path: Path) -> list[Thread]:
    threads = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                threads.append(Thread(**json.loads(line)))
    return threads
