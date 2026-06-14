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


# --------------------------------------------------------------------------- #
# G-09: prospective memory / scheduler
# --------------------------------------------------------------------------- #

def test_schedule_and_due_tasks_roundtrip(tmp_path):
    """schedule_task → due_tasks returns the task when due_at is in the past."""
    from datetime import timezone
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    past = utcnow() - timedelta(hours=1)
    tid = store.schedule_task("Acme", "Q3 earnings published", "refresh competitive profile", past)
    assert tid  # non-empty id
    tasks = store.due_tasks("acme")
    assert len(tasks) == 1
    assert tasks[0]["action_hint"] == "refresh competitive profile"
    assert tasks[0]["id"] == tid


def test_future_task_not_returned_by_due_tasks(tmp_path):
    """Tasks with due_at in the future must not appear in due_tasks."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    future = utcnow() + timedelta(days=7)
    store.schedule_task("Acme", "next earnings", "re-run analysis", future)
    assert store.due_tasks("acme") == []


def test_mark_fired_removes_task_from_due_tasks(tmp_path):
    """After mark_fired, the task must no longer appear in due_tasks."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    past = utcnow() - timedelta(minutes=5)
    tid = store.schedule_task("Acme", "condition", "action", past)
    store.mark_fired(tid)
    assert store.due_tasks("acme") == []


def test_due_tasks_injected_into_run_dag_context(tmp_path, monkeypatch):
    """run_dag appends pending follow-up block to base_seed when tasks are due."""
    import asyncio
    from sentinel.agent import dag as dag_mod
    from sentinel.artifacts.schemas import Plan, Step, Result
    from sentinel.memory.store import MemoryStore
    from sentinel.config.defaults import build_default
    from sentinel.config.schema import BackendOption

    # Pre-schedule a due task for the target entity
    store = MemoryStore(tmp_path / "sentinel.db")
    past = utcnow() - timedelta(hours=1)
    store.schedule_task("acme corp", "Q3 published", "refresh profile", past)

    captured: list[dict] = []

    async def fake_run_plan(plan, *, assemble, **kw):
        captured.append(dict(kw.get("base_seed") or {}))
        for s in plan.steps:
            s.status = "done"
        return Result(task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
                      dashboard_payload={"artifacts": {}}, degraded=False)

    monkeypatch.setattr(dag_mod, "run_plan", fake_run_plan)

    plan = Plan(id="p-g09", task_id="t-g09", steps=[
        Step(id="s1", capability="self_profile", output_key="out"),
    ])
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    asyncio.run(dag_mod.run_dag(
        plan, cfg=cfg, backend="vllm", cloud_allowed=False, use_cache=False,
        project_id="p-x",
        base_seed={"target": "acme corp"},
    ))

    assert captured, "fake_run_plan was never called"
    ctx = captured[0].get("memory_context", "")
    assert "Pending follow-ups" in ctx
    assert "refresh profile" in ctx
    # Task should now be fired
    assert store.due_tasks("acme corp") == []


# --------------------------------------------------------------------------- #
# G-10: shared memory conflict resolution
# --------------------------------------------------------------------------- #

def test_conflict_same_topic_is_auto_resolved(tmp_path):
    """SENTINEL-021: two entries with the same entity+boundary+topic_prefix but different content
    are reconciled at write time — the conflict is logged already-resolved (never left 'open') and
    recall returns exactly one live head. (Supersedes the pre-021 'must stay open' contract.)"""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    # First 40 chars identical ("acme annual revenue report shows growth "); amount differs after.
    store.write(_entry("acme", DataBoundary.PUBLIC, "acme annual revenue report shows growth of $50M net"))
    store.write(_entry("acme", DataBoundary.PUBLIC, "acme annual revenue report shows growth of $60M net"))
    assert store.list_conflicts("acme", status="open") == []  # no longer left open
    resolved = (store.list_conflicts("acme", status="resolved_a")
                + store.list_conflicts("acme", status="resolved_b"))
    assert len(resolved) == 1
    assert resolved[0]["entity"] == "acme"
    live = store.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert len(live) == 1  # exactly one head survives


def test_no_conflict_for_distinct_topics(tmp_path):
    """Entries with clearly different topic prefixes must not trigger a conflict."""
    from sentinel.memory.store import MemoryStore
    store = MemoryStore(tmp_path / "sentinel.db")
    store.write(_entry("acme", DataBoundary.PUBLIC, "hiring surge in Q3 2024"))
    store.write(_entry("acme", DataBoundary.PUBLIC, "new product launch scheduled for Q4"))
    assert store.list_conflicts("acme") == []


