# tests/test_e2e_memory_brain.py
"""
End-to-end test for the Self-Driving Memory Brain feature.

Flow under test:
  1. Configure entity via POST /api/memory/source-config/<entity>
  2. Trigger crawl via POST /api/memory/crawl-now/<entity>
  3. Worker claims + processes job (connector mocked — no live MCPs needed)
  4. recall() returns the written findings
  5. Email findings are PRIVATE and never appear in PUBLIC recall
  6. Persona recall merges shared + private facts correctly
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from sentinel.memory import MemoryStore
from sentinel.memory.connectors.base import SourceFinding
from sentinel.memory.schema import DataBoundary, MemoryEntry, utcnow
from sentinel.memory.worker import MemoryWorker
from sentinel.web import app as web_app


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path) -> Path:
    path = tmp_path / "sentinel.db"
    MemoryStore(path)           # initialise schema
    return path


@pytest.fixture
def client(db_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(db_path.parent))
    return TestClient(web_app.app)


@pytest.fixture
def store(db_path) -> MemoryStore:
    return MemoryStore(db_path)


# ── helpers ───────────────────────────────────────────────────────────────────

def _pending_jobs(db_path: Path, entity: str) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM crawl_jobs WHERE entity=? AND status='pending'", (entity,)
        ).fetchall()
    return [dict(r) for r in rows]


def _all_jobs(db_path: Path) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT entity, source_type, status FROM crawl_jobs").fetchall()
    return [dict(r) for r in rows]


# ── tests ─────────────────────────────────────────────────────────────────────

class TestEntitySourceConfigAPI:
    """API routes: configure + crawl-now."""

    def test_get_returns_defaults_for_unconfigured_entity(self, client):
        resp = client.get("/api/memory/source-config/biltiq-ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity"] == "biltiq ai"
        assert data["priority"] == "medium"
        assert data["website_url"] == ""

    def test_post_saves_config_and_get_reflects_it(self, client):
        payload = {
            "priority": "high",
            "website_url": "https://biltiq.ai",
            "email_filter": "from:biltiq.ai",
            "sources_enabled": ["website", "email"],
        }
        resp = client.post(
            "/api/memory/source-config/biltiq-ai",
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200

        data = client.get("/api/memory/source-config/biltiq-ai").json()
        assert data["priority"] == "high"
        assert data["website_url"] == "https://biltiq.ai"
        assert "email" in data["sources_enabled"]

    def test_post_rejects_internal_website_url(self, client):
        for bad in ("http://127.0.0.1/", "http://169.254.169.254/", "ftp://biltiq.ai"):
            resp = client.post(
                "/api/memory/source-config/biltiq-ai",
                content=json.dumps({"website_url": bad}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status_code == 400, f"expected 400 for {bad!r}"

    def test_post_rejects_sql_injection_in_email_filter(self, client):
        resp = client.post(
            "/api/memory/source-config/biltiq-ai",
            content=json.dumps({"email_filter": "'; DROP TABLE crawl_jobs; --"}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_crawl_now_enqueues_job_after_configure(self, client, db_path):
        # configure first so force_enqueue knows about this entity
        client.post(
            "/api/memory/source-config/biltiq-ai",
            content=json.dumps({
                "website_url": "https://biltiq.ai",
                "sources_enabled": ["website"],
            }),
            headers={"Content-Type": "application/json"},
        )
        resp = client.post("/api/memory/crawl-now/biltiq-ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enqueued"] >= 1
        assert data["entity"] == "biltiq ai"

        jobs = _pending_jobs(db_path, "biltiq ai")
        assert len(jobs) >= 1
        assert jobs[0]["source_type"] == "website"


class TestWorkerProcessesJob:
    """Worker: claim → connector → write → mark done."""

    @pytest.mark.asyncio
    async def test_worker_writes_public_finding_to_memory(self, db_path, store):
        # Seed a pending job directly
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO entity_source_config "
                "(entity, priority, website_url, sources_enabled, updated_at) "
                "VALUES ('biltiq ai', 'high', 'https://biltiq.ai', '[\"website\"]', ?)",
                (utcnow().isoformat(),),
            )
            conn.execute(
                "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at) "
                "VALUES ('job-001', 'biltiq ai', 'website', 'pending', 10, ?)",
                (utcnow().isoformat(),),
            )
            conn.commit()

        findings = [
            SourceFinding(
                text="BiltIQ AI provides B2B research automation.",
                boundary=DataBoundary.PUBLIC,
                source_type="website",
                source_url="https://biltiq.ai",
                source_label="BiltIQ website",
                trust_score=0.8,
            )
        ]

        worker = MemoryWorker(db_path)
        with patch.object(worker, "_run_connector", new=AsyncMock(return_value=findings)):
            did_work = await worker._process_one_job()

        assert did_work is True

        recalled = store.recall("biltiq ai", [DataBoundary.PUBLIC])
        assert any("B2B research automation" in e.content for e in recalled)

    @pytest.mark.asyncio
    async def test_email_findings_never_appear_in_public_recall(self, db_path, store):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO entity_source_config "
                "(entity, priority, email_filter, sources_enabled, updated_at) "
                "VALUES ('biltiq ai', 'high', 'from:biltiq.ai', '[\"email\"]', ?)",
                (utcnow().isoformat(),),
            )
            conn.execute(
                "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at) "
                "VALUES ('job-002', 'biltiq ai', 'email', 'pending', 10, ?)",
                (utcnow().isoformat(),),
            )
            conn.commit()

        # Connector returns PUBLIC — worker must override to PRIVATE
        secret_findings = [
            SourceFinding(
                text="BiltIQ closing ₹5Cr deal with TCS next week.",
                boundary=DataBoundary.PUBLIC,  # intentionally wrong — worker must fix this
                source_type="email",
                source_url="gmail://",
                source_label="Email",
                trust_score=0.95,
            )
        ]

        worker = MemoryWorker(db_path)
        with patch.object(worker, "_run_connector", new=AsyncMock(return_value=secret_findings)):
            await worker._process_one_job()

        # Must NOT appear in public recall (competitor run)
        public = store.recall("biltiq ai", [DataBoundary.PUBLIC])
        assert not any("₹5Cr" in e.content for e in public), \
            "Email finding leaked into PUBLIC recall!"

        # Must appear in private recall
        private = store.recall("biltiq ai", [DataBoundary.PRIVATE])
        assert any("₹5Cr" in e.content for e in private)

    @pytest.mark.asyncio
    async def test_failed_connector_marks_job_failed_no_partial_writes(self, db_path, store):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO entity_source_config "
                "(entity, priority, website_url, sources_enabled, updated_at) "
                "VALUES ('biltiq ai', 'medium', 'https://biltiq.ai', '[\"website\"]', ?)",
                (utcnow().isoformat(),),
            )
            conn.execute(
                "INSERT INTO crawl_jobs (id, entity, source_type, status, priority, scheduled_at) "
                "VALUES ('job-003', 'biltiq ai', 'website', 'pending', 5, ?)",
                (utcnow().isoformat(),),
            )
            conn.commit()

        worker = MemoryWorker(db_path)
        with patch.object(worker, "_run_connector",
                          new=AsyncMock(side_effect=RuntimeError("Firecrawl timeout"))):
            await worker._process_one_job()

        # Job marked failed
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT status, error FROM crawl_jobs WHERE id='job-003'"
            ).fetchone()
        assert row[0] == "failed"
        assert "Firecrawl timeout" in row[1]

        # No memory entries written
        recalled = store.recall("biltiq ai", [DataBoundary.PUBLIC, DataBoundary.PRIVATE])
        assert len(recalled) == 0


class TestPersonaRecall:
    """Persona-scoped recall: shared + private merge, boundary independence."""

    def test_shared_facts_visible_to_all(self, store):
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PUBLIC,
            content="BiltIQ pricing starts at ₹4,999/month.",
            source_type="website",
        ))
        result = store.recall("biltiq ai", [DataBoundary.PUBLIC])
        assert any("₹4,999" in e.content for e in result)

    def test_persona_recall_sees_shared_plus_private(self, store):
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PUBLIC,
            content="BiltIQ raised seed funding in 2025.",
            source_type="website",
        ))
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PRIVATE,
            content="Renewal call scheduled for July 1st.",
            source_type="email", persona_id="sales",
        ))

        result = store.recall(
            "biltiq ai", [DataBoundary.PUBLIC, DataBoundary.PRIVATE], persona_id="sales"
        )
        contents = [e.content for e in result]
        assert any("seed funding" in c for c in contents)
        assert any("July 1st" in c for c in contents)

    def test_persona_recall_does_not_leak_other_persona(self, store):
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PRIVATE,
            content="CEO mentioned acquisition interest.",
            source_type="email", persona_id="executive",
        ))
        result = store.recall(
            "biltiq ai", [DataBoundary.PRIVATE], persona_id="sales"
        )
        assert not any("acquisition" in e.content for e in result)

    def test_public_recall_never_returns_private_even_with_persona(self, store):
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PRIVATE,
            content="Confidential: board meeting notes.",
            source_type="email", persona_id="sales",
        ))
        result = store.recall(
            "biltiq ai", [DataBoundary.PUBLIC], persona_id="sales"
        )
        assert not any("board meeting" in e.content for e in result)

    def test_source_type_preserved_on_round_trip(self, store):
        store.write(MemoryEntry(
            entity="biltiq ai", boundary=DataBoundary.PUBLIC,
            content="LinkedIn: 5 new enterprise accounts this week.",
            source_type="social",
        ))
        result = store.recall("biltiq ai", [DataBoundary.PUBLIC])
        social = [e for e in result if e.source_type == "social"]
        assert len(social) == 1
        assert "enterprise accounts" in social[0].content


class TestScheduler:
    """CrawlScheduler: tick enqueues overdue jobs, force_enqueue is idempotent."""

    def test_tick_enqueues_job_for_overdue_entity(self, db_path):
        from sentinel.memory.scheduler import CrawlScheduler
        from datetime import timedelta

        # Insert config with last_done = 10 hours ago (overdue for medium=6h)
        stale_time = (utcnow() - timedelta(hours=10)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO entity_source_config "
                "(entity, priority, website_url, sources_enabled, updated_at) "
                "VALUES ('biltiq ai', 'medium', 'https://biltiq.ai', '[\"website\"]', ?)",
                (stale_time,),
            )
            # Mark a done job from 10h ago so scheduler sees it as stale
            conn.execute(
                "INSERT INTO crawl_jobs "
                "(id, entity, source_type, status, priority, scheduled_at, done_at) "
                "VALUES ('old-job', 'biltiq ai', 'website', 'done', 5, ?, ?)",
                (stale_time, stale_time),
            )
            conn.commit()

        sched = CrawlScheduler(db_path)
        count = sched.tick()
        assert count >= 1

        jobs = _pending_jobs(db_path, "biltiq ai")
        assert any(j["source_type"] == "website" for j in jobs)

    def test_force_enqueue_is_idempotent_same_hour(self, db_path):
        from sentinel.memory.scheduler import CrawlScheduler

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO entity_source_config "
                "(entity, priority, website_url, sources_enabled, updated_at) "
                "VALUES ('biltiq ai', 'high', 'https://biltiq.ai', '[\"website\"]', ?)",
                (utcnow().isoformat(),),
            )
            conn.commit()

        sched = CrawlScheduler(db_path)
        sched.force_enqueue("biltiq ai", priority=10)
        sched.force_enqueue("biltiq ai", priority=10)  # second call same hour

        jobs = _pending_jobs(db_path, "biltiq ai")
        assert len(jobs) == 1  # deduplicated by unique index
