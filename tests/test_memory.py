"""SENTINEL-002 — Memory Harness tests (AC-1..AC-11).

No live LLM anywhere. The headline test is AC-3 (the boundary invariant): a PRIVATE memory entry
must never surface in a public-only recall. Storage tests use a temp SQLite path; the gate test
(AC-10) inspects how the synthesizer instruction is built, not a real run.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from sentinel.agent.modes.competitor import build_competitor_agent
from sentinel.agent.orchestrator import allowed_boundaries
from sentinel.artifacts.schemas import (
    AccountBrief,
    Battlecard,
    Boundary,
    Finding,
    Source,
)
from sentinel.config import SentinelConfig
from sentinel.memory import (
    DataBoundary,
    MemoryEntry,
    MemoryStore,
    RunRecord,
    RunStore,
    compute_delta,
)
from sentinel.memory.schema import content_hash, utcnow
from sentinel.memory.strength import (
    STRENGTH_CEIL,
    ReinforceSignal,
    decayed_strength,
    reinforce,
)


# --------------------------------------------------------------------------- #
# Fixtures + helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def mem(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "sentinel.db")


@pytest.fixture
def runs(tmp_path) -> RunStore:
    return RunStore(tmp_path / "sentinel.db")


def _entry(entity, boundary, content, **kw) -> MemoryEntry:
    return MemoryEntry(entity=entity, boundary=boundary, content=content, **kw)


def _pub(text) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://x"))


def _priv(text) -> Finding:
    return Finding(text=text, source=Source(boundary=Boundary.PRIVATE, label="CRM"))


# --------------------------------------------------------------------------- #
# Step 1 — schema / content_hash
# --------------------------------------------------------------------------- #
def test_content_hash_stable_for_normalized_text():
    assert content_hash("  Hello   World ") == content_hash("hello world")
    assert content_hash("a") != content_hash("b")


def test_entry_backfills_hash_and_normalizes_entity():
    e = _entry("  Acme Corp ", DataBoundary.PUBLIC, "Series B raised")
    assert e.entity == "acme corp"
    assert e.content_hash == content_hash("Series B raised")


# --------------------------------------------------------------------------- #
# Step 2 — strength kernel
# --------------------------------------------------------------------------- #
def test_positive_reinforce_raises_but_never_exceeds_ceiling():
    e = _entry("x", DataBoundary.PUBLIC, "c")
    before = e.strength
    reinforce(e, ReinforceSignal.POSITIVE)
    assert e.strength > before
    for _ in range(50):
        reinforce(e, ReinforceSignal.POSITIVE)
    assert e.strength <= STRENGTH_CEIL


def test_neutral_reinforce_is_identity():
    e = _entry("x", DataBoundary.PUBLIC, "c")
    snap = e.model_dump()
    reinforce(e, ReinforceSignal.NEUTRAL)
    assert e.model_dump() == snap


def test_decay_decreases_over_time():
    e = _entry("x", DataBoundary.PUBLIC, "c")
    now = utcnow()
    s_now = decayed_strength(e, now)
    s_later = decayed_strength(e, now + timedelta(days=10))
    assert s_later < s_now


# --------------------------------------------------------------------------- #
# Step 3 — RunStore persistence (AC-1)
# --------------------------------------------------------------------------- #
def test_runs_persist_across_reopen(tmp_path):
    path = tmp_path / "sentinel.db"
    store = RunStore(path)
    for i in range(3):
        store.save(RunRecord(entity="acme", target="Acme", mode="client", backend="gemini",
                             created_at=utcnow() + timedelta(seconds=i)))
    reopened = RunStore(path)  # fresh handle, same file
    listed = reopened.list()
    assert len(listed) == 3
    # newest first
    assert listed[0].created_at >= listed[-1].created_at


def test_latest_for_returns_most_recent(runs):
    runs.save(RunRecord(entity="acme", target="Acme", mode="client", backend="gemini",
                        reference="old", created_at=utcnow() - timedelta(days=2)))
    runs.save(RunRecord(entity="acme", target="Acme", mode="client", backend="gemini",
                        reference="new", created_at=utcnow()))
    assert runs.latest_for("Acme").reference == "new"
    assert runs.latest_for("nobody") is None


# --------------------------------------------------------------------------- #
# Step 4 — write: fail-closed + dedup (AC-4, AC-7)
# --------------------------------------------------------------------------- #
def test_bogus_boundary_is_quarantined_and_never_recalled(mem):
    bad = MemoryEntry.model_construct(
        id="bad1", entity="acme", boundary="not-a-boundary", memory_type="finding",
        content="leak me", source_label="", source_url=None, created_at=utcnow(),
        content_hash=content_hash("leak me"), strength=1.0, interval_days=1.0, ease=2.5,
        last_reinforced_at=utcnow(), access_count=0, quarantined=False,
    )
    mem.write(bad)
    assert mem.count("acme") == 0  # not visible
    assert mem.count("acme", include_quarantined=True) == 1  # but stored, quarantined
    assert mem.recall("acme", {DataBoundary.PUBLIC, DataBoundary.PRIVATE}) == []


def test_duplicate_write_reinforces_instead_of_duplicating(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "Series B raised"))
    mem.write(_entry("acme", DataBoundary.PUBLIC, "  series b   RAISED "))  # normalized-equal
    assert mem.count("acme") == 1
    got = mem.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert got[0].access_count >= 1  # bumped by the dedup reinforce
    assert got[0].strength > 1.0


# --------------------------------------------------------------------------- #
# Step 5 — recall: THE boundary choke point (AC-3 adversarial, AC-6)
# --------------------------------------------------------------------------- #
def test_private_memory_never_enters_a_public_recall(mem):
    mem.write(_entry("Acme", DataBoundary.PRIVATE, "Deal in negotiation, $2M"))
    mem.write(_entry("Acme", DataBoundary.PUBLIC, "Hiring 40 engineers"))

    public_only = mem.recall("acme", {DataBoundary.PUBLIC})
    assert [e.content for e in public_only] == ["Hiring 40 engineers"]
    assert all(e.boundary == DataBoundary.PUBLIC for e in public_only)

    both = mem.recall("acme", {DataBoundary.PUBLIC, DataBoundary.PRIVATE})
    assert {e.boundary for e in both} == {DataBoundary.PUBLIC, DataBoundary.PRIVATE}


def test_competitor_mode_allows_only_public():
    assert allowed_boundaries("competitor") == {DataBoundary.PUBLIC}
    assert allowed_boundaries("client") == {DataBoundary.PUBLIC, DataBoundary.PRIVATE}


def test_recall_reinforces_and_drops_below_floor(mem):
    mem.write(_entry("acme", DataBoundary.PUBLIC, "fresh fact"))
    # a stale, weak entry that has decayed below the floor
    stale = _entry("acme", DataBoundary.PUBLIC, "ancient fact",
                   strength=0.1, interval_days=1.0,
                   last_reinforced_at=utcnow() - timedelta(days=120))
    mem.write(stale)

    got = mem.recall("acme", {DataBoundary.PUBLIC})
    contents = [e.content for e in got]
    assert "fresh fact" in contents
    assert "ancient fact" not in contents  # decayed below floor, dropped

    # reading reinforced the surviving entry
    again = mem.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    fresh = next(e for e in again if e.content == "fresh fact")
    assert fresh.access_count >= 1


def test_recall_respects_token_budget(mem):
    for i in range(20):
        mem.write(_entry("acme", DataBoundary.PUBLIC, f"finding number {i} " + "x" * 50))
    got = mem.recall("acme", {DataBoundary.PUBLIC}, limit=20, token_budget=40)
    assert 0 < len(got) < 20  # truncated by the budget


# --------------------------------------------------------------------------- #
# Step 6 — extraction (AC-5)
# --------------------------------------------------------------------------- #
def test_process_run_stamps_boundaries_from_findings(mem):
    brief = AccountBrief(
        account="Acme", one_line_summary="warm",
        public_signal=[_pub("hiring surge"), _pub("new HQ")],
        private_signal=[_priv("deal stalled at procurement")],
        merged_insights=["expand"],
    )
    n = mem.process_run("Acme", brief)
    assert n == 3
    pub = mem.recall("acme", {DataBoundary.PUBLIC})
    both = mem.recall("acme", {DataBoundary.PUBLIC, DataBoundary.PRIVATE})
    assert {e.content for e in pub} == {"hiring surge", "new HQ"}
    assert "deal stalled at procurement" in {e.content for e in both}
    # and the private one is absent from the public recall (the whole point)
    assert "deal stalled at procurement" not in {e.content for e in pub}


def test_battlecard_findings_are_all_public(mem):
    bc = Battlecard(target="Stripe", one_line_summary="s", positioning="p",
                    strengths=[_pub("great API")], weaknesses=[_pub("pricey")])
    mem.process_run("Stripe", bc)
    assert mem.recall("stripe", {DataBoundary.PUBLIC}) != []
    assert mem.recall("stripe", {DataBoundary.PRIVATE}) == []


# --------------------------------------------------------------------------- #
# Step 7 — delta (AC-8)
# --------------------------------------------------------------------------- #
def test_delta_first_run():
    d = compute_delta(None, ["a", "b"])
    assert d.prior_run_at is None
    assert set(d.added) == {"a", "b"}
    assert d.removed == []
    assert "First run" in d.summary


def test_delta_added_and_removed():
    prior = RunRecord(entity="acme", target="Acme", mode="client", backend="gemini",
                      finding_texts=["kept", "gone"])
    d = compute_delta(prior, ["kept", "brand new"])
    assert d.added == ["brand new"]
    assert d.removed == ["gone"]
    assert d.prior_run_at is not None


# --------------------------------------------------------------------------- #
# Step 9 — purge (AC-9)
# --------------------------------------------------------------------------- #
def test_purge_entity_clears_memory_and_runs(tmp_path):
    path = tmp_path / "sentinel.db"
    mem = MemoryStore(path)
    rs = RunStore(path)
    mem.write(_entry("acme", DataBoundary.PRIVATE, "secret"))
    rs.save(RunRecord(entity="acme", target="Acme", mode="client", backend="gemini"))

    mem.purge_entity("Acme")
    assert mem.recall("acme", {DataBoundary.PUBLIC, DataBoundary.PRIVATE}) == []
    assert rs.latest_for("acme") is None


# --------------------------------------------------------------------------- #
# Step 8 — gate / no-regression (AC-10)
# --------------------------------------------------------------------------- #
def test_empty_memory_context_keeps_synth_instruction_identical():
    cfg = SentinelConfig.default()
    agent = build_competitor_agent(config=cfg, memory_context="")
    synth = next(s for s in agent.sub_agents if s.name == "battlecard_synthesizer")
    # byte-identical to the SENTINEL-001 golden (template), i.e. no regression when memory is off
    assert synth.instruction == cfg.prompts["competitor.synthesizer"].template


def test_memory_context_is_appended_when_present():
    cfg = SentinelConfig.default()
    block = "\n\n## Prior memory for this entity\n- (PUBLIC) something"
    agent = build_competitor_agent(config=cfg, memory_context=block)
    synth = next(s for s in agent.sub_agents if s.name == "battlecard_synthesizer")
    assert synth.instruction.endswith(block)
    assert synth.instruction.startswith(cfg.prompts["competitor.synthesizer"].template)


# --------------------------------------------------------------------------- #
# G-06: knowledge graph — EntityRelation + upsert/recall + render enrichment
# --------------------------------------------------------------------------- #

def test_entity_relation_normalises_entities():
    from sentinel.memory.schema import EntityRelation
    rel = EntityRelation(from_entity="BiltIQ AI", rel_type="competitor", to_entity=" Crayon ")
    assert rel.from_entity == "biltiq ai"
    assert rel.to_entity == "crayon"


def test_upsert_and_get_related_roundtrip(tmp_path):
    from sentinel.memory.schema import EntityRelation
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    rel = EntityRelation(from_entity="biltiq ai", rel_type="competitor", to_entity="crayon")
    store.upsert_relation(rel)
    edges = store.get_related("biltiq ai")
    assert len(edges) == 1
    assert edges[0].rel_type == "competitor"
    assert edges[0].to_entity == "crayon"


def test_get_related_returns_both_directions(tmp_path):
    """get_related returns edges where entity is either source OR target."""
    from sentinel.memory.schema import EntityRelation
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    store.upsert_relation(EntityRelation(from_entity="a", rel_type="knows", to_entity="b"))
    assert len(store.get_related("b")) == 1  # b is the target
    assert len(store.get_related("a")) == 1  # a is the source


def test_get_related_empty_when_no_edges(tmp_path):
    from sentinel.memory.store import MemoryStore
    assert MemoryStore(tmp_path / "sentinel.db").get_related("nobody") == []


def test_render_memory_context_includes_relations():
    from sentinel.agent.orchestrator import _render_memory_context
    from sentinel.memory.schema import EntityRelation
    rel = EntityRelation(from_entity="biltiq ai", rel_type="competitor", to_entity="crayon",
                         context="SaaS mid-market")
    out = _render_memory_context([], relations=[rel])
    assert "crayon" in out
    assert "competitor" in out
    assert "SaaS mid-market" in out


def test_render_memory_context_empty_with_no_entries_and_no_relations():
    """AC-10 parity: empty entries + no relations → "" (byte-identical to pre-G06)."""
    from sentinel.agent.orchestrator import _render_memory_context
    assert _render_memory_context([]) == ""
    assert _render_memory_context([], relations=[]) == ""
    assert _render_memory_context([], relations=None) == ""


# --------------------------------------------------------------------------- #
# G-08: hierarchical memory paging — tier filter + pagination
# --------------------------------------------------------------------------- #

def _write_entries_with_strengths(store, entity: str, strengths: list[float]) -> None:
    """Write one PUBLIC entry per strength value, bypassing reinforcement for predictable setup."""
    from sentinel.memory.schema import content_hash, utcnow
    from sentinel.memory.schema import MemoryEntry
    for i, s in enumerate(strengths):
        e = MemoryEntry(
            entity=entity, boundary=DataBoundary.PUBLIC,
            content=f"finding {i} strength {s}",
        )
        e.strength = s
        store.write(e)


def test_hot_tier_returns_only_high_strength_entries(tmp_path):
    """tier='hot' must return only entries with decayed_strength >= HOT_THRESHOLD."""
    from sentinel.memory.store import MemoryStore
    from sentinel.memory.strength import HOT_THRESHOLD
    store = MemoryStore(tmp_path / "sentinel.db")
    _write_entries_with_strengths(store, "acme", [0.5, 1.0, 1.5, 1.8])
    hot = store.recall("acme", {DataBoundary.PUBLIC}, tier="hot", reinforce_on_read=False)
    assert all(e.strength >= HOT_THRESHOLD for e in hot)
    assert len(hot) == 2  # 1.5 and 1.8 qualify


def test_cold_tier_returns_only_below_threshold_entries(tmp_path):
    """tier='cold' returns entries with STRENGTH_FLOOR <= s < HOT_THRESHOLD."""
    from sentinel.memory.store import MemoryStore
    from sentinel.memory.strength import HOT_THRESHOLD, STRENGTH_FLOOR
    store = MemoryStore(tmp_path / "sentinel.db")
    _write_entries_with_strengths(store, "acme", [0.5, 1.0, 1.5, 1.8])
    cold = store.recall("acme", {DataBoundary.PUBLIC}, tier="cold", reinforce_on_read=False)
    assert all(STRENGTH_FLOOR <= e.strength < HOT_THRESHOLD for e in cold)
    assert len(cold) == 2  # 0.5 and 1.0 qualify


def test_hot_plus_cold_covers_all_entries(tmp_path):
    """hot + cold entry IDs must equal all-tier IDs (no gaps, no duplicates)."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    _write_entries_with_strengths(store, "acme", [0.3, 0.8, 1.3, 1.9])
    all_ids = {e.id for e in store.recall("acme", {DataBoundary.PUBLIC}, tier="all",
                                          reinforce_on_read=False, limit=20)}
    hot_ids = {e.id for e in store.recall("acme", {DataBoundary.PUBLIC}, tier="hot",
                                          reinforce_on_read=False, limit=20)}
    cold_ids = {e.id for e in store.recall("acme", {DataBoundary.PUBLIC}, tier="cold",
                                           reinforce_on_read=False, limit=20)}
    assert hot_ids | cold_ids == all_ids
    assert hot_ids & cold_ids == set()  # no overlap


def test_cold_tier_pagination_no_overlap(tmp_path):
    """Page 0 and page 1 of cold tier must not share any entries."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    # Write 6 cold entries (all below HOT_THRESHOLD = 1.2)
    _write_entries_with_strengths(store, "acme", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    pg0 = store.recall("acme", {DataBoundary.PUBLIC}, tier="cold",
                       page=0, page_size=3, reinforce_on_read=False)
    pg1 = store.recall("acme", {DataBoundary.PUBLIC}, tier="cold",
                       page=1, page_size=3, reinforce_on_read=False)
    assert len(pg0) == 3
    assert len(pg1) == 3
    assert {e.id for e in pg0} & {e.id for e in pg1} == set()


def test_recall_all_tier_unchanged_for_existing_callers(tmp_path):
    """Default tier='all' is backward-compatible: same results as before G-08."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    _write_entries_with_strengths(store, "acme", [0.5, 1.5])
    default_result = store.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    all_result = store.recall("acme", {DataBoundary.PUBLIC}, tier="all", reinforce_on_read=False)
    assert {e.id for e in default_result} == {e.id for e in all_result}
