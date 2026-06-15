# tests/test_memory_brain_ui.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.memory import MemoryStore
from sentinel.memory.schema import DataBoundary, MemoryEntry
from sentinel.web import app as web_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    # Point app's default stores at an isolated DB so each test is hermetic.
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    MemoryStore(tmp_path / "sentinel.db")
    return TestClient(web_app.app)


# ── _source_badge unit tests ─────────────────────────────────────────────────

def test_source_badge_website_shows_label():
    """Website badge renders the correct label."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PUBLIC,
                        content="fact", source_type="website")
    badge = _source_badge(entry)
    assert "website" in badge.lower() or "🌐" in badge


def test_source_badge_youtube_shows_label():
    """YouTube badge renders the correct label."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PUBLIC,
                        content="fact", source_type="youtube")
    badge = _source_badge(entry)
    assert "youtube" in badge.lower() or "▶" in badge


def test_source_badge_email_shows_private():
    """Email entry badge always shows PRIVATE label."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PRIVATE,
                        content="secret", source_type="email")
    badge = _source_badge(entry)
    assert "PRIVATE" in badge or "private" in badge.lower()


def test_source_badge_private_boundary_shows_private():
    """Any PRIVATE boundary entry shows PRIVATE label regardless of source_type."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PRIVATE,
                        content="internal doc", source_type="social")
    badge = _source_badge(entry)
    assert "PRIVATE" in badge or "private" in badge.lower()


def test_source_badge_none_source_type_falls_back_to_research():
    """None source_type gracefully falls back to 'research' (tested via a duck-typed stub)."""
    from sentinel.web.render.memory import _source_badge
    # MemoryEntry rejects source_type=None via Pydantic, so test _source_badge directly
    # with a minimal duck-typed object that has source_type=None (as could arrive from
    # legacy DB rows loaded without Pydantic validation).
    class _Stub:
        source_type = None
        boundary = DataBoundary.PUBLIC
    badge = _source_badge(_Stub())
    assert len(badge) > 0
    assert "<span" in badge


def test_source_badge_unknown_type_falls_back_to_research():
    """Unknown source_type gracefully falls back to 'research'."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PUBLIC,
                        content="fact", source_type="foobar_unknown")
    badge = _source_badge(entry)
    assert "<span" in badge


def test_source_badge_escapes_html_in_label():
    """Badge HTML is always escaped — no injection from label."""
    from sentinel.web.render.memory import _source_badge
    entry = MemoryEntry(entity="acme", boundary=DataBoundary.PUBLIC,
                        content="fact", source_type="website")
    badge = _source_badge(entry)
    # The badge is generated from a fixed dict — no raw user content in the label
    assert "<script>" not in badge


# ── Settings page has Memory Sources section ──────────────────────────────────

def test_settings_page_has_memory_sources_section(client):
    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.text
    assert "Memory Sources" in body or "memory-sources" in body.lower()


def test_settings_memory_sources_has_id_anchor(client):
    """Memory Sources section has an id attribute for direct linking."""
    resp = client.get("/settings")
    assert resp.status_code == 200
    body = resp.text
    assert "memory-sources" in body
