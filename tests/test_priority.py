"""SENTINEL-010 — Account Prioritization. Tests map 1:1 to spec ACs.

Pure-code scoring: no LLM, no network. DB-backed tests seed a tmp SENTINEL-002 file via the
SENTINEL_DATA_DIR env so the engine's internal RunStore()/MemoryStore() read the seed and the real
boundary choke-point (MemoryStore.recall) is exercised (AC-10). The clock is injected for
determinism (AC-2).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from sentinel.config import SentinelConfig
from sentinel.memory import DataBoundary, MemoryEntry, MemoryStore, RunRecord, RunStore
from sentinel.memory.schema import MemoryType
from sentinel.priority import (
    REGISTRY,
    PriorityStore,
    compute_account_priority,
    half_life_decay,
    normalize,
    register_signal,
)
from sentinel.priority.engine import PriorityContext

NOW = datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def cfg() -> SentinelConfig:
    return SentinelConfig.default()


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A tmp data dir with one entity that has runs + PUBLIC and PRIVATE memory."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    db = tmp_path / "sentinel.db"
    runs = RunStore(db)
    mem = MemoryStore(db)

    # Two runs: an older one and a fresh one with new material.
    runs.save(RunRecord(
        entity="Acme Corp", target="Acme Corp", mode="client", backend="vllm", kind="account_brief",
        public=2, private=1, finding_texts=["acme uses postgres", "acme hq in austin"],
        created_at=NOW - timedelta(days=30),
    ))
    runs.save(RunRecord(
        entity="Acme Corp", target="Acme Corp", mode="client", backend="vllm", kind="account_brief",
        public=3, private=2,
        finding_texts=["acme uses postgres", "acme raised series b", "acme hiring vp sales"],
        created_at=NOW - timedelta(days=2),
    ))
    mem.write(MemoryEntry(
        entity="Acme Corp", boundary=DataBoundary.PUBLIC, memory_type=MemoryType.FINDING,
        content="acme raised series b", source_label="techcrunch", source_url="https://tc.example",
        created_at=NOW - timedelta(days=2),
    ))
    mem.write(MemoryEntry(
        entity="Acme Corp", boundary=DataBoundary.PRIVATE, memory_type=MemoryType.OBSERVATION,
        content="champion is the VP eng, met at conference", source_label="crm",
        created_at=NOW - timedelta(days=5),
    ))
    return tmp_path


# --------------------------------------------------------------------------- #
# Step 1 — primitives (AC-7)
# --------------------------------------------------------------------------- #
def test_normalize_clamps_to_unit_range():
    assert normalize(5, 0, 10) == 0.5
    assert normalize(-3, 0, 10) == 0.0       # below low → clamped
    assert normalize(99, 0, 10) == 1.0       # above high → clamped
    assert normalize(5, 10, 10) == 0.0       # degenerate range → neutral


def test_normalize_invert_flips():
    assert normalize(2, 0, 10, invert=True) == pytest.approx(0.8)
    assert normalize(0, 0, 10, invert=True) == 1.0


def test_half_life_decay_endpoints():
    assert half_life_decay(0, 14) == 1.0                  # age 0 → 1
    assert half_life_decay(14, 14) == pytest.approx(0.5)  # one half-life → 0.5
    assert half_life_decay(28, 14) == pytest.approx(0.25)
    assert half_life_decay(1000, 14) < 0.001              # far future → ~0
    assert half_life_decay(5, 0) == 0.0                   # non-positive half-life → 0


def test_register_signal_populates_registry():
    register_signal("_t_probe", 1.0, lambda ctx: 0.5)
    assert "_t_probe" in REGISTRY
    assert REGISTRY["_t_probe"].weight == 1.0
    del REGISTRY["_t_probe"]


# --------------------------------------------------------------------------- #
# Step 2 — engine (AC-1/2/3/4/5)
# --------------------------------------------------------------------------- #
def _ctx(now=NOW, runs=None, memory=None):
    return PriorityContext(
        entity="x", runs=runs or [], memory=memory or [],
        allowed_boundaries=frozenset({DataBoundary.PUBLIC, DataBoundary.PRIVATE}), now=now,
    )


def test_returns_priorityscore_no_network(seeded, cfg):
    score = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    assert 0.0 <= score.score <= 100.0
    assert score.tier in ("hot", "warm", "cold")
    assert score.entity == "acme corp"
    assert score.breakdown                       # populated per registered signal
    assert score.reasons                          # at least one cited reason


def test_deterministic_identical_inputs(seeded, cfg):
    a = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    b = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    assert a.score == b.score
    assert a.breakdown == b.breakdown


def test_weight_normalization_scale_invariant(cfg):
    runs = [RunRecord(entity="z", target="z", mode="client", backend="vllm",
                      finding_texts=["a", "b"], created_at=NOW - timedelta(days=1))]
    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        register_signal("s1", 1.0, lambda c: 0.4)
        register_signal("s2", 1.0, lambda c: 0.8)
        eq = compute_account_priority("z", now=NOW, config=cfg, runs=runs, memory=[]).score
        REGISTRY.clear()
        register_signal("s1", 2.0, lambda c: 0.4)
        register_signal("s2", 2.0, lambda c: 0.8)
        doubled = compute_account_priority("z", now=NOW, config=cfg, runs=runs, memory=[]).score
        assert eq == doubled == pytest.approx(60.0)   # mean of 0.4 and 0.8 = 0.6 → 60
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_raising_signal_is_isolated(cfg):
    def boom(ctx):
        raise RuntimeError("kaboom")

    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        register_signal("ok", 1.0, lambda c: 1.0)
        register_signal("bad", 1.0, boom, default=0.0)
        score = compute_account_priority("z", now=NOW, config=cfg, runs=[], memory=[])
        assert score.breakdown["bad"] == 0.0
        assert any("bad" in n for n in score.notes)   # failure noted, not raised
        assert score.score == pytest.approx(50.0)      # (1.0 + 0.0)/2 → 50
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_score_clamped_to_100(cfg):
    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        register_signal("huge", 1.0, lambda c: 5.0)   # signal lies; engine still clamps raw + total
        score = compute_account_priority("z", now=NOW, config=cfg, runs=[], memory=[])
        assert score.score == 100.0
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


def test_empty_registry_scores_zero(cfg):
    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        score = compute_account_priority("z", now=NOW, config=cfg, runs=[], memory=[])
        assert score.score == 0.0
        assert score.tier == "cold"
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


# --------------------------------------------------------------------------- #
# Step 3 — seed signals (AC-8/10)
# --------------------------------------------------------------------------- #
def test_seed_signals_all_in_unit_range(seeded, cfg):
    score = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    for name in ("recency", "new_material", "volume", "private_engagement", "competitor_move"):
        assert name in score.breakdown
        assert 0.0 <= score.breakdown[name] <= 1.0


def test_private_engagement_contributes_with_private_allowed(seeded, cfg):
    full = compute_account_priority(
        "Acme Corp", now=NOW, config=cfg,
        allowed_boundaries={DataBoundary.PUBLIC, DataBoundary.PRIVATE},
    )
    assert full.breakdown["private_engagement"] > 0.0


def test_public_only_yields_no_private_reason(seeded, cfg):
    public = compute_account_priority(
        "Acme Corp", now=NOW, config=cfg, allowed_boundaries={DataBoundary.PUBLIC},
    )
    assert public.breakdown["private_engagement"] == 0.0
    assert all(r.boundary != DataBoundary.PRIVATE for r in public.reasons)


# --------------------------------------------------------------------------- #
# Step 4 — config (AC-3/13)
# --------------------------------------------------------------------------- #
def test_default_config_has_priority_block_and_roundtrips(cfg):
    assert cfg.priority.enabled is True
    assert cfg.priority.hot_threshold == 66.0
    reloaded = SentinelConfig.model_validate(cfg.model_dump())
    assert reloaded.priority.recency_half_life_days == cfg.priority.recency_half_life_days


def test_weight_override_changes_effective_weighting(cfg):
    runs = [RunRecord(entity="z", target="z", mode="client", backend="vllm",
                      finding_texts=["a"], created_at=NOW)]
    saved = dict(REGISTRY)
    REGISTRY.clear()
    try:
        register_signal("hi", 1.0, lambda c: 1.0)
        register_signal("lo", 1.0, lambda c: 0.0)
        base = compute_account_priority("z", now=NOW, config=cfg, runs=runs, memory=[]).score
        cfg.priority.weights = {"hi": 3.0, "lo": 1.0}   # tilt toward the 1.0 signal
        tilted = compute_account_priority("z", now=NOW, config=cfg, runs=runs, memory=[]).score
        assert base == pytest.approx(50.0)
        assert tilted == pytest.approx(75.0)
    finally:
        REGISTRY.clear()
        REGISTRY.update(saved)


# --------------------------------------------------------------------------- #
# Step 5 — persistence (AC-11)
# --------------------------------------------------------------------------- #
def test_save_and_latest_for_roundtrips(seeded, cfg, tmp_path):
    db = tmp_path / "sentinel.db"
    store = PriorityStore(db)
    score = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    store.save(score)
    got = store.latest_for("Acme Corp")
    assert got is not None
    assert got.score == score.score
    assert got.tier == score.tier
    assert got.breakdown == score.breakdown
    assert [r.text for r in got.reasons] == [r.text for r in score.reasons]


def test_history_preserved_across_saves(seeded, cfg, tmp_path):
    db = tmp_path / "sentinel.db"
    store = PriorityStore(db)
    s1 = compute_account_priority("Acme Corp", now=NOW, config=cfg)
    s2 = compute_account_priority("Acme Corp", now=NOW + timedelta(days=1), config=cfg)
    store.save(s1)
    store.save(s2)
    assert len(store.history_for("Acme Corp")) == 2


def test_priority_table_does_not_collide_with_memory(seeded, tmp_path):
    """PriorityStore shares the file but its table is independent of memory/run rows."""
    db = tmp_path / "sentinel.db"
    PriorityStore(db)                       # ensures priority schema on the same file
    assert MemoryStore(db).count("Acme Corp") >= 1   # memory still readable
    assert RunStore(db).runs_for("Acme Corp")        # runs still readable


# --------------------------------------------------------------------------- #
# AC-12 — perf
# --------------------------------------------------------------------------- #
def test_single_entity_compute_under_200ms(seeded, cfg):
    start = time.perf_counter()
    compute_account_priority("Acme Corp", now=NOW, config=cfg)
    assert (time.perf_counter() - start) < 0.2


# --------------------------------------------------------------------------- #
# AC-6 — exactly one public scoring surface
# --------------------------------------------------------------------------- #
def test_single_scoring_surface():
    import sentinel.priority as p
    assert callable(p.compute_account_priority)
    assert callable(p.register_signal)
    # No parallel scorer: the package exposes one compute entry point.
    computes = [n for n in dir(p) if n.startswith("compute_")]
    assert computes == ["compute_account_priority"]


# --------------------------------------------------------------------------- #
# Step 6 — focus route + dashboard card (AC-9/13)
# --------------------------------------------------------------------------- #
from fastapi.testclient import TestClient  # noqa: E402

from sentinel.config import get_config, reset_config, set_config  # noqa: E402
from sentinel.web import app as web_app  # noqa: E402


@pytest.fixture
def web_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    reset_config()                       # fresh default config (priority enabled) per test
    db = tmp_path / "sentinel.db"
    runs = RunStore(db)
    runs.save(RunRecord(entity="Hot Co", target="Hot Co", mode="competitor", backend="vllm",
                        public=4, finding_texts=["x", "y", "z", "w"], created_at=NOW))
    runs.save(RunRecord(entity="Stale Co", target="Stale Co", mode="competitor", backend="vllm",
                        public=1, finding_texts=["q"], created_at=NOW - timedelta(days=120)))
    yield TestClient(web_app.app)
    reset_config()


def test_focus_route_ranks_and_cites(web_client):
    r = web_client.get("/focus")
    assert r.status_code == 200
    body = r.text
    assert "Hot Co" in body and "Stale Co" in body
    # The fresher, deeper account ranks above the stale one.
    assert body.index("Hot Co") < body.index("Stale Co")
    assert "Last researched" in body            # a cited reason rendered
    assert "Signal breakdown" in body            # auditable per-signal detail (AC-11)


def test_focus_route_disabled_state(web_client):
    cfg = get_config().model_copy(deep=True)
    cfg.priority.enabled = False
    set_config(cfg)
    r = web_client.get("/focus")
    assert r.status_code == 200
    assert "turned off" in r.text


def test_dashboard_renders_focus_card(web_client):
    r = web_client.get("/")
    assert r.status_code == 200
    assert "Top to focus on" in r.text


# --------------------------------------------------------------------------- #
# SENTINEL-011b — orchestrator recompute-on-run hook
# (topology-agnostic: shared by the coordinator and SequentialAgent paths)
# --------------------------------------------------------------------------- #
from sentinel.agent import orchestrator as orch  # noqa: E402


def test_recompute_persists_snapshot_after_run(seeded, cfg):
    """The post-run hook recomputes + persists a PriorityScore and traces the tier (client mode)."""
    trace: list[str] = []
    orch._recompute_priority(target="Acme Corp", mode="client", cfg=cfg, trace=trace)
    got = PriorityStore().latest_for("Acme Corp")
    assert got is not None
    assert got.tier in {"hot", "warm", "cold"}
    assert any(t.startswith("priority:") for t in trace)


def test_recompute_disabled_is_noop(seeded, cfg):
    """priority.enabled=False → no compute, no persisted snapshot, no trace line."""
    cfg.priority.enabled = False
    trace: list[str] = []
    orch._recompute_priority(target="Acme Corp", mode="client", cfg=cfg, trace=trace)
    assert PriorityStore().latest_for("Acme Corp") is None
    assert trace == []


def test_recompute_is_failsoft(seeded, cfg, monkeypatch):
    """A scoring error is swallowed into a trace note — a completed run is never taken down."""
    def boom(*a, **k):
        raise RuntimeError("simulated scoring failure")

    monkeypatch.setattr("sentinel.priority.compute_account_priority", boom)
    trace: list[str] = []
    orch._recompute_priority(target="Acme Corp", mode="client", cfg=cfg, trace=trace)
    assert any("priority: skipped" in t for t in trace)
    assert PriorityStore().latest_for("Acme Corp") is None


def test_recompute_competitor_mode_excludes_private(seeded, cfg):
    """Boundary inherited (SENTINEL-002): a competitor recompute scores {PUBLIC} only, so the
    persisted snapshot carries zero private engagement — no re-coded boundary logic."""
    trace: list[str] = []
    orch._recompute_priority(target="Acme Corp", mode="competitor", cfg=cfg, trace=trace)
    got = PriorityStore().latest_for("Acme Corp")
    assert got is not None
    assert got.breakdown.get("private_engagement", 0.0) == 0.0
    assert not any(r.boundary == DataBoundary.PRIVATE for r in got.reasons)
