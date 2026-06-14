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

from sentinel.memory import DataBoundary, MemoryEntry
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
