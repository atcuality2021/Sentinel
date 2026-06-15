# tests/test_memory_brain_recall.py
from __future__ import annotations

import pytest

from sentinel.memory import MemoryStore
from sentinel.memory.schema import DataBoundary, MemoryEntry


@pytest.fixture
def mem(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "sentinel.db")


def _entry(entity, boundary, content, *, source_type="research", persona_id=None) -> MemoryEntry:
    return MemoryEntry(
        entity=entity, boundary=boundary, content=content,
        source_type=source_type, persona_id=persona_id,
    )


def test_recall_without_persona_id_unchanged(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Acme fact A"))
    result = mem.recall("acme", [DataBoundary.PUBLIC])
    assert len(result) == 1
    assert "Acme fact A" in result[0].content


def test_persona_id_none_returns_only_shared_facts(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Shared fact"))
    mem.write(_entry("acme", DataBoundary.PRIVATE, "Analyst note", persona_id="analyst"))
    result = mem.recall("acme", [DataBoundary.PUBLIC, DataBoundary.PRIVATE], persona_id=None)
    contents = [e.content for e in result]
    assert "Shared fact" in contents
    assert "Analyst note" not in contents


def test_persona_recall_includes_shared_and_persona_facts(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Shared fact"))
    mem.write(_entry("acme", DataBoundary.PRIVATE, "Analyst note", persona_id="analyst"))
    result = mem.recall("acme", [DataBoundary.PUBLIC, DataBoundary.PRIVATE], persona_id="analyst")
    contents = [e.content for e in result]
    assert "Shared fact" in contents
    assert "Analyst note" in contents


def test_persona_recall_does_not_leak_other_persona_facts(mem):
    mem.write(_entry("acme", DataBoundary.PRIVATE, "Sales note", persona_id="sales"))
    result = mem.recall("acme", [DataBoundary.PRIVATE], persona_id="analyst")
    assert not any("Sales note" in e.content for e in result)


def test_boundary_public_never_returns_private_even_with_persona(mem):
    mem.write(_entry("acme", DataBoundary.PRIVATE, "Secret", persona_id="analyst"))
    result = mem.recall("acme", [DataBoundary.PUBLIC], persona_id="analyst")
    assert not any("Secret" in e.content for e in result)


def test_persona_wins_on_content_hash_collision(mem):
    # Same fact from research (shared) and from analyst persona — persona version returned once
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Acme HQ in Mumbai.", source_type="research"))
    mem.write(_entry("acme", DataBoundary.PRIVATE, "Acme HQ in Mumbai.", persona_id="analyst"))
    result = mem.recall("acme", [DataBoundary.PUBLIC, DataBoundary.PRIVATE], persona_id="analyst")
    matching = [e for e in result if "Mumbai" in e.content]
    assert len(matching) == 1  # deduped — only one copy


def test_source_type_stored_and_readable(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Website fact", source_type="website"))
    result = mem.recall("acme", [DataBoundary.PUBLIC])
    assert result[0].source_type == "website"
