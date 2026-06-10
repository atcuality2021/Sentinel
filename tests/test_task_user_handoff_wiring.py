"""CRITICAL-01/02 wiring tests: user_id and handoff_id reach run_dag from gate_proposal.

Both G-14 (user profile injection) and G-17 (A2A handoff completion) depend on
kwargs flowing from app.py → gate_proposal → run_dag. These tests verify that
the plumbing is live end-to-end without a running web server.
"""
from __future__ import annotations

import asyncio


# Shared fake for run_plan — captures kwargs for assertion.
_last_run_plan_kwargs: dict = {}


async def _fake_run_plan(plan, *, assemble, **kw):
    global _last_run_plan_kwargs
    _last_run_plan_kwargs = dict(kw)
    from sentinel.artifacts.schemas import Result
    for s in plan.steps:
        s.status = "done"
    return Result(
        task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
        dashboard_payload={"artifacts": {}}, degraded=False,
    )


def _make_plan():
    from sentinel.artifacts.schemas import Plan, Step
    plan = Plan(id="p-wiring", task_id="t-wiring", steps=[
        Step(id="s1", capability="finance", output_key="financial_profile"),
    ])
    plan.steps[0].status = "done"
    return plan


def _make_cfg():
    from sentinel.config.defaults import build_default
    from sentinel.config.schema import BackendOption
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


# ---------------------------------------------------------------------------
# G-17: handoff_id → SessionHandoffStore.complete() fires after successful run
# ---------------------------------------------------------------------------

def test_run_dag_completes_handoff_on_success(tmp_path, monkeypatch):
    """When run_dag receives handoff_id, it marks the SessionHandoff done post-run."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.agent import dag as dag_mod
    monkeypatch.setattr(dag_mod, "run_plan", _fake_run_plan)

    # Post a pending handoff.
    from sentinel.memory.store import SessionHandoffStore
    from sentinel.memory.schema import SessionHandoff
    store = SessionHandoffStore(tmp_path / "sentinel.db")
    h = SessionHandoff(entity="hdfc bank", intent="run finance profile", priority=8)
    store.post(h)
    assert store.pending()[0]["id"] == h.id

    asyncio.run(dag_mod.run_dag(
        _make_plan(), cfg=_make_cfg(), backend="vllm", cloud_allowed=False,
        use_cache=False, project_id="proj-x", handoff_id=h.id,
    ))

    # The handoff must now be done, not pending.
    assert store.pending() == []


# ---------------------------------------------------------------------------
# G-14: user_id → UserProfileStore.get() fires and injects persona_framing
# ---------------------------------------------------------------------------

def test_run_dag_injects_user_profile_into_persona_framing(tmp_path, monkeypatch):
    """When run_dag receives user_id whose profile has non-default prefs, persona_framing
    contains a '## User preferences' block before run_plan is called."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.agent import dag as dag_mod
    monkeypatch.setattr(dag_mod, "run_plan", _fake_run_plan)

    # Store a non-default profile.
    from sentinel.memory.store import UserProfileStore
    from sentinel.memory.schema import UserProfile
    UserProfileStore(tmp_path / "sentinel.db").upsert(UserProfile(
        user_id="credit-analyst-01",
        verbosity=5,
        citation_density=5,
        domain_level="expert",
        preferred_format="table",
    ))

    global _last_run_plan_kwargs
    _last_run_plan_kwargs = {}

    asyncio.run(dag_mod.run_dag(
        _make_plan(), cfg=_make_cfg(), backend="vllm", cloud_allowed=False,
        use_cache=False, project_id="proj-x", user_id="credit-analyst-01",
    ))

    # persona_framing in base_seed must include the preferences block.
    base = _last_run_plan_kwargs.get("base_seed") or {}
    framing = base.get("persona_framing") or ""
    assert "## User preferences" in framing
    assert "domain_level: expert" in framing
    assert "preferred_format: table" in framing


# ---------------------------------------------------------------------------
# Backward compat: neither field set → run_dag runs normally, no error
# ---------------------------------------------------------------------------

def test_run_dag_without_user_id_or_handoff_id_runs_cleanly(monkeypatch):
    """Omitting user_id and handoff_id entirely must not raise — fail-soft invariant."""
    from sentinel.agent import dag as dag_mod
    monkeypatch.setattr(dag_mod, "run_plan", _fake_run_plan)
    result = asyncio.run(dag_mod.run_dag(
        _make_plan(), cfg=_make_cfg(), backend="vllm", cloud_allowed=False, use_cache=False,
    ))
    assert not result.degraded
