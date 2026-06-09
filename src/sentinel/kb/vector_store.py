from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings


def _collection(project_id: str, data_dir: Path) -> chromadb.Collection:
    client = chromadb.PersistentClient(
        path=str(data_dir / "kb_chroma"),
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(
        name=f"kb_{project_id}",
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    project_id: str,
    data_dir: Path,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict],
) -> None:
    _collection(project_id, data_dir).upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


def query_chunks(
    project_id: str,
    data_dir: Path,
    query_embedding: list[float],
    top_k: int = 20,
    where: dict | None = None,
) -> list[dict]:
    col = _collection(project_id, data_dir)
    count = col.count()
    if count == 0:
        return []
    kwargs: dict = dict(
        query_embeddings=[query_embedding],
        n_results=min(top_k, count),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where
    result = col.query(**kwargs)
    return [
        {
            "id": result["ids"][0][i],
            "text": result["documents"][0][i],
            "metadata": result["metadatas"][0][i],
            "distance": result["distances"][0][i],
        }
        for i in range(len(result["ids"][0]))
    ]


def delete_project_collection(project_id: str, data_dir: Path) -> None:
    client = chromadb.PersistentClient(
        path=str(data_dir / "kb_chroma"),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(f"kb_{project_id}")
    except Exception:
        pass
