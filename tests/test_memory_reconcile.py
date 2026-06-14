"""SENTINEL-021 — Auto-reconcile product memory (one live head per entity/topic).

The defect being closed: when a fact contradicts an existing one for the same entity+boundary
(same 40-char topic prefix, different content), the G-10 detector logged a `memory_conflicts` row
but quarantined neither side, so `recall()` served BOTH contradicting findings. These tests pin the
fix: a deterministic write-time resolver demotes the loser so recall returns exactly one live head.

No live LLM anywhere — the resolver is pure and model-free (compliance-safe).

Step map (plan.html):
  Step 1 — _pick_winner ordering + order-independence            (AC2)
  Step 2 — superseded_by column round-trip + pre-migration load  (AC3/AC6)
  Step 3 — auto-resolve at write; exact-dup regression; fail-soft (AC1/AC3/AC4)
  Step 4 — reconcile_open_conflicts + golden-question rollback   (AC5)
  Step 5 — UI "N superseded" count                               (AC7)
"""

from __future__ import annotations

from datetime import timedelta

import sqlite3

from sentinel.memory import DataBoundary, MemoryEntry, MemoryStore
from sentinel.memory.schema import utcnow
from sentinel.memory.store import _pick_winner


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _entry(
    *,
    entity: str = "acme",
    boundary: DataBoundary = DataBoundary.PUBLIC,
    content: str = "fact",
    created_at=None,
    strength: float = 1.0,
    access_count: int = 0,
    id: str | None = None,
) -> MemoryEntry:
    kw: dict = dict(
        entity=entity,
        boundary=boundary,
        content=content,
        strength=strength,
        access_count=access_count,
    )
    if created_at is not None:
        kw["created_at"] = created_at
    if id is not None:
        kw["id"] = id
    return MemoryEntry(**kw)


# --------------------------------------------------------------------------- #
# Step 1 — _pick_winner: pure, deterministic resolution policy (AC2)
# --------------------------------------------------------------------------- #
def test_pick_winner_newer_created_at_wins():
    now = utcnow()
    older = _entry(content="old fact", created_at=now - timedelta(hours=1))
    newer = _entry(content="new fact", created_at=now)
    winner, loser = _pick_winner(older, newer)
    assert winner is newer
    assert loser is older


def test_pick_winner_private_beats_public_on_created_at_tie():
    # OQ-1: equal recency → the operator-vetted PRIVATE entry outranks the web-sourced PUBLIC one.
    ts = utcnow()
    pub = _entry(boundary=DataBoundary.PUBLIC, content="public claim", created_at=ts)
    priv = _entry(boundary=DataBoundary.PRIVATE, content="private claim", created_at=ts)
    winner, loser = _pick_winner(pub, priv)
    assert winner is priv
    assert loser is pub


def test_pick_winner_strength_then_access_tiebreak():
    ts = utcnow()
    weak = _entry(content="a", created_at=ts, strength=1.0, access_count=2)
    strong = _entry(content="b", created_at=ts, strength=3.0, access_count=0)
    winner, _ = _pick_winner(weak, strong)
    assert winner is strong  # higher strength wins before access_count is consulted

    # equal strength → higher access_count wins
    cold = _entry(content="c", created_at=ts, strength=2.0, access_count=1)
    hot = _entry(content="d", created_at=ts, strength=2.0, access_count=9)
    winner2, _ = _pick_winner(cold, hot)
    assert winner2 is hot


def test_pick_winner_stable_id_final_tiebreak():
    # Identical on every ranked dimension → smaller id wins, deterministically.
    ts = utcnow()
    common = dict(content="same", created_at=ts, strength=1.0, access_count=0)
    a = _entry(id="aaa", **common)
    z = _entry(id="zzz", **common)
    winner, loser = _pick_winner(a, z)
    assert winner.id == "aaa"
    assert loser.id == "zzz"


def test_pick_winner_is_order_independent():
    # AC2: f(a, b) and f(b, a) must name the same winner regardless of argument order.
    now = utcnow()
    a = _entry(id="id-a", content="a", created_at=now - timedelta(minutes=5), strength=2.0)
    b = _entry(id="id-b", content="b", created_at=now, strength=1.0)
    w1, l1 = _pick_winner(a, b)
    w2, l2 = _pick_winner(b, a)
    assert w1.id == w2.id
    assert l1.id == l2.id
    assert w1.id == "id-b"  # newer created_at wins despite lower strength


# --------------------------------------------------------------------------- #
# Step 2 — superseded_by column: round-trip + pre-migration DB load (AC3/AC6)
# --------------------------------------------------------------------------- #
def test_superseded_by_round_trips(tmp_path):
    mem = MemoryStore(tmp_path / "s.db")
    e = _entry(content="demoted fact", id="loser-1")
    e.quarantined = True
    e.superseded_by = "winner-1"
    mem.write(e)
    rows = mem.list_for_entity("acme", include_quarantined=True)
    back = next(r for r in rows if r.id == "loser-1")
    assert back.superseded_by == "winner-1"
    assert back.quarantined is True


