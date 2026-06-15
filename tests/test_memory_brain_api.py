# tests/test_memory_brain_api.py
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from sentinel.memory import MemoryStore
from sentinel.web import app as web_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    # Point app's default stores at an isolated DB so each test is hermetic.
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    # Ensure schema is initialised (entity_source_config + crawl_jobs tables).
    MemoryStore(tmp_path / "sentinel.db")
    return TestClient(web_app.app)


def test_get_entity_source_config_returns_empty_defaults(client):
    resp = client.get("/api/memory/source-config/acme-corp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity"] == "acme corp"
    assert data["priority"] == "medium"


def test_post_entity_source_config_saves(client):
    payload = {
        "priority": "high",
        "website_url": "https://acme.com",
        "email_filter": "from:acme.com",
        "sources_enabled": ["website", "email"],
    }
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    get_resp = client.get("/api/memory/source-config/acme-corp")
    data = get_resp.json()
    assert data["priority"] == "high"
    assert data["website_url"] == "https://acme.com"


def test_post_rejects_invalid_email_filter(client):
    payload = {"email_filter": "'; DROP TABLE memory_entries; --"}
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_post_rejects_http_scheme_other_than_http_https(client):
    for bad_url in ("ftp://acme.com", "file:///etc/passwd", "javascript:alert(1)"):
        resp = client.post(
            "/api/memory/source-config/acme-corp",
            content=json.dumps({"website_url": bad_url}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400, f"expected 400 for {bad_url!r}"


def test_post_rejects_loopback_url(client):
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps({"website_url": "http://127.0.0.1/admin"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_post_rejects_private_range_url(client):
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps({"website_url": "http://192.168.1.1/secret"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_post_rejects_link_local_url(client):
    # AWS metadata endpoint SSRF classic
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps({"website_url": "http://169.254.169.254/latest/meta-data/"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_post_rejects_unresolvable_hostname(client):
    resp = client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps({"website_url": "https://this.hostname.does.not.exist.invalid/"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_post_rejects_if_any_record_is_internal(client):
    # Mock getaddrinfo to return both an external and an internal record
    # (DNS rebinding simulation — one round-robin entry is internal)
    import socket as _socket
    import unittest.mock as _mock
    from sentinel.web.render import memory_config as mc

    fake_records = [
        (2, 1, 6, "", ("93.184.216.34", 0)),   # external (example.com)
        (2, 1, 6, "", ("192.168.1.100", 0)),    # internal — must be rejected
    ]
    with _mock.patch.object(mc.socket, "getaddrinfo", return_value=fake_records):
        resp = client.post(
            "/api/memory/source-config/acme-corp",
            content=json.dumps({"website_url": "https://sneaky-rebind.example.com/"}),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400


def test_post_crawl_now_enqueues_job(client):
    # First configure
    client.post(
        "/api/memory/source-config/acme-corp",
        content=json.dumps({"website_url": "https://acme.com", "sources_enabled": ["website"]}),
        headers={"Content-Type": "application/json"},
    )
    resp = client.post("/api/memory/crawl-now/acme-corp")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enqueued"] >= 1
