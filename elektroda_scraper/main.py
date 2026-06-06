import argparse
import logging
from pathlib import Path

from scraper.fetcher import Fetcher
from scraper.parser import parse_thread, thread_stub_from_url
from scraper.storage import save_threads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = Path(__file__).parent / "output" / "threads.jsonl"


def read_urls(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def run(urls_file: Path, output: Path) -> None:
    urls = read_urls(urls_file)
    if not urls:
        log.warning("No URLs found in %s", urls_file)
        return

    log.info("Loaded %d URLs from %s", len(urls), urls_file)

    full_threads = []
    with Fetcher() as fetcher:
        for url in urls:
            log.info("Scraping %s", url)
            try:
                driver = fetcher.get(url)
                thread = thread_stub_from_url(url)
                full_threads.append(parse_thread(driver.page_source, thread))
            except Exception as exc:
                log.error("Failed to scrape %s: %s", url, exc)

    save_threads(full_threads, output)
    log.info("Saved %d threads to %s", len(full_threads), output)


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
