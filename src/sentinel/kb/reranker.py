from __future__ import annotations

import os

import httpx

_DEFAULT_BASE = "https://rerank.atcuality.com/v1"


def rerank(
    query: str,
    documents: list[str],
    top_k: int = 5,
) -> list[tuple[int, float]]:
    """
    Call the cross-encoder reranker. Returns (original_index, score) pairs,
    sorted descending by relevance score.
    """
    if not documents:
        return []
    base = os.environ.get("RERANK_API_BASE", _DEFAULT_BASE)
    key = (
        os.environ.get("RERANK_API_KEY")
        or os.environ.get("EMBED_API_KEY")
        or os.environ.get("VLLM_API_KEY")
        or os.environ.get("ATCUALITY_API_KEY")
        or ""
    )
    resp = httpx.post(
        f"{base}/rerank",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"query": query, "documents": documents, "top_k": min(top_k, len(documents))},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", data.get("data", []))
    return [
        (r["index"], float(r.get("relevance_score", r.get("score", 0.0))))
        for r in results
    ]
