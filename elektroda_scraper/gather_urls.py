import argparse
import logging
import random
import time
from pathlib import Path

from scraper.discovery import (
    LISTING_READY_SELECTOR,
    SEARCH_QUERIES,
    ThreadInfo,
    build_search_url,
    meets_criteria,
    parse_listing,
)
from scraper.fetcher import Fetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

URLS_PATH = Path(__file__).parent / "urls.txt"
JSONL_PATH = Path(__file__).parent / "output" / "threads.jsonl"


def load_known_urls(urls_path: Path, jsonl_path: Path) -> set[str]:
    known: set[str] = set()
    if urls_path.exists():
        for line in urls_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                known.add(line)
    if jsonl_path.exists():
        import json
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    known.add(json.loads(line)["url"])
                except (KeyError, json.JSONDecodeError):
                    pass
    log.info("Loaded %d known URL(s) (urls.txt + threads.jsonl).", len(known))
    return known


def append_urls(urls: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = (
        path.exists()
        and path.stat().st_size > 0
        and path.read_bytes()[-1:] != b"\n"
    )
    with path.open("a", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        for url in urls:
            f.write(url + "\n")


def run(
    output: Path,
    min_replies: int,
    max_pages: int,
    limit: int,
    dry_run: bool,
    dump_html: Path | None = None,
) -> None:
    known_urls = load_known_urls(output, JSONL_PATH)
    collected: list[str] = []

    with Fetcher() as fetcher:
        for query in SEARCH_QUERIES:
            if len(collected) >= limit:
                break
            log.info("Searching: %r", query)

            for page in range(1, max_pages + 1):
                if len(collected) >= limit:
                    break

                url = build_search_url(query, page)
                log.info("  Page %d: %s", page, url)

                try:
                    driver = fetcher.get(url, ready_selector=LISTING_READY_SELECTOR)
                except Exception as exc:
                    log.error("  Failed to load listing page: %s", exc)
                    log.error(
                        "  Tip: LISTING_READY_SELECTOR=%r may need adjusting. "
                        "Open %s in a browser and inspect the first topic link.",
                        LISTING_READY_SELECTOR,
                        url,
                    )
                    break

                html = driver.page_source
                if dump_html and not dump_html.exists():
                    dump_html.write_text(html, encoding="utf-8")
                    log.info("HTML dumped to %s", dump_html)
                threads = parse_listing(html)
                if not threads:
                    log.info("  No threads found on page %d — stopping pagination.", page)
                    break

                page_urls: list[str] = []
                for thread in threads:
                    if len(collected) >= limit:
                        break
                    if thread.url in known_urls:
                        continue
                    if not meets_criteria(thread, min_replies):
                        continue
                    collected.append(thread.url)
                    known_urls.add(thread.url)
                    page_urls.append(thread.url)
                    log.info(
                        "  + %s (solved=%s replies=%d)",
                        thread.title[:80],
                        thread.is_solved,
                        thread.reply_count,
                    )

                # Persist after each page so an interrupt never loses progress.
                if page_urls and not dry_run:
                    append_urls(page_urls, output)
                log.info("  Page %d: %d new URL(s) collected.", page, len(page_urls))
                if page < max_pages:
                    time.sleep(random.randint(3, 8))

            time.sleep(random.randint(5, 12))

    if not collected:
        log.info("No new URLs found.")
        return

    if dry_run:
        print("\n--- DRY RUN — not saving ---")
        for url in collected:
            print(url)
    else:
        log.info("Saved %d new URL(s) to %s (written incrementally).", len(collected), output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover elektroda.pl threads and append qualifying URLs to urls.txt."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=URLS_PATH,
        help="Path to urls.txt (default: urls.txt next to this script)",
    )
    parser.add_argument(
        "--min-replies",
        type=int,
        default=5,
        help="Minimum reply count to qualify a thread (default: 5)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Max search result pages to browse per query (default: 3)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=400,
        help="Max new URLs to collect in one run (default: 400)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print found URLs to stdout without saving",
    )
    parser.add_argument(
        "--dump-html",
        type=Path,
        default=None,
        metavar="FILE",
        help="Save the first fetched page's HTML to FILE for debugging selectors",
    )
    args = parser.parse_args()

    run(
        output=args.output,
        min_replies=args.min_replies,
        max_pages=args.max_pages,
        limit=args.limit,
        dry_run=args.dry_run,
        dump_html=args.dump_html,
    )


if __name__ == "__main__":
    main()
