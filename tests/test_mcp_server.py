"""SENTINEL-016 G-16 — MCP server mode: tests for the pure helper functions.

Tests target the _*_impl helpers directly so they run without an MCP transport
subprocess. The MCP tool registrations are thin wrappers that add only clamping
and delegation, so testing the helpers covers the business logic.
"""
from __future__ import annotations

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers — patch SENTINEL_DATA_DIR to a tmp_path DB for all tests
# ---------------------------------------------------------------------------

def _patch_data_dir(monkeypatch, tmp_path: Path) -> Path:
    db = tmp_path / "sentinel.db"
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    # Ensure the schema is initialised
    from sentinel.memory.store import _ensure_schema
    _ensure_schema(db)
    return db


# ---------------------------------------------------------------------------
# recall_memory
# ---------------------------------------------------------------------------

def test_recall_memory_returns_stored_findings(monkeypatch, tmp_path):
    """_recall_memory_impl returns entries written via MemoryStore.write()."""
    db = _patch_data_dir(monkeypatch, tmp_path)
    from sentinel.memory.store import MemoryStore
    from sentinel.memory.schema import MemoryEntry
    from sentinel.artifacts.schemas import Boundary
    store = MemoryStore(db)
    store.write(MemoryEntry(
        entity="biltiq ai",
        boundary=Boundary.PUBLIC,
        content="biltiq ai is a sovereign intelligence platform",
        source_label="test",
    ))

    # Patch _DATA_DIR in the server module so it points at our tmp DB
    import sentinel.mcp.server as srv
    monkeypatch.setattr(srv, "_DATA_DIR", tmp_path)

    results = srv._recall_memory_impl("biltiq ai", boundary="public", limit=10)
    assert len(results) == 1
    assert results[0]["entity"] == "biltiq ai"
    assert "sovereign" in results[0]["content"]
    assert results[0]["boundary"] == "public"


def test_recall_memory_unknown_entity_returns_empty(monkeypatch, tmp_path):
    """_recall_memory_impl returns [] for an entity with no stored findings."""
    _patch_data_dir(monkeypatch, tmp_path)
    import sentinel.mcp.server as srv
    monkeypatch.setattr(srv, "_DATA_DIR", tmp_path)
    assert srv._recall_memory_impl("unknown-entity-xyz") == []


# ---------------------------------------------------------------------------
# top_skills
# ---------------------------------------------------------------------------

def test_top_skills_returns_ranked_capabilities(monkeypatch, tmp_path):
    """_top_skills_impl returns capabilities sorted by avg_score desc."""
    db = _patch_data_dir(monkeypatch, tmp_path)
    from sentinel.memory.store import SkillCurationStore
    curation = SkillCurationStore(db)
    curation.record_outcome("self_profile", 0.9)
    curation.record_outcome("competitor", 0.4)

    import sentinel.mcp.server as srv
    monkeypatch.setattr(srv, "_DATA_DIR", tmp_path)

    top = srv._top_skills_impl(limit=5)
    assert len(top) == 2
    assert top[0]["capability"] == "self_profile"
    assert top[0]["avg_score"] > top[1]["avg_score"]


def test_list_recent_runs_limit_respected(monkeypatch, tmp_path):
    """_list_recent_runs_impl returns at most *limit* runs."""
    db = _patch_data_dir(monkeypatch, tmp_path)
    from sentinel.memory.store import RunStore
    from sentinel.memory.schema import RunRecord
    rs = RunStore(db)
    for i in range(4):
        rs.save(RunRecord(
            entity="biltiq ai", target="BiltIQ AI", mode="full",
            backend="gemma12", public=1, private=0,
        ))

    import sentinel.mcp.server as srv
    monkeypatch.setattr(srv, "_DATA_DIR", tmp_path)

    runs = srv._list_recent_runs_impl("biltiq ai", limit=2)
    assert len(runs) == 2
    assert runs[0]["entity"] == "biltiq ai"
