from __future__ import annotations

from pathlib import Path

from .bm25_index import BM25Index
from .embedder import embed_one
from .reranker import rerank
from .schema import KBSearchResult
from .vector_store import query_chunks


def _bm25_path(project_id: str, data_dir: Path) -> Path:
    return data_dir / "kb_bm25" / f"{project_id}.json"


def hybrid_search(
    project_id: str,
    data_dir: Path,
    query: str,
    source_type: str | None = None,
    bm25_top_k: int = 20,
    vector_top_k: int = 20,
    rerank_top_k: int = 5,
) -> list[KBSearchResult]:
    """
    Hybrid retrieval: BM25 candidates + vector candidates → merged pool
    → cross-encoder rerank → top-K results.

    Falls back to vector-distance ordering if the reranker is unavailable.
    """
    # 1. BM25 retrieval (keyword recall: exact product names, acronyms)
    bm25 = BM25Index(_bm25_path(project_id, data_dir))
    bm25_hit_ids: set[str] = {cid for cid, _ in bm25.query(query, top_k=bm25_top_k)}

    # 2. Vector retrieval (semantic recall: paraphrases, synonyms)
    query_emb = embed_one(query)
    where = {"source_type": source_type} if source_type else None
    vec_hits = query_chunks(project_id, data_dir, query_emb, top_k=vector_top_k, where=where)

    if not vec_hits:
        return []

    # 3. Promote BM25 hits to top of candidate pool, then append vector-only hits
    bm25_first = [h for h in vec_hits if h["id"] in bm25_hit_ids]
    vec_only = [h for h in vec_hits if h["id"] not in bm25_hit_ids]
    candidates = bm25_first + vec_only

    texts = [c["text"] for c in candidates]

    # 4. Cross-encoder rerank
    try:
        ranked = rerank(query, texts, top_k=rerank_top_k)
    except Exception:
        # Fallback: cosine similarity order (distance → score)
        ranked = [(i, 1.0 - c["distance"]) for i, c in enumerate(candidates)]
        ranked.sort(key=lambda x: x[1], reverse=True)
        ranked = ranked[:rerank_top_k]

    results: list[KBSearchResult] = []
    for idx, score in ranked:
        c = candidates[idx]
        meta = c.get("metadata", {})
        results.append(KBSearchResult(
            chunk_id=c["id"],
            url=meta.get("url", ""),
            title=meta.get("title", ""),
            text=c["text"],
            source_type=meta.get("source_type", "web"),
            score=score,
        ))
    return results
