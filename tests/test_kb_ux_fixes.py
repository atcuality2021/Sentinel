"""Tests for KB UX fixes: friendly error messages + retry route."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sentinel.web.render import _kb_error_friendly


# ── _kb_error_friendly ────────────────────────────────────────────────────────

def test_empty_error_returns_empty():
    assert _kb_error_friendly("") == ""
    assert _kb_error_friendly(None) == ""


def test_401_unauthorized_returns_friendly():
    msg = _kb_error_friendly("Embedding failed at batch 0: Error code: 401 · {'error': 'Unauthorized'}")
    assert "VLLM_API_KEY" in msg
    assert "401" not in msg  # raw code replaced


def test_401_case_insensitive():
    msg = _kb_error_friendly("error code: 401 unauthorized")
    assert "API key" in msg.lower() or "vllm" in msg.lower()


def test_403_forbidden():
    msg = _kb_error_friendly("403 Forbidden from embed server")
    assert "denied" in msg.lower() or "forbidden" in msg.lower()


def test_404_endpoint():
    msg = _kb_error_friendly("404 Not Found — /embed endpoint missing")
    assert "endpoint" in msg.lower() or "EMBED_API_BASE" in msg


def test_connection_refused():
    msg = _kb_error_friendly("Connection refused to localhost:8001")
    assert "reach" in msg.lower() or "running" in msg.lower()


def test_timeout():
    msg = _kb_error_friendly("Read timeout after 30s")
    assert "timed out" in msg.lower() or "timeout" in msg.lower()


def test_empty_content():
    msg = _kb_error_friendly("Empty text — nothing to index")
    assert "content" in msg.lower() or "index" in msg.lower()


def test_unknown_error_truncated_to_120():
    raw = "x" * 200
    msg = _kb_error_friendly(raw)
    assert len(msg) <= 120


def test_unknown_error_passthrough():
    raw = "Some unusual internal error message"
    msg = _kb_error_friendly(raw)
    assert len(msg) > 0


# ── KB retry route ────────────────────────────────────────────────────────────

@pytest.fixture
def app_client():
    from fastapi.testclient import TestClient
    from sentinel.web.app import app
    return TestClient(app, raise_server_exceptions=False)


def test_retry_unknown_source_redirects_with_error(app_client):
    resp = app_client.post(
        "/projects/nonexistent_proj/kb/sources/nonexistent_src/retry",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]


def test_retry_artifact_source_blocked(app_client):
    fake_src = {
        "id": "src1",
        "project_id": "proj1",
        "url": "artifact://Research_Crayon_competitive",
        "source_type": "artifact",
        "status": "failed",
        "chunk_count": 0,
        "error": "Embedding failed",
    }
    with patch("sentinel.web.app.KBStore") as mock_store_cls:
        mock_store = MagicMock()
        mock_store.get.return_value = fake_src
        mock_store_cls.return_value = mock_store

        resp = app_client.post(
            "/projects/proj1/kb/sources/src1/retry",
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "cannot" in resp.headers["location"].lower() or "err=" in resp.headers["location"]


def test_retry_web_source_queues_crawl(app_client):
    fake_src = {
        "id": "src2",
        "project_id": "proj1",
        "url": "https://example.com",
        "source_type": "web",
        "status": "failed",
        "chunk_count": 0,
        "error": "401 Unauthorized",
    }
    with (
        patch("sentinel.web.app.KBStore") as mock_store_cls,
        patch("sentinel.web.app.KBManager"),
    ):
        mock_store = MagicMock()
        mock_store.get.return_value = fake_src
        mock_store_cls.return_value = mock_store

        resp = app_client.post(
            "/projects/proj1/kb/sources/src2/retry",
            follow_redirects=False,
        )

    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert "ok=" in loc or "started" in loc.lower()
    # Status reset to pending before background task fires
    mock_store.update_status.assert_called_once_with("src2", "pending", 0, None)
