# tests/test_memory_brain_worker.py
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from sentinel.memory import MemoryStore
from sentinel.memory.connectors.base import SourceFinding
from sentinel.memory.schema import DataBoundary, utcnow
from sentinel.memory.worker import MemoryWorker


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "sentinel.db"
    MemoryStore(path)
    return path


def _insert_pending_job(db: Path, entity: str = "acme corp",
                         source_type: str = "website", priority: int = 5) -> str:
    job_id = uuid4().hex
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (job_id, entity, source_type, priority, utcnow().isoformat()),
        )
        conn.commit()
    return job_id


def _job_status(db: Path, job_id: str) -> str:
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT status FROM crawl_jobs WHERE id=?", (job_id,)).fetchone()
        return row[0] if row else "missing"


@pytest.mark.asyncio
async def test_worker_claims_and_completes_job(db):
    job_id = _insert_pending_job(db, "acme corp", "website")
    findings = [
        SourceFinding(text="Acme launched v2.", boundary=DataBoundary.PUBLIC,
                      source_type="website", source_url="https://acme.com",
                      source_label="Acme website", trust_score=0.8)
    ]
    worker = MemoryWorker(db)
    with patch.object(worker, "_run_connector", new=AsyncMock(return_value=findings)):
        await worker._process_one_job()
    assert _job_status(db, job_id) == "done"


@pytest.mark.asyncio
async def test_worker_marks_job_failed_on_connector_error(db):
    job_id = _insert_pending_job(db, "acme corp", "website")
    worker = MemoryWorker(db)
    with patch.object(worker, "_run_connector", new=AsyncMock(side_effect=RuntimeError("network error"))):
        await worker._process_one_job()
    assert _job_status(db, job_id) == "failed"


@pytest.mark.asyncio
async def test_worker_writes_findings_to_memory(db):
    _insert_pending_job(db, "acme corp", "website")
    findings = [
        SourceFinding(text="Acme Corp HQ is in Mumbai.", boundary=DataBoundary.PUBLIC,
                      source_type="website", source_url="https://acme.com",
                      source_label="Acme website", trust_score=0.8)
    ]
    worker = MemoryWorker(db)
    with patch.object(worker, "_run_connector", new=AsyncMock(return_value=findings)):
        await worker._process_one_job()
    mem = MemoryStore(db)
    recalled = mem.recall("acme corp", [DataBoundary.PUBLIC])
    assert any("Mumbai" in e.content for e in recalled)


@pytest.mark.asyncio
async def test_email_findings_always_private(db):
    _insert_pending_job(db, "acme corp", "email")
    findings = [
        SourceFinding(text="Email: deal signed for ₹5Cr.", boundary=DataBoundary.PUBLIC,
                      source_type="email", source_url="gmail://",
                      source_label="Email", trust_score=0.95)
        # NOTE: connector returned PUBLIC — worker must override to PRIVATE
    ]
    worker = MemoryWorker(db)
    with patch.object(worker, "_run_connector", new=AsyncMock(return_value=findings)):
        await worker._process_one_job()
    mem = MemoryStore(db)
    # Must NOT appear in public recall
    public = mem.recall("acme corp", [DataBoundary.PUBLIC])
    assert not any("₹5Cr" in e.content for e in public)
    # MUST appear in private recall
    private = mem.recall("acme corp", [DataBoundary.PRIVATE])
    assert any("₹5Cr" in e.content for e in private)


@pytest.mark.asyncio
async def test_stale_running_jobs_reset_to_pending(db):
    job_id = uuid4().hex
    stale_time = (utcnow() - timedelta(minutes=15)).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, "
            "scheduled_at, claimed_at) VALUES (?, 'acme', 'website', 'running', 5, ?, ?)",
            (job_id, stale_time, stale_time),
        )
        conn.commit()
    worker = MemoryWorker(db)
    worker._reset_stale_jobs()
    assert _job_status(db, job_id) == "pending"
