import asyncio
import logging
import math

import httpx
from sentence_transformers import CrossEncoder

from app.config import settings

log = logging.getLogger(__name__)


def _sigmoid(raw: float) -> float:
    return 1.0 / (1.0 + math.exp(-raw))


class Reranker:
    def __init__(self) -> None:
        self._model: CrossEncoder | None = None
        # BGE-reranker-v2-m3 emits already-activated [0,1] scores;
        # cross-encoder/mmarco-* emits raw logits and needs a sigmoid.
        self._needs_sigmoid: bool = not settings.reranker_model.startswith("BAAI/bge-reranker")

    def _load(self) -> CrossEncoder:
        if self._model is None:
            log.info("Loading cross-encoder: %s", settings.reranker_model)
            self._model = CrossEncoder(settings.reranker_model, max_length=512)
        return self._model

    def warmup(self) -> None:
        self._load()

    def _to_score(self, raw: float) -> float:
        if self._needs_sigmoid:
            return _sigmoid(raw)
        return raw

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        if not chunks:
            return chunks
        model = self._load()
        pairs = [(query, chunk.get("rerank_text") or chunk["text"]) for chunk in chunks]
        raw_scores = model.predict(pairs)
        for chunk, raw in zip(chunks, raw_scores):
            chunk["relevance_score"] = round(self._to_score(float(raw)), 6)
        ranked = sorted(chunks, key=lambda c: c["relevance_score"], reverse=True)
        return ranked[:top_k]


reranker = Reranker()


async def _llamacpp_rerank(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    documents = [chunk.get("rerank_text") or chunk["text"] for chunk in chunks]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{settings.llamacpp_host}:{settings.llamacpp_port}/v1/rerank",
            json={"query": query, "documents": documents, "top_n": len(documents)},
            timeout=60,
        )
    response.raise_for_status()
    # llama.cpp returns raw logits; sigmoid puts them on the same [0,1] scale
    # as the local CrossEncoder so relevance_threshold means the same thing.
    for result in response.json()["results"]:
        raw_score = float(result["relevance_score"])
        chunks[result["index"]]["relevance_score"] = round(_sigmoid(raw_score), 6)
    ranked = sorted(chunks, key=lambda chunk: chunk["relevance_score"], reverse=True)
    return ranked[:top_k]


async def rerank_and_filter(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    # "off" and the llamacpp-unreachable fallback keep Qdrant vector order
    # without per-chunk scores, so relevance_threshold can't apply there.
    if not chunks or settings.reranker_mode == "off":
        return chunks[:top_k]
    if settings.reranker_mode == "llamacpp":
        try:
            ranked = await _llamacpp_rerank(query, chunks, top_k)
        except httpx.HTTPError as error:
            log.warning(
                "llama.cpp reranker at %s:%d unavailable (%s) — falling back to vector order.",
                settings.llamacpp_host, settings.llamacpp_port, error,
            )
            return chunks[:top_k]
    else:
        # Off the event loop — otherwise torch inference blocks health checks
        # and other requests for the whole duration of the rerank.
        ranked = await asyncio.to_thread(reranker.rerank, query, chunks, top_k)
    return [chunk for chunk in ranked if chunk["relevance_score"] >= settings.relevance_threshold]