# Since SENTINEL-021 auto-resolves at write, the manual resolve_conflict() path (still used by the
# human-override UI) no longer receives 'open' rows from write(). These tests seed an open conflict
# directly to exercise the resolver mechanics in isolation.
def _seed_open_conflict(db_path, store) -> tuple[str, str, str]:
    """Write two distinct-topic entries (no auto-conflict) and link them with an open conflict row.
    Returns (conflict_id, entry_a_id, entry_b_id)."""
    import sqlite3
    aid = store.write(_entry("acme", DataBoundary.PUBLIC, "revenue is $50M"))
    bid = store.write(_entry("acme", DataBoundary.PUBLIC, "headcount is 1200 staff"))
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_conflicts (id, entity, entry_id_a, entry_id_b, topic_prefix, status) "
        "VALUES ('c1','acme',?,?,'seed','open')",
        (aid, bid),
    )
    conn.commit()
    conn.close()
    return "c1", aid, bid


def test_resolve_conflict_keep_a_quarantines_b(tmp_path):
    """resolve_conflict(keep='a') must quarantine entry_id_b and mark status resolved_a."""
    from sentinel.memory.store import MemoryStore
    db = tmp_path / "sentinel.db"
    store = MemoryStore(db)
    cid, _aid, bid = _seed_open_conflict(db, store)
    store.resolve_conflict(cid, keep="a")
    assert len(store.list_conflicts("acme", status="resolved_a")) == 1
    recalled = store.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert not any(e.id == bid for e in recalled)  # entry_id_b quarantined


def test_resolve_conflict_keep_b_quarantines_a(tmp_path):
    """resolve_conflict(keep='b') must quarantine entry_id_a and mark status resolved_b."""
    from sentinel.memory.store import MemoryStore
    db = tmp_path / "sentinel.db"
    store = MemoryStore(db)
    cid, aid, _bid = _seed_open_conflict(db, store)
    store.resolve_conflict(cid, keep="b")
    assert len(store.list_conflicts("acme", status="resolved_b")) == 1
    recalled = store.recall("acme", {DataBoundary.PUBLIC}, reinforce_on_read=False)
    assert not any(e.id == aid for e in recalled)  # entry_id_a quarantined


# --------------------------------------------------------------------------- #
# G-11: context window budget allocator
# --------------------------------------------------------------------------- #

def test_context_budget_slots_sum_to_total():
    """All named slots must sum to approximately the declared total (±1 token per slot for rounding)."""
    from sentinel.memory.context_budget import ContextBudget, _PROPORTIONS
    budget = ContextBudget(total=2400)
    total_alloc = sum(budget.slot(name) for name in _PROPORTIONS)
    assert abs(total_alloc - 2400) <= len(_PROPORTIONS)


def test_context_budget_none_total_uses_defaults():
    """total=None falls back to the hardcoded default caps (backward-compatible)."""
    from sentinel.memory.context_budget import ContextBudget, _DEFAULTS
    budget = ContextBudget(total=None)
    for name, default in _DEFAULTS.items():
        assert budget.slot(name) == default


def test_context_budget_unknown_slot_returns_safe_fallback():
    """An unrecognised slot name returns a positive fallback without raising."""
    from sentinel.memory.context_budget import ContextBudget
    budget = ContextBudget(total=1000)
    assert budget.slot("nonexistent_slot") > 0


# ---------------------------------------------------------------------------
# G-14 — User Modeling
# ---------------------------------------------------------------------------

def test_user_profile_upsert_and_get_roundtrip(tmp_path):
    """upsert() persists a profile; get() returns it with all fields intact."""
    from sentinel.memory.store import UserProfileStore
    from sentinel.memory.schema import UserProfile
    store = UserProfileStore(tmp_path / "sentinel.db")
    profile = UserProfile(
        user_id="harish",
        verbosity=5,
        citation_density=4,
        domain_level="expert",
        preferred_format="prose",
    )
    store.upsert(profile)
    got = store.get("harish")
    assert got is not None
    assert got.user_id == "harish"
    assert got.verbosity == 5
    assert got.citation_density == 4
    assert got.domain_level == "expert"
    assert got.preferred_format == "prose"


def test_user_profile_get_unknown_returns_none(tmp_path):
    """get() for an unseen user_id returns None without raising."""
    from sentinel.memory.store import UserProfileStore
    store = UserProfileStore(tmp_path / "sentinel.db")
    assert store.get("ghost-user") is None


def test_render_user_profile_context_default_returns_empty():
    """render_user_profile_context returns '' for a default-valued profile (backward compat)."""
    from sentinel.memory.store import render_user_profile_context
    from sentinel.memory.schema import UserProfile
    profile = UserProfile(user_id="default-user")  # all defaults
    assert render_user_profile_context(profile) == ""
    assert render_user_profile_context(None) == ""


def test_render_user_profile_context_customised_includes_prefs():
    """A customised profile renders a '## User preferences' block injected into synthesizer."""
    from sentinel.memory.store import render_user_profile_context
    from sentinel.memory.schema import UserProfile
    profile = UserProfile(
        user_id="power-user",
        verbosity=5,
        citation_density=5,
        domain_level="expert",
        preferred_format="table",
    )
    ctx = render_user_profile_context(profile)
    assert "## User preferences" in ctx
    assert "verbosity: 5/5" in ctx
    assert "domain_level: expert" in ctx
    assert "preferred_format: table" in ctx


# ---------------------------------------------------------------------------
# G-15 — Skill Curation Loop
# ---------------------------------------------------------------------------

