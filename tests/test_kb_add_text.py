"""Tests for KBManager.add_text and RunStore.get — artifact-to-KB reuse flow."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentinel.kb.schema import CrawlStatus, SourceType
from sentinel.memory.schema import RunRecord
from sentinel.memory.store import RunStore


# --------------------------------------------------------------------------- #
# RunStore.get
# --------------------------------------------------------------------------- #

def test_run_store_get_returns_none_for_missing(tmp_path):
    store = RunStore(tmp_path / "test.db")
    assert store.get("nonexistent-id") is None


def test_run_store_get_returns_saved_record(tmp_path):
    store = RunStore(tmp_path / "test.db")
    rec = RunRecord(
        entity="acme corp",
        target="Research Acme Corp",
        mode="competitor",
        backend="vllm",
        kind="market",
        finding_texts=["Acme is a B2B SaaS company.", "Acme raised $50M in Series B."],
        project_id="proj-123",
    )
    store.save(rec)
    fetched = store.get(rec.id)
    assert fetched is not None
    assert fetched.id == rec.id
    assert fetched.entity == "acme corp"
    assert fetched.finding_texts == ["Acme is a B2B SaaS company.", "Acme raised $50M in Series B."]


def test_run_store_get_does_not_return_other_records(tmp_path):
    store = RunStore(tmp_path / "test.db")
    rec_a = RunRecord(entity="alpha", target="Alpha research", mode="competitor", backend="vllm")
    rec_b = RunRecord(entity="beta", target="Beta research", mode="competitor", backend="vllm")
    store.save(rec_a)
    store.save(rec_b)
    fetched = store.get(rec_a.id)
    assert fetched is not None
    assert fetched.entity == "alpha"


# --------------------------------------------------------------------------- #
# SourceType enum
# --------------------------------------------------------------------------- #

def test_source_type_artifact_value():
    assert SourceType.ARTIFACT.value == "artifact"


def test_source_type_artifact_is_str():
    assert isinstance(SourceType.ARTIFACT, str)


# --------------------------------------------------------------------------- #
# KBManager.add_text
# --------------------------------------------------------------------------- #

def _make_manager(tmp_path: Path):
    from sentinel.kb.manager import KBManager
    return KBManager(tmp_path)


def _patch_embed_and_upsert(monkeypatch):
    """Stub out the embedding + vector store so tests run without a live server."""
    import sentinel.kb.manager as mgr_mod

    monkeypatch.setattr(mgr_mod, "embed", lambda texts: [[0.1] * 8 for _ in texts])
    monkeypatch.setattr(
        mgr_mod,
        "upsert_chunks",
        lambda **kwargs: None,
    )


def test_add_text_indexes_non_empty_content(tmp_path, monkeypatch):
    _patch_embed_and_upsert(monkeypatch)
    manager = _make_manager(tmp_path)
    text = "Acme Corp is a market leader in B2B SaaS.\n\nThey raised $50M in 2024."
    source = manager.add_text("proj-1", text, "Acme research run")
    assert source.status == CrawlStatus.INDEXED
    assert source.chunk_count > 0
    assert source.source_type == SourceType.ARTIFACT
    assert source.url.startswith("artifact://")


def test_add_text_label_sanitised_in_url(tmp_path, monkeypatch):
    _patch_embed_and_upsert(monkeypatch)
    manager = _make_manager(tmp_path)
    source = manager.add_text("proj-1", "Some content here.", "Research objective with spaces")
    assert " " not in source.url


def test_add_text_url_truncated_to_80_chars(tmp_path, monkeypatch):
    _patch_embed_and_upsert(monkeypatch)
    manager = _make_manager(tmp_path)
    long_label = "x" * 200
    source = manager.add_text("proj-1", "content", long_label)
    # "artifact://" prefix + up to 80 chars of label
    assert len(source.url) <= len("artifact://") + 80


def test_add_text_empty_content_fails(tmp_path):
    manager = _make_manager(tmp_path)
    source = manager.add_text("proj-1", "   ", "empty label")
    assert source.status == CrawlStatus.FAILED
    assert source.chunk_count == 0
    assert source.error is not None


def test_add_text_embedding_failure_returns_failed_source(tmp_path, monkeypatch):
    import sentinel.kb.manager as mgr_mod

    monkeypatch.setattr(mgr_mod, "embed", MagicMock(side_effect=RuntimeError("embed server down")))
    monkeypatch.setattr(mgr_mod, "upsert_chunks", lambda **kwargs: None)

    manager = _make_manager(tmp_path)
    source = manager.add_text("proj-1", "Some research findings here.", "label")
    assert source.status == CrawlStatus.FAILED
    assert "embed server down" in (source.error or "")


def test_add_text_uses_artifact_source_type_by_default(tmp_path, monkeypatch):
    _patch_embed_and_upsert(monkeypatch)
    manager = _make_manager(tmp_path)
    source = manager.add_text("proj-1", "content for KB", "label")
    assert source.source_type == SourceType.ARTIFACT


def test_add_text_accepts_custom_source_type(tmp_path, monkeypatch):
    _patch_embed_and_upsert(monkeypatch)
    manager = _make_manager(tmp_path)
    source = manager.add_text("proj-1", "content", "label", source_type=SourceType.DOCUMENT)
    assert source.source_type == SourceType.DOCUMENT
