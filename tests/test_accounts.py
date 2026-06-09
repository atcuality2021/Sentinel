"""SENTINEL-004 — Reports & Accounts tests (AC-1..AC-11).

No live LLM anywhere. Two layers:

* **Store** — ``RunStore.entities``/``runs_for`` aggregation + ordering, and the distinguishing
  property of ``MemoryStore.list_for_entity``: it is **read-only** (AC-5). The guard reads an
  entry, calls the method, re-reads, and asserts the SM-2 state is byte-identical — proving the
  account view cannot reinforce, unlike ``recall``.
* **Routes** — the index, detail, not-found, and the POST-only purge, via ``TestClient`` against a
  temp SQLite path. Safe-method guarantee (AC-8): a ``GET`` never deletes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from sentinel.memory import (
    DataBoundary,
    MemoryEntry,
    MemoryStore,
    RunRecord,
    RunStore,
)
from sentinel.memory.schema import utcnow
from sentinel.web import app as web_app


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def db(tmp_path):
    """A shared temp DB path; both stores point at the same file (one sentinel.db)."""
    return tmp_path / "sentinel.db"


@pytest.fixture
def mem(db) -> MemoryStore:
    return MemoryStore(db)


@pytest.fixture
def runs(db) -> RunStore:
    return RunStore(db)


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    # Route the app's default stores at an isolated DB so each test is hermetic.
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    return TestClient(web_app.app)


def _entry(entity, boundary, content, **kw) -> MemoryEntry:
    return MemoryEntry(entity=entity, boundary=boundary, content=content, **kw)


def _run(entity, target, *, mode="competitor", backend="gemini", kind="battlecard",
         public=0, private=0, gaps=0, reference="ref", when=None) -> RunRecord:
    return RunRecord(
        entity=entity, target=target, mode=mode, backend=backend, kind=kind,
        public=public, private=private, gaps=gaps, reference=reference,
        created_at=when or utcnow(),
    )


def _seed_two_entities(runs: RunStore) -> None:
    now = utcnow()
    # Acme — 2 client runs, the newer one with a fresher target casing.
    runs.save(_run("Acme", "Acme Inc", mode="client", public=2, private=1,
                   when=now - timedelta(days=2)))
    runs.save(_run("acme", "Acme", mode="client", backend="vllm", public=1, private=2,
                   when=now - timedelta(hours=1)))
    # Stripe — 1 competitor run (older overall activity than Acme's newest).
    runs.save(_run("Stripe", "Stripe", mode="competitor", public=3, private=0,
                   when=now - timedelta(days=1)))


# --------------------------------------------------------------------------- #
# Step 1 — RunStore.entities / runs_for (AC-1, AC-3, AC-6)
# --------------------------------------------------------------------------- #
def test_entities_collapses_counts_and_orders_by_recent_activity(runs):
    _seed_two_entities(runs)
    summaries = runs.entities()
    keys = [s.entity for s in summaries]
    assert keys == ["acme", "stripe"]  # one row each; Acme's newest run is most recent

    acme = summaries[0]
    assert acme.runs == 2
    assert acme.display_name == "Acme"          # latest run's target casing (AC-1 / R-2)
    assert acme.public == 3 and acme.private == 3  # cumulative = per-run sum (AC-6)
    assert acme.modes == ["client"]


def test_runs_for_is_newest_first(runs):
    _seed_two_entities(runs)
    timeline = runs.runs_for("ACME")  # mixed-case key resolves (AC-10)
    assert len(timeline) == 2
    assert timeline[0].created_at >= timeline[1].created_at
    assert timeline[0].backend == "vllm"  # the newer run


def test_entities_empty_when_no_runs(runs):
    assert runs.entities() == []


# --------------------------------------------------------------------------- #
# Step 1 — MemoryStore.list_for_entity: the read-only path (AC-5)
# --------------------------------------------------------------------------- #
def test_list_for_entity_returns_both_boundaries(mem):
    mem.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    mem.write(_entry("Acme", DataBoundary.PRIVATE, "deal stalled"))
    got = mem.list_for_entity("acme")
    assert {e.boundary for e in got} == {DataBoundary.PUBLIC, DataBoundary.PRIVATE}


def test_list_for_entity_allowed_narrows(mem):
    mem.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    mem.write(_entry("Acme", DataBoundary.PRIVATE, "deal stalled"))
    pub = mem.list_for_entity("acme", allowed={DataBoundary.PUBLIC})
    assert [e.content for e in pub] == ["hiring surge"]


def test_list_for_entity_is_read_only(mem):
    """AC-5 — the distinguishing property vs recall: viewing must not reinforce."""
    mem.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    before = mem.list_for_entity("acme")[0]
    snap = (before.strength, before.access_count, before.last_reinforced_at)

    # Read it several times the way a page refresh would.
    for _ in range(3):
        mem.list_for_entity("acme")

    after = mem.list_for_entity("acme")[0]
    assert (after.strength, after.access_count, after.last_reinforced_at) == snap


def test_recall_reinforces_but_list_does_not(mem):
    """Contrast guard: recall bumps access_count; list_for_entity leaves it flat."""
    mem.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    mem.recall("acme", {DataBoundary.PUBLIC})  # reinforces on read
    reinforced = mem.list_for_entity("acme")[0].access_count
    assert reinforced >= 1
    mem.list_for_entity("acme")  # must NOT bump further
    assert mem.list_for_entity("acme")[0].access_count == reinforced


# --------------------------------------------------------------------------- #
# Steps 3/5 — GET /accounts and /accounts/{entity} (AC-1, AC-2, AC-3, AC-4, AC-6, AC-9, AC-10)
# --------------------------------------------------------------------------- #
def test_accounts_index_lists_each_entity_once(client, db):
    _seed_two_entities(RunStore(db))
    r = client.get("/accounts")
    assert r.status_code == 200
    assert r.text.count("/accounts/acme") >= 1   # one link to the acme detail
    assert "stripe" in r.text.lower()
    assert "Acme" in r.text  # display name (latest target casing)


def test_accounts_index_empty_state(client):
    r = client.get("/accounts")
    assert r.status_code == 200
    assert "No accounts yet" in r.text


def test_account_detail_shows_timeline_and_separated_memory(client, db):
    rs, ms = RunStore(db), MemoryStore(db)
    rs.save(_run("Acme", "Acme Inc", mode="client", backend="vllm", public=2, private=1))
    ms.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    ms.write(_entry("Acme", DataBoundary.PRIVATE, "deal stalled at procurement"))

    r = client.get("/accounts/acme")
    assert r.status_code == 200
    assert "Run timeline" in r.text
    assert "Public signal" in r.text and "Private signal" in r.text  # both sections (AC-4)
    assert "hiring surge" in r.text and "deal stalled at procurement" in r.text
    assert "badge public" in r.text and "badge private" in r.text


def test_account_detail_shows_run_seq_and_persisted_sources(client, db):
    """SENTINEL-008: the timeline surfaces the 1-based run sequence and each run's cited
    sources; a legacy row (no sources, run_seq 0) degrades to a neutral dash, not '#0'."""
    from sentinel.artifacts.schemas import Boundary, Source

    rs = RunStore(db)
    src = Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://tc.example")
    rs.save(_run("Acme", "Acme", when=utcnow() - timedelta(days=1)))           # → run_seq 1
    rs.save(RunRecord(entity="Acme", target="Acme", mode="competitor", backend="vllm",
                      sources=[src]))                                          # → run_seq 2

    r = client.get("/accounts/acme")
    assert r.status_code == 200
    assert ">#2<" in r.text and ">#1<" in r.text       # both runs sequenced, newest-first
    assert ">#0<" not in r.text                        # the sentinel never renders as a cell
    assert "TechCrunch" in r.text                       # provenance round-trips into the page
    assert "https://tc.example" in r.text


def test_account_detail_cumulative_counts_match_run_sum(client, db):
    rs = RunStore(db)
    rs.save(_run("Acme", "Acme", public=2, private=1, when=utcnow() - timedelta(days=1)))
    rs.save(_run("Acme", "Acme", public=3, private=4, when=utcnow()))
    r = client.get("/accounts/acme")
    # cumulative provenance pills sum the per-run counts (AC-6): public 5, private 5
    assert "Public: <b>5</b>" in r.text
    assert "Private: <b>5</b>" in r.text


def test_account_with_only_public_memory_shows_no_private_section(client, db):
    rs, ms = RunStore(db), MemoryStore(db)
    rs.save(_run("Acme", "Acme", public=1))
    ms.write(_entry("Acme", DataBoundary.PUBLIC, "hiring surge"))
    r = client.get("/accounts/acme")
    assert "Public signal" in r.text
    assert "Private signal" not in r.text  # empty section renders nothing (AC-4)


def test_unknown_account_is_not_found_not_500(client):
    r = client.get("/accounts/nobody-here")
    assert r.status_code == 200  # a clean 200 page, never a 500 (AC-9)
    assert "No such account" in r.text


def test_entity_key_with_spaces_and_case_round_trips_and_escapes(client, db):
    rs = RunStore(db)
    rs.save(_run("Acme  CORP <x>", "Acme  CORP <x>", public=1))  # normalizes to 'acme corp <x>'
    # the index link is URL-encoded; following it resolves the same entity (AC-10)
    idx = client.get("/accounts")
    assert "acme%20corp" in idx.text.lower()
    detail = client.get("/accounts/acme corp <x>")
    assert detail.status_code == 200
    assert "Run timeline" in detail.text
    # the angle-bracket name is escaped, not live markup (no stored XSS)
    assert "<x>" not in detail.text
    assert "&lt;x&gt;" in detail.text


def test_memory_finding_text_is_escaped(client, db):
    rs, ms = RunStore(db), MemoryStore(db)
    rs.save(_run("Acme", "Acme", public=1))
    ms.write(_entry("Acme", DataBoundary.PUBLIC, "<script>alert(1)</script>"))
    r = client.get("/accounts/acme")
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


# --------------------------------------------------------------------------- #
# Step 6 — purge: POST-only, behind a confirm (AC-7, AC-8)
# --------------------------------------------------------------------------- #
def test_get_detail_is_safe_and_confirm_does_not_delete(client, db):
    rs, ms = RunStore(db), MemoryStore(db)
    rs.save(_run("Acme", "Acme", public=1, private=1))
    ms.write(_entry("Acme", DataBoundary.PRIVATE, "secret deal"))

    # default detail has no POST form; the ?confirm=purge variant reveals it (AC-8)
    plain = client.get("/accounts/acme")
    assert "/accounts/acme/purge" not in plain.text
    confirm = client.get("/accounts/acme?confirm=purge")
    assert "/accounts/acme/purge" in confirm.text

    # neither GET deleted anything
    assert MemoryStore(db).count("acme") == 1
    assert RunStore(db).runs_for("acme") != []


def test_post_purge_deletes_memory_and_runs(client, db):
    rs, ms = RunStore(db), MemoryStore(db)
    rs.save(_run("Acme", "Acme", public=1, private=1))
    ms.write(_entry("Acme", DataBoundary.PRIVATE, "secret deal"))

    r = client.post("/accounts/acme/purge", follow_redirects=False)
    assert r.status_code == 303  # POST→GET redirect; a refresh can't re-trigger (AC-8)
    assert r.headers["location"].startswith("/accounts")

    # gone from both tables (AC-7): absent from index, detail is not-found
    assert MemoryStore(db).count("acme") == 0
    assert RunStore(db).runs_for("acme") == []
    assert "No such account" in client.get("/accounts/acme").text
