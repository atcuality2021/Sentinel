# src/sentinel/memory/worker.py
"""MemoryWorker — drains the crawl_jobs queue and writes findings to MemoryStore."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import timedelta
from pathlib import Path

from sentinel.memory import MemoryStore
from sentinel.memory.connectors.base import SourceFinding
from sentinel.memory.schema import DataBoundary, MemoryEntry, MemoryType, normalize_entity, utcnow

log = logging.getLogger(__name__)

_STALE_THRESHOLD = timedelta(minutes=10)
_POLL_INTERVAL_S = 30


class MemoryWorker:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._store = MemoryStore(db_path)

    def _reset_stale_jobs(self) -> None:
        cutoff = (utcnow() - _STALE_THRESHOLD).isoformat()
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status='pending', claimed_at=NULL "
                "WHERE status='running' AND claimed_at < ?",
                (cutoff,),
            )
            conn.commit()

    def _claim_job(self) -> dict | None:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, entity, source_type, priority FROM crawl_jobs "
                "WHERE status='pending' ORDER BY priority DESC, scheduled_at ASC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE crawl_jobs SET status='running', claimed_at=? WHERE id=?",
                (utcnow().isoformat(), row["id"]),
            )
            conn.commit()
        return dict(row)

    def _mark_done(self, job_id: str) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status='done', done_at=? WHERE id=?",
                (utcnow().isoformat(), job_id),
            )
            conn.commit()

    def _mark_failed(self, job_id: str, error: str) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status='failed', error=? WHERE id=?",
                (error[:500], job_id),
            )
            conn.commit()

    def _get_entity_config(self, entity: str) -> dict[str, object]:
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM entity_source_config WHERE entity=?", (entity,)
            ).fetchone()
        return dict(row) if row else {}

    async def _run_connector(
        self, source_type: str, entity: str, config: dict[str, object]
    ) -> list[SourceFinding]:
        from sentinel.memory.connectors import get_connector
        connector = get_connector(source_type)
        return await connector.fetch(entity, config)

    def _write_findings(self, entity: str, findings: list[SourceFinding]) -> None:
        for f in findings:
            # Defense-in-depth: email is always PRIVATE regardless of what the connector returned.
            boundary = DataBoundary.PRIVATE if f.source_type == "email" else f.boundary
            entry = MemoryEntry(
                entity=entity,
                boundary=boundary,
                memory_type=MemoryType.FINDING,
                content=f.text,
                source_label=f.source_label,
                source_url=f.source_url,
            )
            self._store.write(entry)

    async def _process_one_job(self) -> bool:
        self._reset_stale_jobs()
        job = self._claim_job()
        if not job:
            return False
        entity = normalize_entity(job["entity"])
        source_type = job["source_type"]
        config = self._get_entity_config(entity)
        try:
            findings = await self._run_connector(source_type, entity, config)
            self._write_findings(entity, findings)
            self._mark_done(job["id"])
            log.info("crawl done: %s/%s → %d findings", entity, source_type, len(findings))
        except Exception as exc:
            self._mark_failed(job["id"], str(exc))
            log.warning("crawl failed: %s/%s — %s", entity, source_type, exc)
        return True

    async def run_forever(self) -> None:
        log.info("sentinel-memory-worker started (db=%s)", self._path)
        while True:
            did_work = await self._process_one_job()
            if not did_work:
                await asyncio.sleep(_POLL_INTERVAL_S)
