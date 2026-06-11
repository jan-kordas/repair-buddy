import logging
import math

from sentence_transformers import CrossEncoder

from app.config import settings

log = logging.getLogger(__name__)


class Reranker:
    def __init__(self) -> None:
        self._model: CrossEncoder | None = None

    def _load(self) -> CrossEncoder:
        if self._model is None:
            log.info("Loading cross-encoder: %s", settings.reranker_model)
            self._model = CrossEncoder(settings.reranker_model)
        return self._model

    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        if not chunks:
            return chunks
        model = self._load()
        pairs = [(query, chunk["text"]) for chunk in chunks]
        raw_scores = model.predict(pairs)
        for chunk, score in zip(chunks, raw_scores):
            chunk["relevance_score"] = round(1.0 / (1.0 + math.exp(-float(score))), 4)
        ranked = sorted(chunks, key=lambda c: c["relevance_score"], reverse=True)
        return ranked[:top_k]


reranker = Reranker()