def test_skill_curation_record_and_top_skills(tmp_path):
    """record_outcome() persists stats; top_skills() returns them ranked by avg_score."""
    from sentinel.memory.store import SkillCurationStore
    store = SkillCurationStore(tmp_path / "sentinel.db")
    store.record_outcome("self_profile", 0.9)
    store.record_outcome("self_profile", 0.7)
    store.record_outcome("competitor", 0.5)
    top = store.top_skills(limit=5)
    assert len(top) == 2
    # self_profile avg=0.8 > competitor avg=0.5
    assert top[0]["capability"] == "self_profile"
    assert top[0]["run_count"] == 2
    assert abs(top[0]["avg_score"] - 0.8) < 0.01


def test_skill_curation_none_score_increments_count(tmp_path):
    """A None score still increments run_count so frequency is tracked even without eval."""
    from sentinel.memory.store import SkillCurationStore
    store = SkillCurationStore(tmp_path / "sentinel.db")
    store.record_outcome("self_profile", None)
    store.record_outcome("self_profile", None)
    top = store.top_skills()
    assert top[0]["run_count"] == 2


def test_skill_curation_top_skills_empty_db_returns_empty(tmp_path):
    """top_skills() on a fresh DB returns [] without raising."""
    from sentinel.memory.store import SkillCurationStore
    store = SkillCurationStore(tmp_path / "sentinel.db")
    assert store.top_skills() == []


def test_skill_curation_limit_respected(tmp_path):
    """top_skills(limit=1) returns at most 1 row even when multiple capabilities exist."""
    from sentinel.memory.store import SkillCurationStore
    store = SkillCurationStore(tmp_path / "sentinel.db")
    for cap in ("self_profile", "competitor", "compare"):
        store.record_outcome(cap, 0.8)
    assert len(store.top_skills(limit=1)) == 1


# ---------------------------------------------------------------------------
# G-17 — A2A Cross-Session Coordination
# ---------------------------------------------------------------------------

def test_handoff_post_and_pending_roundtrip(tmp_path):
    """post() persists a handoff; pending() returns it with correct fields."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    h = SessionHandoff(entity="biltiq ai", intent="run full profile", priority=8)
    store.post(h)
    pending = store.pending()
    assert len(pending) == 1
    assert pending[0]["entity"] == "biltiq ai"
    assert pending[0]["intent"] == "run full profile"
    assert pending[0]["priority"] == 8


def test_handoff_claim_removes_from_pending(tmp_path):
    """claim() moves a handoff out of pending() so it is not picked up twice."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    h = SessionHandoff(entity="openai", intent="competitive analysis", priority=5)
    store.post(h)
    store.claim(h.id)
    assert store.pending() == []


def test_handoff_complete_marks_done(tmp_path):
    """complete() sets status='done'; the handoff no longer appears in pending()."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    h = SessionHandoff(entity="anthropic", intent="profile update", priority=3)
    store.post(h)
    store.claim(h.id)
    store.complete(h.id)
    assert store.pending() == []


def test_handoff_priority_ordering(tmp_path):
    """pending() returns handoffs highest-priority first."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    store.post(SessionHandoff(entity="a", intent="low", priority=2))
    store.post(SessionHandoff(entity="b", intent="high", priority=9))
    store.post(SessionHandoff(entity="c", intent="mid", priority=5))
    pending = store.pending()
    priorities = [p["priority"] for p in pending]
    assert priorities == sorted(priorities, reverse=True)


# --- LOW-09: pending() project_id filter prevents cross-tenant leakage -------------------- #


def test_handoff_pending_filters_by_project_id(tmp_path):
    """pending(project_id=X) must only return handoffs for project X."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    store.post(SessionHandoff(entity="stripe", intent="competitor profile",
                              priority=5, project_id="proj-A"))
    store.post(SessionHandoff(entity="acme", intent="client brief",
                              priority=7, project_id="proj-B"))
    store.post(SessionHandoff(entity="glean", intent="market scan",
                              priority=3, project_id="proj-A"))

    a_pending = store.pending(project_id="proj-A")
    b_pending = store.pending(project_id="proj-B")

    assert all(p["project_id"] == "proj-A" for p in a_pending)
    assert len(a_pending) == 2
    assert all(p["project_id"] == "proj-B" for p in b_pending)
    assert len(b_pending) == 1


def test_handoff_pending_no_project_id_returns_all(tmp_path):
    """pending() without project_id returns all tenants — backward-compat for admin callers."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    store.post(SessionHandoff(entity="x", intent="t1", priority=5, project_id="proj-X"))
    store.post(SessionHandoff(entity="y", intent="t2", priority=5, project_id="proj-Y"))

    all_pending = store.pending()
    assert len(all_pending) == 2


def test_handoff_pending_unknown_project_id_returns_empty(tmp_path):
    """pending(project_id=Z) with no matching rows returns [] without error."""
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    store.post(SessionHandoff(entity="x", intent="t", priority=5, project_id="proj-X"))

    assert store.pending(project_id="proj-UNKNOWN") == []
