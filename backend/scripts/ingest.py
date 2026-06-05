import hashlib
import logging
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

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
COLLECTION = "repair_manuals"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
MIN_CHUNK_WORDS = 10
OCR_THRESHOLD = 50
EMBED_BATCH = 32
OLLAMA_URL = f"http://{settings.ollama_host}:{settings.ollama_port}/api/embed"


def read_page_text(page: fitz.Page) -> str:
    text = page.get_text().strip()
    if len(text) >= OCR_THRESHOLD:
        return text

    try:
        ocr_result = page.get_textpage_ocr(language="eng")
        return page.get_text(textpage=ocr_result).strip()
    except RuntimeError as error:
        raise RuntimeError(
            "OCR failed - is Tesseract installed? (`brew install tesseract`)"
        ) from error


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


def split_into_chunks(text: str) -> list[str]:
    words = text.split()
    step = CHUNK_SIZE - CHUNK_OVERLAP

    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + CHUNK_SIZE])
        if len(chunk.split()) >= MIN_CHUNK_WORDS:
            chunks.append(chunk)
    return chunks


def chunks_from_pdf(pdf_path: Path) -> list[dict]:
    with fitz.open(pdf_path) as document:
        metadata = detect_car_metadata(pdf_path.name)

        chunks = []
        for page_index, page in enumerate(tqdm(document, desc=pdf_path.name), start=1):
            page_text = read_page_text(page)
            for chunk in split_into_chunks(page_text):
                chunks.append(
                    {
                        "text": chunk,
                        "source": pdf_path.name,
                        "page": page_index,
                        **metadata,
                    }
                )
    return chunks


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


def recreate_collection(qdrant: QdrantClient, vector_size: int) -> None:
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def chunk_id(source: str, page: int, index: int) -> str:
    return hashlib.md5(f"{source}_{page}_{index}".encode()).hexdigest()


def upload_to_qdrant(
    qdrant: QdrantClient,
    chunks: list[dict],
    embeddings: list[list[float]],
) -> None:
    points = []
    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            PointStruct(
                id=chunk_id(chunk["source"], chunk["page"], index),
                vector=embedding,
                payload=chunk,
            )
        )
    qdrant.upsert(collection_name=COLLECTION, points=points)


def main() -> None:
    qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    qdrant.get_collections()

    pdf_paths = sorted(RAW_DIR.glob("*.pdf"))
    if not pdf_paths:
        log.warning("No PDFs found")
        return

    test_vector = generate_embeddings(["test"])[0]
    recreate_collection(qdrant, vector_size=len(test_vector))

    for pdf_path in pdf_paths:
        log.info(f"Reading {pdf_path.name}")
        chunks = chunks_from_pdf(pdf_path)
        if not chunks:
            continue

        log.info(f"Embedding {len(chunks)} chunks from {pdf_path.name}")
        embeddings = generate_embeddings([chunk["text"] for chunk in chunks])
        upload_to_qdrant(qdrant, chunks, embeddings)

    log.info("Done")


if __name__ == "__main__":
    main()
