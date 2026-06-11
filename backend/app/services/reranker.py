import logging
import math

from sentence_transformers import CrossEncoder

from app.config import settings

log = logging.getLogger(__name__)


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

    def _to_score(self, raw: float) -> float:
        if self._needs_sigmoid:
            return 1.0 / (1.0 + math.exp(-raw))
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
