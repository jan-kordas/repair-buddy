import argparse
import asyncio
import hashlib
import json
import logging
import re
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import delete
from tqdm import tqdm

from app.config import settings
from app.db import SessionLocal
from app.ingest.forum_cleaning import clean_post, clean_summary
from app.ingest.pipeline import MicroPayload, Parent, chunk_pdf
from app.ingest.splitter import count_tokens
from app.models import ChunkParent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

PDF_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
JSONL_PATH = Path(__file__).resolve().parents[2] / "elektroda_scraper" / "output" / "threads.jsonl"
COLLECTION_PDF = "repair_manuals"
COLLECTION_FORUM = "forum_posts"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EMBED_BATCH = 32
UPSERT_BATCH = 256
OLLAMA_URL = f"http://{settings.ollama_host}:{settings.ollama_port}/api/embed"
# qwen3-embedding:0.6b default num_ctx in Ollama is 2048 tokens (~1500 chars of dense text)
MAX_EMBED_CHARS = 1500

# Minimum words for a post chunk to be worth embedding
FORUM_POST_MIN_WORDS = 12
# Posts longer than this token count get split into sub-chunks
FORUM_POST_MAX_TOKENS = 300


def _embed_batch(client: httpx.Client, batch: list[str]) -> list[list[float]]:
    truncated = [text[:MAX_EMBED_CHARS] for text in batch]
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
                for offset, text in enumerate(batch):
                    try:
                        embeddings.extend(_embed_batch(client, [text]))
                    except httpx.HTTPStatusError:
                        log.error("Skipping chunk %d (embedding failed): %.120r", start + offset, text[:120])
                        embeddings.append([0.0] * (len(embeddings[0]) if embeddings else 1))
            progress.update(len(batch))
    return embeddings


def recreate_collection(qdrant: QdrantClient, collection: str, vector_size: int) -> None:
    if qdrant.collection_exists(collection):
        qdrant.delete_collection(collection)
    qdrant.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def micro_point_id(parent_id: str, index: int) -> str:
    return hashlib.md5(f"{parent_id}_{index}".encode()).hexdigest()


def upsert_micros(
    qdrant: QdrantClient,
    micros: list[MicroPayload],
    embeddings: list[list[float]],
) -> None:
    points = [
        PointStruct(
            id=micro_point_id(micro.parent_id, index),
            vector=embedding,
            payload={
                "parent_id": micro.parent_id,
                "text": micro.text,
                "source": micro.source,
                "page": micro.page,
                "lang": micro.lang,
                "doc_type": micro.doc_type,
                "car_makes": micro.car_makes,
                "car_models": micro.car_models,
            },
        )
        for index, (micro, embedding) in enumerate(zip(micros, embeddings))
    ]
    for start in range(0, len(points), UPSERT_BATCH):
        qdrant.upsert(collection_name=COLLECTION_PDF, points=points[start : start + UPSERT_BATCH])


def parent_to_row(parent: Parent) -> ChunkParent:
    return ChunkParent(
        id=UUID(parent.id),
        source=parent.source,
        section=parent.section,
        page_start=parent.page_start,
        page_end=parent.page_end,
        lang=parent.lang,
        doc_type=parent.doc_type,
        car_make=parent.car_make,
        car_models=parent.car_models,
        text=parent.text,
    )


async def ingest_pdfs(qdrant: QdrantClient, vector_size: int) -> None:
    recreate_collection(qdrant, COLLECTION_PDF, vector_size)
    pdf_paths = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_paths:
        log.warning("No PDFs found in %s, run scripts/prepare_dataset.py first.", PDF_DIR)
        return

    async with SessionLocal() as session:
        await session.execute(delete(ChunkParent))
        await session.commit()

        for pdf_path in pdf_paths:
            log.info("Chunking %s", pdf_path.name)
            parents, micros = chunk_pdf(pdf_path)
            if not micros:
                log.warning("No chunks from %s", pdf_path.name)
                continue
            log.info("  %d parents, %d micros", len(parents), len(micros))

            session.add_all([parent_to_row(parent) for parent in parents])
            await session.commit()

            embeddings = generate_embeddings([micro.text for micro in micros])
            upsert_micros(qdrant, micros, embeddings)


def load_threads(path: Path) -> list[dict]:
    threads = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                threads.append(json.loads(line))
    return threads


