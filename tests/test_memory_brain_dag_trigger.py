# tests/test_memory_brain_dag_trigger.py
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sentinel.memory import MemoryStore
from sentinel.memory.schema import utcnow


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "sentinel.db"
    MemoryStore(path)
    return path


def _insert_config(db: Path, entity: str):
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO entity_source_config "
            "(entity, priority, sources_enabled, updated_at) "
            "VALUES (?, 'medium', '[\"website\"]', ?)",
            (entity, utcnow().isoformat()),
        )
        conn.commit()


def _pending_jobs(db: Path, entity: str) -> list:
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT * FROM crawl_jobs WHERE entity=? AND status='pending'", (entity,)
        ).fetchall()


def test_maybe_trigger_enqueues_for_configured_entity(db):
    _insert_config(db, "acme corp")
    from sentinel.agent.dag import _maybe_trigger_memory_crawl
    _maybe_trigger_memory_crawl("acme corp", db_path=db)
    assert len(_pending_jobs(db, "acme corp")) == 1


def test_maybe_trigger_skips_unconfigured_entity(db):
    from sentinel.agent.dag import _maybe_trigger_memory_crawl
    _maybe_trigger_memory_crawl("unknown entity", db_path=db)
    assert len(_pending_jobs(db, "unknown entity")) == 0


def test_maybe_trigger_is_fail_soft(db):
    from sentinel.agent.dag import _maybe_trigger_memory_crawl
    # Should not raise even if DB path is wrong
    _maybe_trigger_memory_crawl("acme corp", db_path=Path("/nonexistent/path.db"))