def test_superseded_by_defaults_none_for_live_entry(tmp_path):
    mem = MemoryStore(tmp_path / "s.db")
    mem.write(_entry(content="live fact", id="live-1"))
    rows = mem.list_for_entity("acme", include_quarantined=True)
    assert next(r for r in rows if r.id == "live-1").superseded_by is None


# A pre-021 memory_entries table: has project_id (pre-021 reality) but NO superseded_by column.
_PRE_021_MEM_SCHEMA = """
CREATE TABLE memory_entries (
    id TEXT PRIMARY KEY, entity TEXT NOT NULL, boundary TEXT NOT NULL, memory_type TEXT NOT NULL,
    content TEXT NOT NULL, source_label TEXT NOT NULL, source_url TEXT, created_at TEXT NOT NULL,
    content_hash TEXT NOT NULL, strength REAL NOT NULL, interval_days REAL NOT NULL,
    ease REAL NOT NULL, last_reinforced_at TEXT NOT NULL, access_count INTEGER NOT NULL,
    quarantined INTEGER NOT NULL, project_id TEXT
);
"""


def test_pre_021_db_migrates_and_reads_unchanged(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_PRE_021_MEM_SCHEMA)
    conn.execute(
        "INSERT INTO memory_entries (id, entity, boundary, memory_type, content, source_label, "
        "source_url, created_at, content_hash, strength, interval_days, ease, last_reinforced_at, "
        "access_count, quarantined, project_id) VALUES "
        "('m1','datadog','public','finding','legacy fact','src',NULL,'2026-01-01T00:00:00Z',"
        "'h',1.0,1.0,2.5,'2026-01-01T00:00:00Z',0,0,NULL)"
    )
    conn.commit()
    conn.close()

    # Opening the store runs _ensure_schema → ALTERs in superseded_by (idempotent migration).
    mem = MemoryStore(db)
    rows = mem.list_for_entity("datadog", include_quarantined=True)
    assert len(rows) == 1
    assert rows[0].superseded_by is None  # legacy row reads back, column defaulted
    cols = {r[1] for r in sqlite3.connect(str(db)).execute("PRAGMA table_info(memory_entries)")}
    assert "superseded_by" in cols


# --------------------------------------------------------------------------- #
# Step 3 — auto-resolve at write (AC1/AC3/AC4 + fail-soft)
# --------------------------------------------------------------------------- #
# Two findings whose first 40 chars are identical (so G-10 flags a topic conflict) but whose full
# content differs (so they are not an exact-hash dup).
_COMMON40 = "Headquarters is located in the capital region"  # 45 chars; first 40 shared
_FACT_OLD = _COMMON40 + " of France."
_FACT_NEW = _COMMON40 + " of Germany."


def test_two_contradictions_recall_returns_exactly_one(tmp_path):
    mem = MemoryStore(tmp_path / "s.db")
    now = utcnow()
    mem.write(_entry(content=_FACT_OLD, id="old", created_at=now - timedelta(hours=1)))
    mem.write(_entry(content=_FACT_NEW, id="new", created_at=now))

    live = mem.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert [e.id for e in live] == ["new"]  # only the newer head survives recall (AC1)


def test_loser_quarantined_and_linked_and_conflict_resolved(tmp_path):
    mem = MemoryStore(tmp_path / "s.db")
    now = utcnow()
    mem.write(_entry(content=_FACT_OLD, id="old", created_at=now - timedelta(hours=1)))
    mem.write(_entry(content=_FACT_NEW, id="new", created_at=now))

    rows = {r.id: r for r in mem.list_for_entity("acme", include_quarantined=True)}
    assert rows["old"].quarantined is True
    assert rows["old"].superseded_by == "new"   # loser links to winner (AC3)
    assert rows["new"].quarantined is False
    assert rows["new"].superseded_by is None
    # The conflict is logged already-resolved, never left 'open' (AC3).
    assert mem.list_conflicts(status="open") == []
    assert len(mem.list_conflicts(status="resolved_b")) == 1


def test_exact_dup_reinforces_without_conflict(tmp_path):
    mem = MemoryStore(tmp_path / "s.db")
    id1 = mem.write(_entry(content="identical fact", id="dup-1"))
    id2 = mem.write(_entry(content="identical fact", id="dup-2"))
    assert id1 == id2 == "dup-1"  # second write deduped onto the first (no new row)
    assert mem.list_conflicts(status="open") == []
    live = mem.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert [e.id for e in live] == ["dup-1"]
    assert live[0].quarantined is False  # no regression — dup path never quarantines (AC4)


def test_resolver_failure_does_not_break_write(tmp_path, monkeypatch):
    import sentinel.memory.store as store_mod

    def _boom(a, b):
        raise RuntimeError("resolver exploded")

    monkeypatch.setattr(store_mod, "_pick_winner", _boom)
    mem = MemoryStore(tmp_path / "s.db")
    mem.write(_entry(content=_FACT_OLD, id="old"))
    returned = mem.write(_entry(content=_FACT_NEW, id="new"))  # must not raise

    assert returned == "new"  # the write itself succeeded despite the resolver failing
    ids = {r.id for r in mem.list_for_entity("acme", include_quarantined=True)}
    assert ids == {"old", "new"}  # both persisted (fail-soft: logged-but-unresolved at worst)
