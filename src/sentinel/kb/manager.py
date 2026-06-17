from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable

from .bm25_index import BM25Index
from .chunker import chunk_text
from .crawler import crawl_website
from .embedder import embed
from .schema import CrawlStatus, KBChunk, KBSource, SourceType
from .vector_store import delete_project_collection, upsert_chunks

_EMBED_BATCH = 32


def _bm25_path(project_id: str, data_dir: Path) -> Path:
    return data_dir / "kb_bm25" / f"{project_id}.json"


class KBManager:
    """Orchestrates the full crawl → chunk → embed → dual-index pipeline."""

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)

    async def add_source(
        self,
        project_id: str,
        url: str,
        source_type: SourceType = SourceType.WEB,
        on_progress: Callable[[str], None] | None = None,
    ) -> KBSource:
        source = KBSource(project_id=project_id, url=url, source_type=source_type)
        source.status = CrawlStatus.CRAWLING

        def _log(msg: str) -> None:
            if on_progress:
                on_progress(msg)

        _log(f"Crawling {url} …")
        try:
            pages = await crawl_website(url, source_type=source_type.value)
        except Exception as exc:
            source.status = CrawlStatus.FAILED
            source.error = str(exc)
            return source

        if not pages:
            source.status = CrawlStatus.FAILED
            source.error = "No content extracted from URL"
            return source

        _log(f"Crawled {len(pages)} page(s). Chunking …")

        chunks: list[KBChunk] = []
        for page in pages:
            for fragment in chunk_text(page.text, chunk_size=512, chunk_overlap=64):
                chunks.append(KBChunk(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    source_id=source.id,
                    url=page.url,
                    title=page.title,
                    text=fragment,
                    source_type=source_type.value,
                ))

        _log(f"{len(chunks)} chunks. Embedding in batches of {_EMBED_BATCH} …")

        bm25 = BM25Index(_bm25_path(project_id, self._data_dir))

        for i in range(0, len(chunks), _EMBED_BATCH):
            batch = chunks[i : i + _EMBED_BATCH]
            try:
                vecs = embed([c.text for c in batch])
            except Exception as exc:
                source.status = CrawlStatus.FAILED
                source.error = f"Embedding failed at batch {i}: {exc}"
                return source

            upsert_chunks(
                project_id=project_id,
                data_dir=self._data_dir,
                ids=[c.id for c in batch],
                embeddings=vecs,
                documents=[c.text for c in batch],
                metadatas=[{
                    "url": c.url,
                    "title": c.title,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                } for c in batch],
            )
            for c in batch:
                bm25.add(c.id, c.text)

            _log(f"  Indexed {min(i + _EMBED_BATCH, len(chunks))}/{len(chunks)} chunks …")

        bm25.save()
        source.chunk_count = len(chunks)
        source.status = CrawlStatus.INDEXED
        _log(f"Done. {len(chunks)} chunks from {len(pages)} page(s) indexed.")
        return source

    def add_text(
        self,
        project_id: str,
        text: str,
        label: str,
        source_type: SourceType = SourceType.ARTIFACT,
    ) -> KBSource:
        """Ingest raw text (e.g. a research artifact) directly — no crawl step needed."""
        source = KBSource(
            project_id=project_id,
            url=f"artifact://{label.replace(' ', '_')[:80]}",
            source_type=source_type,
        )
        if not text.strip():
            source.status = CrawlStatus.FAILED
            source.error = "Empty text — nothing to index"
            return source

        chunks: list[KBChunk] = []
        for fragment in chunk_text(text, chunk_size=512, chunk_overlap=64):
            chunks.append(KBChunk(
                id=str(uuid.uuid4()),
                project_id=project_id,
                source_id=source.id,
                url=source.url,
                title=label,
                text=fragment,
                source_type=source_type.value,
            ))

        bm25 = BM25Index(_bm25_path(project_id, self._data_dir))
        for i in range(0, len(chunks), _EMBED_BATCH):
            batch = chunks[i : i + _EMBED_BATCH]
            try:
                vecs = embed([c.text for c in batch])
            except Exception as exc:
                source.status = CrawlStatus.FAILED
                source.error = f"Embedding failed at batch {i}: {exc}"
                return source
            upsert_chunks(
                project_id=project_id,
                data_dir=self._data_dir,
                ids=[c.id for c in batch],
                embeddings=vecs,
                documents=[c.text for c in batch],
                metadatas=[{
                    "url": c.url,
                    "title": c.title,
                    "source_type": c.source_type,
                    "source_id": c.source_id,
                } for c in batch],
            )
            for c in batch:
                bm25.add(c.id, c.text)
        bm25.save()
        source.chunk_count = len(chunks)
        source.status = CrawlStatus.INDEXED
        return source

    def delete_project(self, project_id: str) -> None:
        """Remove all KB data for a project (ChromaDB + BM25 index)."""
        delete_project_collection(project_id, self._data_dir)
        bm25_file = _bm25_path(project_id, self._data_dir)
        if bm25_file.exists():
            bm25_file.unlink()
