"""Dense-vector index for episodic run records (SENTINEL-016 G-05).

Maintains a global ChromaDB collection ``episodic_runs`` under ``data_dir/episodic_chroma/``.
Each document is a short summary text embedding the run's entity + key findings so semantic
search can surface past sessions that keyword-LIKE misses.

All public functions are fail-soft: any embedding or Chroma error returns gracefully.
"""
from __future__ import annotations

from pathlib import Path


def _episodic_col(data_dir: Path):
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(data_dir / "episodic_chroma"),
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name="episodic_runs",
        metadata={"hnsw:space": "cosine"},
    )


def _run_text(entity: str, finding_texts: list[str]) -> str:
    """Short indexable summary: entity name + up to 3 finding snippets (200 chars each)."""
    snippets = " | ".join(t[:200] for t in (finding_texts or [])[:3])
    return f"{entity}: {snippets}" if snippets else entity


def embed_and_index_run(
    run_id: str,
    entity: str,
    finding_texts: list[str],
    data_dir: Path,
    *,
    project_id: str | None = None,
) -> None:
    """Embed a run's summary text and upsert into the episodic ChromaDB collection.

    Called by RunStore.save() after the SQL row is committed. Completely fail-soft —
    a missing embed server or Chroma error is swallowed; the SQL record always wins.
    """
    try:
        from sentinel.kb.embedder import embed_one

        text = _run_text(entity, finding_texts)
        vec = embed_one(text)
        meta: dict = {"run_id": run_id, "entity": entity}
        if project_id:
            meta["project_id"] = project_id
        _episodic_col(data_dir).upsert(
            ids=[run_id],
            embeddings=[vec],
            documents=[text],
            metadatas=[meta],
        )
    except Exception:
        pass


def semantic_search_run_ids(
    query: str,
    data_dir: Path,
    top_k: int = 5,
) -> list[str]:
    """Return up to ``top_k`` run IDs whose episodic text is semantically similar to ``query``.

    Returns an empty list on any error (fail-soft).
    """
    try:
        from sentinel.kb.embedder import embed_one

        col = _episodic_col(data_dir)
        if col.count() == 0:
            return []
        vec = embed_one(query)
        result = col.query(
            query_embeddings=[vec],
            n_results=min(top_k, col.count()),
            include=["metadatas"],
        )
        return [m["run_id"] for m in result["metadatas"][0]]
    except Exception:
        return []
