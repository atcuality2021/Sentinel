from __future__ import annotations

import json
from pathlib import Path

from rank_bm25 import BM25Okapi


class BM25Index:
    """Per-project BM25 index with JSON persistence (corpus is plain list[list[str]])."""

    def __init__(self, index_path: Path) -> None:
        self._path = index_path
        self._corpus: list[list[str]] = []
        self._ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        if index_path.exists():
            self._load()

    def add(self, chunk_id: str, text: str) -> None:
        self._corpus.append(text.lower().split())
        self._ids.append(chunk_id)
        self._bm25 = BM25Okapi(self._corpus)

    def query(self, text: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Return (chunk_id, score) pairs descending by BM25 score."""
        if not self._bm25 or not self._ids:
            return []
        scores = self._bm25.get_scores(text.lower().split())
        ranked = sorted(zip(self._ids, scores), key=lambda x: x[1], reverse=True)
        return [(cid, float(s)) for cid, s in ranked[:top_k] if s > 0]

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # JSON stores list[list[str]] — no arbitrary code execution risk unlike pickle.
        with self._path.open("w", encoding="utf-8") as f:
            json.dump({"corpus": self._corpus, "ids": self._ids}, f)

    def _load(self) -> None:
        with self._path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._corpus = data["corpus"]
        self._ids = data["ids"]
        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
