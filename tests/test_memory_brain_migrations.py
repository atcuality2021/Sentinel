from __future__ import annotations
import sqlite3
from pathlib import Path

import pytest

from sentinel.memory import MemoryStore


@pytest.fixture
def db(tmp_path) -> Path:
    path = tmp_path / "sentinel.db"
    MemoryStore(path)  # triggers _ensure_schema
    return path


def _cols(db: Path, table: str) -> set[str]:
    with sqlite3.connect(db) as conn:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_memory_entries_has_source_type(db):
    assert "source_type" in _cols(db, "memory_entries")


def test_memory_entries_has_persona_id(db):
    assert "persona_id" in _cols(db, "memory_entries")


def test_crawl_jobs_table_exists(db):
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "crawl_jobs" in tables


def test_entity_source_config_table_exists(db):
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "entity_source_config" in tables


def test_crawl_jobs_columns(db):
    cols = _cols(db, "crawl_jobs")
    for col in ("id", "entity", "project_id", "source_type", "status", "priority",
                "scheduled_at", "claimed_at", "done_at", "error"):
        assert col in cols, f"missing column: {col}"


def test_entity_source_config_columns(db):
    cols = _cols(db, "entity_source_config")
    for col in ("entity", "priority", "website_url", "youtube_channel",
                "social_handles", "email_filter", "sources_enabled", "updated_at"):
        assert col in cols, f"missing column: {col}"


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "sentinel.db"
    MemoryStore(path)
    MemoryStore(path)  # second open must not raise
