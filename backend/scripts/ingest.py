import argparse
import asyncio
import hashlib
import json
import logging
from pathlib import Path
from uuid import UUID

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import delete
from tqdm import tqdm

from app.config import settings
from app.db import SessionLocal
from app.ingest.pipeline import MicroPayload, Parent, chunk_pdf
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

FORUM_CHUNK_SIZE = 512
FORUM_CHUNK_OVERLAP = 50
FORUM_MIN_CHUNK_WORDS = 10


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    embeddings = []
    with httpx.Client(timeout=120) as client, tqdm(total=len(texts), desc="Embedding") as progress:
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            response = client.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "input": batch})
            response.raise_for_status()
            embeddings.extend(response.json()["embeddings"])
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
        log.warning("No PDFs found in %s — run scripts/prepare_dataset.py first.", PDF_DIR)
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


def split_forum_chunks(text: str) -> list[str]:
    words = text.split()
    step = FORUM_CHUNK_SIZE - FORUM_CHUNK_OVERLAP
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + FORUM_CHUNK_SIZE])
        if len(chunk.split()) >= FORUM_MIN_CHUNK_WORDS:
            chunks.append(chunk)
    return chunks


def forum_chunk_id(source: str, index: int) -> str:
    return hashlib.md5(f"{source}_{index}".encode()).hexdigest()


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
            post["content"] for post in thread.get("posts", []) if post.get("content")
        )
        if not posts_text.strip():
            skipped += 1
            continue
        for chunk_text in split_forum_chunks(prefix + posts_text):
            chunks.append({"text": chunk_text, **base_payload})

    if skipped:
        log.warning("Skipped %d thread(s) with no post content.", skipped)
    return chunks


def upsert_forum(
    qdrant: QdrantClient, chunks: list[dict], embeddings: list[list[float]]
) -> None:
    points = [
        PointStruct(
            id=forum_chunk_id(chunk["source"], index),
            vector=embedding,
            payload=chunk,
        )
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    for start in range(0, len(points), UPSERT_BATCH):
        qdrant.upsert(collection_name=COLLECTION_FORUM, points=points[start : start + UPSERT_BATCH])


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
        embeddings = generate_embeddings([chunk["text"] for chunk in chunks])
        upsert_forum(qdrant, chunks, embeddings)


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
        ingest_forum(qdrant, vector_size)

    log.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
