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
