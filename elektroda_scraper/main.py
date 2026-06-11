import argparse
import logging
import time
from pathlib import Path
import random

from scraper.fetcher import Fetcher
from scraper.parser import parse_thread, thread_stub_from_url
from scraper.storage import append_thread, load_scraped_urls

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent / "output" / "threads.jsonl"


def read_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    urls = list(set(urls))
    return urls


def resolve_output(output: Path) -> bool:
    """Return True if scraping should proceed, False if user chose to quit.
    Truncates the file when user chooses overwrite."""
    if not output.exists():
        return True

    scraped = load_scraped_urls(output)
    print(f"\nOutput file already exists: {output} ({len(scraped)} thread(s) scraped)")
    print("  [o] Overwrite — start fresh, scrape all URLs")
    print("  [a] Append   — skip already scraped URLs")
    print("  [q] Quit")

    while True:
        choice = input("Choice [o/a/q]: ").strip().lower()
        if choice == "o":
            output.write_text("", encoding="utf-8")
            log.info("Output file truncated, starting fresh.")
            return True
        if choice == "a":
            log.info("Append mode — %d URL(s) already scraped will be skipped.", len(scraped))
            return True
        if choice == "q":
            return False
        print("Please enter o, a, or q.")


def run(urls_file: Path, output: Path) -> None:
    if not resolve_output(output):
        log.info("Aborted.")
        return

    urls = read_urls(urls_file)
    if not urls:
        log.warning("No URLs found in %s", urls_file)
        return

    already_scraped = load_scraped_urls(output) if output.exists() else set()
    pending = [u for u in urls if u not in already_scraped]

    log.info("Loaded %d URL(s) from %s — %d new, %d already scraped.",
             len(urls), urls_file, len(pending), len(already_scraped))

    if not pending:
        log.info("Nothing to do.")
        return

    saved = 0
    with Fetcher() as fetcher:
        for i, url in enumerate(pending):
            timeout = random.randint(1,5)
            log.info("[%d/%d] Scraping %s", i + 1, len(pending), url)
            try:
                driver = fetcher.get(url)
                thread = thread_stub_from_url(url)
                append_thread(parse_thread(driver.page_source, thread), output)
                saved += 1
            except Exception as exc:
                log.error("Failed to scrape %s: %s", url, exc)

            if i < len(pending) - 1:
                log.info("Waiting %d seconds to avoid rate limits...", timeout)
                time.sleep(timeout)

    log.info("Done — saved %d new thread(s) to %s", saved, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Elektroda.pl forum scraper")
    parser.add_argument("urls_file", type=Path, help="Path to .txt file with URLs (one per line)")
    parser.add_argument(
        "--output", type=Path, default=OUTPUT_PATH, help="Output .jsonl file path"
    )
    args = parser.parse_args()

    if not args.urls_file.exists():
        parser.error(f"File not found: {args.urls_file}")

    run(args.urls_file, args.output)


if __name__ == "__main__":
    main()
