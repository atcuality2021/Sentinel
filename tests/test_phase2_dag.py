"""SENTINEL-012 Phase 2 Step 10 — the hand-built DAG driver (AC-7/15/16).

Hermetic: every skill is driven through a FakeRunner monkeypatched onto ``orch.InMemoryRunner`` (no
network, no real LLM), so this exercises the *orchestration* — toposort, two-pass execution per node,
cross-step wiring, budgets, fail-soft degradation, and the per-entity cache — not the models.

Proves:
- AC-7  : the BiltIQ S1–S5 DAG runs to a typed Result (map + matrix set + program strategy).
- AC-15 : a forced step failure yields a *degraded* Result (the aggregator runs on partial data and
          flags it), never a crash; the failed branch's dependents are skipped.
- AC-16 : budget exhaustion (max-steps or wall-clock) yields a *partial* Result.
- cache : a per-entity cache hit skips that skill's re-research entirely.
"""

from __future__ import annotations

import asyncio

import pytest

from sentinel.agent import dag
from sentinel.agent import orchestrator as orch
from sentinel.agent.dag import StepCache, TaskBudget, biltiq_program_plan, run_plan
from sentinel.artifacts.schemas import (
    Boundary,
    ComparisonAxis,
    ComparisonMatrix,
    ProductProfile,
    ProgramStrategy,
    RecommendedAction,
    SelfProfile,
    Source,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption

_PUB = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")

# Canned skill outputs, keyed by the state key each skill's terminal agent writes. The FakeRunner
# injects these into session state so the driver reads a schema-valid artifact per node.
_OUTPUTS = {
    "self_profile": SelfProfile(
        org="BiltIQ",
        products=[ProductProfile(name="Sentinel", category="intel", positioning="sovereign",
                                 strengths=["air-gap"])],
        sources=[_PUB],
    ).model_dump(),
    "battlecard": {"target": "rival", "one_line_summary": "incumbent",
                   "sources": [_PUB.model_dump()]},
    "comparison_matrix": ComparisonMatrix(
        subject="Sentinel", rival="rival",
        axes=[ComparisonAxis(axis="sovereignty", ours="air-gapped", theirs="cloud", verdict="win")],
        sources=[_PUB],
    ).model_dump(),
    "program_strategy": ProgramStrategy(
        assessment="Strong on sovereignty across the line.",
        action_plan=[RecommendedAction(action="Lead with the air-gap moat", priority="high",
                                       timeline="this quarter", rationale="we win sovereignty")],
    ).model_dump(),
}


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
        "strategist": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


class _FakeSession:
    def __init__(self, state):
        self.id = "s1"
        self.state = dict(state)


class _FakeSvc:
    def __init__(self, agent, fail_targets):
        self.agent = agent
        self.fail_targets = fail_targets
        self._s: _FakeSession | None = None

    async def create_session(self, *, app_name, user_id, state):
        self._s = _FakeSession(state)
        return self._s

    async def get_session(self, *, app_name, user_id, session_id):
        target = self._s.state.get("target")
        agents = [self.agent, *(getattr(self.agent, "sub_agents", []) or [])]
        for a in agents:
            ok = getattr(a, "output_key", None)
            if ok not in _OUTPUTS:
                continue
            # a forced failure: a competitor branch for a fail-target produces no battlecard, so the
            # driver raises RuntimeError for that step (exercised by AC-15).
            if ok == "battlecard" and target in self.fail_targets:
                continue
            self._s.state[ok] = _OUTPUTS[ok]
        return self._s


class FakeRunnerFactory:
    """Callable stand-in for ``InMemoryRunner``; counts how many run_step passes actually executed."""

    def __init__(self, *, fail_targets=frozenset()):
        self.runs = 0
        self.fail_targets = fail_targets

    def __call__(self, *, agent, app_name):
        self.runs += 1
        return _FakeRunner(agent, self.fail_targets)


class _FakeRunner:
    def __init__(self, agent, fail_targets):
        self.session_service = _FakeSvc(agent, fail_targets)

    async def run_async(self, *, user_id, session_id, new_message, run_config=None):
        if False:
            yield None


def _by_id(plan):
    return {s.id: s for s in plan.steps}


def _run(plan, seeds, **kw):
    return asyncio.run(run_plan(
        plan, seeds=seeds, cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False, **kw,
    ))


# --- plan shape ---------------------------------------------------------------------------- #


def test_biltiq_plan_shape():
    plan, seeds = biltiq_program_plan("task-1", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    ids = _by_id(plan)
    assert set(ids) == {"s_profile", "s_competitor_0", "s_competitor_1",
                        "s_compare_0", "s_compare_1", "s_strategy"}
    assert seeds["s_profile"] == {"target": "BiltIQ"}
    assert seeds["s_competitor_1"] == {"target": "Splunk"}
    # compare joins our profile + the matching rival's battlecard
    assert ids["s_compare_0"].depends_on == ["s_profile", "s_competitor_0"]
    assert ids["s_compare_0"].inputs == {"self_profile": "self_profile", "battlecard_0": "battlecard"}
    # strategy joins every comparison
    assert set(ids["s_strategy"].depends_on) == {"s_compare_0", "s_compare_1"}
    assert ids["s_strategy"].capability == "program_strategy"


# --- AC-7: full DAG → typed Result ---------------------------------------------------------- #


async def _noop_synth(state, output_key, *, cfg, backend, cloud_allowed, trace):
    return state  # no-op: leaves output_key absent → fallback to ADK pass2


@pytest.fixture(autouse=True)
def _hermetic_synth(monkeypatch):
    """Block real litellm calls from _synthesize_chunked so every test stays hermetic."""
    monkeypatch.setattr(dag, "_synthesize_chunked", _noop_synth)


def test_full_dag_runs_to_result(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    factory = FakeRunnerFactory()
    monkeypatch.setattr(orch, "InMemoryRunner", factory)

    plan, seeds = biltiq_program_plan("task-1", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = _run(plan, seeds)

    assert result.degraded is False
    assert result.task_id == "task-1"
    assert all(s.status == "done" for s in plan.steps)
    # dashboard payload carries the map, both matrices, and the strategy
    assert result.dashboard_payload["map"]["org"] == "BiltIQ"
    assert len(result.dashboard_payload["matrix"]) == 2
    assert result.dashboard_payload["strategy"]["action_plan"][0]["priority"] == "high"
    # the strategy ran on the full set → NOT flagged partial
    assert result.dashboard_payload["strategy"]["ran_on_partial_data"] is False
    assert result.citations  # sources unioned across artifacts
    # 9 passes: self_profile 2 + 2×(competitor 2) + 2×(compare 1) + strategy 1
    assert factory.runs == 9
    # every step is timed (observability)
    assert all(s.started_at and s.finished_at for s in plan.steps)


# --- AC-15: a forced step failure degrades, never crashes ----------------------------------- #


def test_forced_failure_degrades_not_crashes(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    factory = FakeRunnerFactory(fail_targets={"Splunk"})  # the Splunk competitor branch fails
    monkeypatch.setattr(orch, "InMemoryRunner", factory)

    plan, seeds = biltiq_program_plan("task-2", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = _run(plan, seeds)
    ids = _by_id(plan)

    assert result.degraded is True
    assert ids["s_competitor_1"].status == "failed"      # the bad branch
    assert ids["s_compare_1"].status == "skipped"        # its dependent, skipped not crashed
    assert ids["s_competitor_0"].status == "done"        # the healthy branch survives
    assert "s_competitor_1" in result.missing_inputs
    # the aggregator STILL ran, on the one surviving comparison, and flagged the partial data (§9.4)
    assert ids["s_strategy"].status == "done"
    assert len(result.dashboard_payload["matrix"]) == 1
    assert result.dashboard_payload["strategy"]["ran_on_partial_data"] is True


# --- AC-16: budget exhaustion → partial ----------------------------------------------------- #


def test_budget_max_steps_yields_partial(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    plan, seeds = biltiq_program_plan("task-3", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = _run(plan, seeds, budget=TaskBudget(max_steps=1))
    ids = _by_id(plan)

    assert result.degraded is True
    assert ids["s_profile"].status == "done"             # exactly one step ran
    assert ids["s_competitor_0"].status == "skipped"     # budget hit before the second
    assert result.dashboard_payload["matrix"] == []      # nothing downstream produced
    assert result.dashboard_payload["strategy"] is None


def test_budget_wall_clock_yields_partial(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())
    # Under the level scheduler (SENTINEL-013 Phase 2) wall-clock is checked once per LEVEL, not per
    # step (plan Step 6): start + one check per wave. self_profile and BOTH competitors are level-0
    # (the competitor steps carry no depends_on), so they fan out in one wave under the first clock
    # read; the compare level reads the clock next and is past budget → skipped. The run is still
    # partial (AC-7) — the cutoff is now level-granular, which is the correct concurrent semantics.
    ticks = iter([0, 100, 200, 300, 400, 500, 600])  # start + one check per wave

    plan, seeds = biltiq_program_plan("task-4", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = asyncio.run(run_plan(
        plan, seeds=seeds, cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False,
        budget=TaskBudget(wall_clock_s=150), clock=lambda: next(ticks),
    ))
    ids = _by_id(plan)

    assert result.degraded is True
    assert ids["s_profile"].status == "done"
    # level-0 sibling of self_profile — runs in the same wave, before the clock trips at the next level
    assert ids["s_competitor_0"].status == "done"
    # level-1 (depends on profile + competitor): the wall-clock is exhausted by the time this wave runs
    assert ids["s_compare_0"].status == "skipped"


# --- SENTINEL-013 Phase 2: concurrent level scheduling (AC-4, AC-6) ------------------------- #


def test_independent_level_steps_run_concurrently(monkeypatch):
    """AC-4: same-level steps overlap rather than running one-after-another. ``self_profile`` and both
    competitor steps are level-0 (the competitors carry no ``depends_on``), so the scheduler fans them
    out in one ``asyncio.gather``. We wrap ``_run_one_step`` with a concurrency counter: because every
    wrapper increments, then yields with ``sleep(0)`` *before* any does real work, all three level-0
    coroutines are in-flight at once → peak ≥ 3. A sequential executor could never exceed 1."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    real = dag._run_one_step
    gauge = {"cur": 0, "peak": 0}

    async def _traced(step, **kw):
        gauge["cur"] += 1
        gauge["peak"] = max(gauge["peak"], gauge["cur"])
        await asyncio.sleep(0)  # yield so level-siblings enter before anyone leaves
        try:
            return await real(step, **kw)
        finally:
            gauge["cur"] -= 1

    monkeypatch.setattr(dag, "_run_one_step", _traced)

    plan, seeds = biltiq_program_plan("task-cc", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = _run(plan, seeds)

    assert result.degraded is False
    assert gauge["peak"] >= 3  # level-0 fan-out: self_profile + 2 competitors overlapped


def test_concurrent_execution_is_deterministic(monkeypatch):
    """AC-6: the concurrent executor's produced artifact list (order included), degraded flag,
    missing_inputs, and citation union are identical run-to-run — completion order does not leak into
    the deliverable, because the scheduler folds each level back in DECLARED order."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    plan_a, seeds = biltiq_program_plan("task-d", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    plan_b, _ = biltiq_program_plan("task-d", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    r1 = _run(plan_a, seeds)
    r2 = _run(plan_b, seeds)

    assert r1.degraded is r2.degraded is False
    assert r1.artifacts == r2.artifacts            # exact order, not just set
    assert sorted(r1.missing_inputs) == sorted(r2.missing_inputs)
    assert ([(c.boundary, c.label, c.url) for c in r1.citations]
            == [(c.boundary, c.label, c.url) for c in r2.citations])
    # the headline (last produced) is the terminal aggregator both times — order is stable
    assert r1.dashboard_payload["strategy"] == r2.dashboard_payload["strategy"]
    assert r1.artifacts[-1] == "program_strategy"


def test_reasoner_ceiling_admits_exactly_the_cap(monkeypatch):
    """AC-7: a level fan-out *wider* than ``max_reasoner_calls`` admits exactly the ceiling and budget-
    skips the rest — the concurrent executor never over-spends the reasoner budget.

    Each BiltIQ capability costs exactly one 26B-reasoner call (every skill has a ``synthesize`` step;
    the aggregator costs 1), so the count of completed steps == reasoner calls spent. Level-0 here is
    ``s_profile`` + three competitors = 4 reasoner-costing steps fanning out in ONE wave; with the
    ceiling at 2, admission reserves against ``proj_reasoner`` in declared order and the 3rd/4th steps
    trip ``max_reasoner_calls`` *before launching* (the check-then-act race a per-step pre-check would
    have lost). So exactly 2 steps run, every later level skips, and the Result is partial — not a crash
    and not an over-budget run."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    plan, seeds = biltiq_program_plan(
        "task-ceiling", our_brand="BiltIQ", rivals=["Datadog", "Splunk", "Elastic"]
    )
    result = _run(plan, seeds, budget=TaskBudget(max_reasoner_calls=2))
    ids = _by_id(plan)

    # exactly the first two level-0 steps (declared order: profile, then competitor_0) were admitted…
    assert ids["s_profile"].status == "done"
    assert ids["s_competitor_0"].status == "done"
    # …and every reasoner-costing step past the ceiling was skipped, not run
    assert ids["s_competitor_1"].status == "skipped"
    assert ids["s_competitor_2"].status == "skipped"
    assert all(ids[c].status == "skipped" for c in ("s_compare_0", "s_compare_1", "s_compare_2"))
    assert ids["s_strategy"].status == "skipped"
    # the ceiling is exact: #(steps that produced) == max_reasoner_calls — never over-spent
    assert sum(1 for s in plan.steps if s.status == "done") == 2
    assert result.degraded is True  # partial Result, not an exception


# --- SENTINEL-013 Phase 2 Step 7: global leaf-concurrency cap (AC-5) ------------------------ #


def _gauge_factory(gauge):
    """An ``InMemoryRunner`` stand-in whose session lifecycle increments/decrements a shared gauge — so
    ``gauge['peak']`` measures how many ``run_step`` bodies are simultaneously *past* the leaf semaphore
    (the gauge brackets create→get_session, which run entirely inside the held permit)."""

    class _GaugeSvc:
        def __init__(self, agent):
            self.agent = agent
            self._s = None

        async def create_session(self, *, app_name, user_id, state):
            gauge["cur"] += 1
            gauge["peak"] = max(gauge["peak"], gauge["cur"])
            await asyncio.sleep(0)  # yield so co-admitted bodies enter before any leaves
            self._s = _FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            for a in [self.agent, *(getattr(self.agent, "sub_agents", []) or [])]:
                ok = getattr(a, "output_key", None)
                if ok in _OUTPUTS:
                    self._s.state[ok] = _OUTPUTS[ok]
            gauge["cur"] -= 1
            return self._s

    class _GaugeRunner:
        def __init__(self, agent):
            self.session_service = _GaugeSvc(agent)

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            await asyncio.sleep(0)
            if False:
                yield None

    def factory(*, agent, app_name):
        return _GaugeRunner(agent)

    return factory


def test_leaf_concurrency_capped_at_max_concurrency(monkeypatch):
    """AC-5: the leaf gate holds a wide fan-out to ``backend.max_concurrency`` concurrent runs. Level-0
    of this plan is ``self_profile`` + three competitors; with the cap at 2, at most two ADK runners are
    ever open at once — yet it still parallelizes *up to* the cap (peak == 2), not serialized to 1."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    gauge = {"cur": 0, "peak": 0}
    monkeypatch.setattr(orch, "InMemoryRunner", _gauge_factory(gauge))

    cfg = _tiered_cfg()
    cfg.backend.max_concurrency = 2
    plan, seeds = biltiq_program_plan(
        "task-sem", our_brand="BiltIQ", rivals=["Datadog", "Splunk", "Elastic"]
    )
    # Generous budget so the ONLY thing bounding the level-0 fan-out is the leaf gate, not the budget
    # (3 rivals would otherwise need 8 reasoner calls, past the default ceiling of 6).
    result = asyncio.run(run_plan(
        plan, seeds=seeds, cfg=cfg, backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False,
        budget=TaskBudget(max_steps=20, max_reasoner_calls=20),
    ))

    assert result.degraded is False
    assert gauge["peak"] == 2  # capped at the configured ceiling AND fully utilizing it


def test_tight_gate_does_not_deadlock(monkeypatch):
    """AC-5 (deadlock half): with the gate at 1 (full serialization) the deepest path
    (profile → compare → strategy) still runs to a complete, non-degraded Result — run_step never
    nests, so a permit-holder never waits on a permit."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    cfg = _tiered_cfg()
    cfg.backend.max_concurrency = 1
    plan, seeds = biltiq_program_plan("task-serial", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = asyncio.run(run_plan(
        plan, seeds=seeds, cfg=cfg, backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False,
    ))

    assert result.degraded is False
    assert all(s.status == "done" for s in plan.steps)
    assert result.dashboard_payload["strategy"]["ran_on_partial_data"] is False


# --- cache: a per-entity hit skips re-research ---------------------------------------------- #


class _FakeCache:
    def __init__(self, hits):
        self.hits = hits
        self.puts: list[tuple[str, str]] = []

    def get(self, entity, capability):
        return self.hits.get((entity.lower(), capability))

    def put(self, entity, capability, artifact):
        self.puts.append((entity, capability))


def test_cache_hit_skips_research(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    factory = FakeRunnerFactory()
    monkeypatch.setattr(orch, "InMemoryRunner", factory)
    cache = _FakeCache({("biltiq", "self_profile"): _OUTPUTS["self_profile"]})

    plan, seeds = biltiq_program_plan("task-5", our_brand="BiltIQ", rivals=["Datadog", "Splunk"])
    result = asyncio.run(run_plan(
        plan, seeds=seeds, cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", cache=cache, use_cache=True,
    ))
    ids = _by_id(plan)

    assert ids["s_profile"].status == "cached"           # served from cache
    assert factory.runs == 7                             # 9 − the 2 self_profile passes skipped
    assert ids["s_competitor_0"].status == "done"        # uncached skills still ran
    assert ("Datadog", "competitor") in cache.puts       # and were written back
    # the cached profile still flows downstream into the dashboard
    assert result.dashboard_payload["map"]["org"] == "BiltIQ"
    assert result.degraded is False
