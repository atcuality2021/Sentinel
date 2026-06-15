from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from sentinel.memory import MemoryStore
from sentinel.memory.schema import utcnow
from sentinel.memory.scheduler import CrawlScheduler, PRIORITY_INTERVALS


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "sentinel.db"
    MemoryStore(path)
    return path


def _insert_config(db: Path, entity: str, priority: str = "medium",
                   sources: list[str] | None = None, **kwargs):
    sources = sources or ["website"]
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO entity_source_config "
            "(entity, priority, sources_enabled, updated_at, website_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (entity, priority, json.dumps(sources), utcnow().isoformat(),
             kwargs.get("website_url", "https://example.com")),
        )
        conn.commit()


def _pending_jobs(db: Path, entity: str) -> list[dict]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(
            "SELECT * FROM crawl_jobs WHERE entity=? AND status='pending'", (entity,)
        ).fetchall()]


def test_priority_intervals_keys():
    for p in ("high", "medium", "low"):
        assert p in PRIORITY_INTERVALS
        for src in ("website", "email", "youtube", "social"):
            assert src in PRIORITY_INTERVALS[p]


def test_tick_enqueues_overdue_source(db):
    _insert_config(db, "acme corp", priority="medium", sources=["website"])
    sched = CrawlScheduler(db)
    sched.tick()
    jobs = _pending_jobs(db, "acme corp")
    assert len(jobs) == 1
    assert jobs[0]["source_type"] == "website"


def test_tick_is_idempotent(db):
    _insert_config(db, "acme corp", sources=["website"])
    sched = CrawlScheduler(db)
    sched.tick()
    sched.tick()  # second tick in same hour window must not add a duplicate
    assert len(_pending_jobs(db, "acme corp")) == 1


def test_tick_does_not_enqueue_when_job_already_running(db):
    _insert_config(db, "acme corp", sources=["website"])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at) "
            "VALUES (?, 'acme corp', 'website', 'running', 5, ?)",
            (uuid4().hex, utcnow().isoformat()),
        )
        conn.commit()
    sched = CrawlScheduler(db)
    sched.tick()
    jobs = _pending_jobs(db, "acme corp")
    assert len(jobs) == 0  # already running, no new pending


def test_force_enqueue_ignores_interval(db):
    _insert_config(db, "acme corp", priority="low", sources=["website"])
    # Mark website as done very recently (not due yet)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at, done_at) "
            "VALUES (?, 'acme corp', 'website', 'done', 5, ?, ?)",
            (uuid4().hex, utcnow().isoformat(), utcnow().isoformat()),
        )
        conn.commit()
    sched = CrawlScheduler(db)
    sched.force_enqueue("acme corp")
    jobs = _pending_jobs(db, "acme corp")
    assert len(jobs) == 1
    assert jobs[0]["priority"] == 10  # HIGH priority


def test_high_priority_config_yields_high_priority_job(db):
    _insert_config(db, "acme corp", priority="high", sources=["website"])
    sched = CrawlScheduler(db)
    sched.tick()
    jobs = _pending_jobs(db, "acme corp")
    assert jobs[0]["priority"] == 10


def test_medium_priority_config_yields_medium_priority_job(db):
    _insert_config(db, "acme corp", priority="medium", sources=["website"])
    sched = CrawlScheduler(db)
    sched.tick()
    jobs = _pending_jobs(db, "acme corp")
    assert jobs[0]["priority"] == 5


def test_force_enqueue_does_not_delete_running_job(db):
    """force_enqueue must not orphan an in-flight worker."""
    _insert_config(db, "acme corp", priority="high", sources=["website"])
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at, claimed_at) "
            "VALUES (?, 'acme corp', 'website', 'running', 10, ?, ?)",
            (uuid4().hex, utcnow().isoformat(), utcnow().isoformat()),
        )
        conn.commit()
    sched = CrawlScheduler(db)
    sched.force_enqueue("acme corp")
    with sqlite3.connect(db) as conn:
        running = conn.execute(
            "SELECT * FROM crawl_jobs WHERE entity='acme corp' AND status='running'"
        ).fetchall()
    assert len(running) == 1  # running job must still exist