def _thread_parent_id(url: str) -> UUID:
    """Deterministic UUID from thread URL so re-ingestion is idempotent."""
    return uuid5(NAMESPACE_URL, url)


def _forum_micro_id(parent_id: UUID, index: int) -> str:
    return hashlib.md5(f"{parent_id}_{index}".encode()).hexdigest()


def _split_post_into_chunks(text: str) -> list[str]:
    """Split a single post into sub-chunks if it exceeds FORUM_POST_MAX_TOKENS."""
    if count_tokens(text) <= FORUM_POST_MAX_TOKENS:
        return [text]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0
    for para in paragraphs:
        para_tokens = count_tokens(para)
        if buffer and buffer_tokens + para_tokens > FORUM_POST_MAX_TOKENS:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_tokens = [], 0
        buffer.append(para)
        buffer_tokens += para_tokens
    if buffer:
        chunks.append("\n\n".join(buffer))
    return chunks or [text]


def build_forum_parents_and_micros(
    threads: list[dict],
) -> tuple[list[ChunkParent], list[dict]]:
    """Build one parent per thread (ai_summary or title) and micros per
    ai_summary and per cleaned post, all linked by parent_id."""
    parents: list[ChunkParent] = []
    micros: list[dict] = []
    skipped = 0

    for thread in threads:
        url = thread.get("url", "")
        title = thread.get("title", "")
        car_make = thread.get("car_make")
        car_models = thread.get("car_models")
        raw_summary = thread.get("ai_summary", "")
        summary = clean_summary(raw_summary)
        posts = thread.get("posts", [])

        parent_text = summary if summary else title
        if not parent_text:
            skipped += 1
            continue

        parent_id = _thread_parent_id(url)
        parent = ChunkParent(
            id=parent_id,
            source=url,
            section=title or None,      # repurpose section as thread title
            page_start=0,               # no pages for forum
            page_end=0,
            lang="pl",
            doc_type="forum",
            car_make=car_make,
            car_models=car_models,
            text=parent_text,
        )
        parents.append(parent)

        base_payload = {
            "parent_id": str(parent_id),
            "source": url,
            "title": title,
            "car_make": car_make,
            "car_models": car_models,
        }

        if summary:
            micros.append({"text": summary, **base_payload})

        any_post = False
        for post in posts:
            raw = post.get("content", "")
            cleaned = clean_post(raw)
            if len(cleaned.split()) < FORUM_POST_MIN_WORDS:
                continue
            any_post = True
            for sub_chunk in _split_post_into_chunks(cleaned):
                if len(sub_chunk.split()) >= FORUM_POST_MIN_WORDS:
                    micros.append({"text": sub_chunk, **base_payload})

        if not any_post and not summary:
            skipped += 1

    if skipped:
        log.warning("Skipped %d thread(s) with no usable content.", skipped)
    log.info("Built %d forum parents and %d micros.", len(parents), len(micros))
    return parents, micros


def upsert_forum(
    qdrant: QdrantClient, micros: list[dict], embeddings: list[list[float]]
) -> None:
    points = [
        PointStruct(
            id=_forum_micro_id(UUID(micro["parent_id"]), index),
            vector=embedding,
            payload=micro,
        )
        for index, (micro, embedding) in enumerate(zip(micros, embeddings))
    ]
    for start in range(0, len(points), UPSERT_BATCH):
        qdrant.upsert(collection_name=COLLECTION_FORUM, points=points[start : start + UPSERT_BATCH])


async def ingest_forum(qdrant: QdrantClient, vector_size: int) -> None:
    recreate_collection(qdrant, COLLECTION_FORUM, vector_size)
    if not JSONL_PATH.exists():
        log.warning("Elektroda JSONL not found at %s, skipping.", JSONL_PATH)
        return
    threads = load_threads(JSONL_PATH)
    log.info("Loaded %d thread(s) from elektroda.", len(threads))

    parents, micros = build_forum_parents_and_micros(threads)

    async with SessionLocal() as session:
        await session.execute(
            delete(ChunkParent).where(ChunkParent.doc_type == "forum")
        )
        session.add_all(parents)
        await session.commit()

    log.info("Embedding %d forum micros...", len(micros))
    if micros:
        embeddings = generate_embeddings([micro["text"] for micro in micros])
        upsert_forum(qdrant, micros, embeddings)


async def main() -> None:
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
        await ingest_pdfs(qdrant, vector_size)
    if args.only != "pdfs":
        await ingest_forum(qdrant, vector_size)

    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
