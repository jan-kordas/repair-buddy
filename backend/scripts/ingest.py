import argparse
import hashlib
import json
import logging
from os.path import commonprefix
from pathlib import Path

import fitz  # pymupdf
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
JSONL_PATH = Path(__file__).resolve().parents[2] / "elektroda_scraper" / "output" / "threads.jsonl"
COLLECTION_PDF   = "repair_manuals"
COLLECTION_FORUM = "forum_posts"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
MIN_CHUNK_WORDS = 10
EMBED_BATCH = 32
UPSERT_BATCH = 256
WATERMARK_MIN_LENGTH = 30
WATERMARK_SAMPLE_PAGES = 5
WATERMARK_SAMPLE_CHARS = 500
OLLAMA_URL = f"http://{settings.ollama_host}:{settings.ollama_port}/api/embed"
# qwen3-embedding:0.6b default num_ctx in Ollama is 2048 tokens (~1500 chars of dense text)
MAX_EMBED_CHARS = 1500


def split_into_chunks(text: str) -> list[str]:
    words = text.split()
    step = CHUNK_SIZE - CHUNK_OVERLAP
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + CHUNK_SIZE])
        if len(chunk.split()) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)
    return chunks


def _embed_batch(client: httpx.Client, batch: list[str]) -> list[list[float]]:
    truncated = [t[:MAX_EMBED_CHARS] for t in batch]
    response = client.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "input": truncated})
    response.raise_for_status()
    return response.json()["embeddings"]


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    embeddings = []
    with httpx.Client(timeout=120) as client, tqdm(total=len(texts), desc="Embedding") as progress:
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            try:
                embeddings.extend(_embed_batch(client, batch))
            except httpx.HTTPStatusError as exc:
                log.warning("Batch [%d:%d] failed (%s), retrying per item.", start, start + len(batch), exc.response.status_code)
                for i, text in enumerate(batch):
                    try:
                        embeddings.extend(_embed_batch(client, [text]))
                    except httpx.HTTPStatusError:
                        log.error("Skipping chunk %d (embedding failed): %.120r", start + i, text[:120])
                        embeddings.append([0.0] * (len(embeddings[0]) if embeddings else 1))
            progress.update(len(batch))
    return embeddings


def chunk_id(source: str, page: int, index: int) -> str:
    return hashlib.md5(f"{source}_{page}_{index}".encode()).hexdigest()


def recreate_collection(qdrant: QdrantClient, collection: str, vector_size: int) -> None:
    if qdrant.collection_exists(collection):
        qdrant.delete_collection(collection)
    qdrant.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upload_to_qdrant(
    qdrant: QdrantClient, collection: str, chunks: list[dict], embeddings: list[list[float]]
) -> None:
    points = [
        PointStruct(
            id=chunk_id(chunk["source"], chunk.get("page") or 0, i),
            vector=embedding,
            payload=chunk,
        )
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    for start in range(0, len(points), UPSERT_BATCH):
        qdrant.upsert(collection_name=collection, points=points[start : start + UPSERT_BATCH])
    log.info("Upserted %d point(s) into '%s'.", len(points), collection)


def find_common_prefix(document: fitz.Document) -> str:
    samples = []
    for page in document:
        text = page.get_text().strip()
        if text:
            samples.append(text[:WATERMARK_SAMPLE_CHARS])
    if len(samples) < WATERMARK_SAMPLE_PAGES:
        return ""
    common = commonprefix(samples)
    return common if len(common) >= WATERMARK_MIN_LENGTH else ""


def detect_car_metadata(filename: str) -> dict:
    name = filename.lower()
    car_make = None
    if "skoda" in name:
        car_make = "skoda"
    elif "volkswagen" in name or "vw" in name:
        car_make = "volkswagen"
    car_models = []
    if "octavia" in name:
        car_models.append("octavia")
    if "golf" in name:
        car_models.append("golf")
    return {"car_make": car_make, "car_models": car_models or None}


def chunks_from_pdf(pdf_path: Path) -> list[dict]:
    with fitz.open(pdf_path) as document:
        metadata = detect_car_metadata(pdf_path.name)
        watermark = find_common_prefix(document)
        if watermark:
            log.info("Detected watermark (%d chars), stripping.", len(watermark))
        chunks = []
        for page_index, page in enumerate(tqdm(document, desc=pdf_path.name), start=1):
            page_text = page.get_text().strip()
            if watermark and page_text.startswith(watermark):
                page_text = page_text[len(watermark):].strip()
            for chunk in split_into_chunks(page_text):
                chunks.append(
                    {"text": chunk, "source": pdf_path.name, "page": page_index, **metadata}
                )
    return chunks


def load_threads(path: Path) -> list[dict]:
    threads = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                threads.append(json.loads(line))
    return threads


def chunks_from_threads(threads: list[dict]) -> list[dict]:
    chunks = []
    skipped = 0
    for thread in threads:
        title = thread.get("title", "")
        prefix = f"[{title}]\n" if title else ""
        base_payload = {
            "source": thread["url"],
            "page": None,
            "title": title,
            "car_make": thread.get("car_make"),
            "car_models": thread.get("car_models"),
        }

        summary = thread.get("ai_summary", "").strip()
        if summary:
            chunks.append({"text": prefix + summary, **base_payload})

        posts_text = " ".join(
            p["content"] for p in thread.get("posts", []) if p.get("content")
        )
        if not posts_text.strip():
            skipped += 1
            continue
        for chunk_text in split_into_chunks(prefix + posts_text):
            chunks.append({"text": chunk_text, **base_payload})

    if skipped:
        log.warning("Skipped %d thread(s) with no post content.", skipped)
    return chunks


def ingest_pdfs(qdrant: QdrantClient, vector_size: int) -> None:
    recreate_collection(qdrant, COLLECTION_PDF, vector_size)
    pdf_paths = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_paths:
        log.warning("No PDFs found in %s — run scripts/prepare_dataset.py first.", PDF_DIR)
        return
    for pdf_path in pdf_paths:
        log.info("Reading %s", pdf_path.name)
        chunks = chunks_from_pdf(pdf_path)
        if not chunks:
            continue
        log.info("Embedding %d chunks from %s", len(chunks), pdf_path.name)
        embeddings = generate_embeddings([c["text"] for c in chunks])
        upload_to_qdrant(qdrant, COLLECTION_PDF, chunks, embeddings)


def ingest_forum(qdrant: QdrantClient, vector_size: int) -> None:
    recreate_collection(qdrant, COLLECTION_FORUM, vector_size)
    if not JSONL_PATH.exists():
        log.warning("Elektroda JSONL not found at %s — skipping.", JSONL_PATH)
        return
    threads = load_threads(JSONL_PATH)
    log.info("Loaded %d thread(s) from elektroda.", len(threads))
    chunks = chunks_from_threads(threads)
    log.info("Embedding %d chunks from forum threads.", len(chunks))
    if chunks:
        embeddings = generate_embeddings([c["text"] for c in chunks])
        upload_to_qdrant(qdrant, COLLECTION_FORUM, chunks, embeddings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PDFs and/or forum threads into Qdrant.")
    parser.add_argument(
        "--only",
        choices=["pdfs", "forum"],
        help="Ingest only one source. Default: ingest both.",
    )
    args = parser.parse_args()

    qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=120)
    log.info("Getting vector size from test embedding...")
    vector_size = len(generate_embeddings(["test"])[0])

    if args.only != "forum":
        ingest_pdfs(qdrant, vector_size)
    if args.only != "pdfs":
        ingest_forum(qdrant, vector_size)

    log.info("Done.")


if __name__ == "__main__":
    main()
