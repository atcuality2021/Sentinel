"""SENTINEL-012 Phase 3 Step 13 — the generic DAG runner over an arbitrary Plan.

Step 10 proved the driver on the *fixed* BiltIQ shape; Step 13 proves the SAME engine executes any
hand-built ``Plan`` and projects a task-shape-agnostic ``Result`` (``run_dag`` / ``assemble_generic``),
honouring ``depends_on`` and failing cleanly on a structurally malformed plan.

Hermetic: every skill is driven through a FakeRunner monkeypatched onto ``orch.InMemoryRunner`` (the
same pattern as the Step-10 tests), so this exercises orchestration — toposort order + generic
assembly — not the models.

Proves:
- a 3-step linear Plan runs in dependency order → a generic Result keyed by output_key (no BiltIQ slots);
- a diamond Plan runs with the join last;
- a dangling ``depends_on`` raises cleanly (structural fault ≠ runtime degradation);
- a cycle raises cleanly.
"""

from __future__ import annotations

import asyncio

import pytest

from sentinel.agent import orchestrator as orch
from sentinel.agent.dag import assemble_generic, run_dag
from sentinel.artifacts.schemas import (
    Boundary,
    Plan,
    ProductProfile,
    SelfProfile,
    Source,
    Step,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption

_PUB = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")

# self_profile is a real SKILL_SPECS capability; its synth terminal writes state["self_profile"].
_OUTPUTS = {
    "self_profile": SelfProfile(
        org="BiltIQ",
        products=[ProductProfile(name="Sentinel", category="intel", positioning="sovereign",
                                 strengths=["air-gap"])],
        sources=[_PUB],
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
    def __init__(self, agent):
        self.agent = agent
        self._s = None

    async def create_session(self, *, app_name, user_id, state):
        self._s = _FakeSession(state)
        return self._s

    async def get_session(self, *, app_name, user_id, session_id):
        agents = [self.agent, *(getattr(self.agent, "sub_agents", []) or [])]
        for a in agents:
            ok = getattr(a, "output_key", None)
            if ok in _OUTPUTS:
                self._s.state[ok] = _OUTPUTS[ok]
        return self._s


class FakeRunnerFactory:
    def __init__(self):
        self.runs = 0

    def __call__(self, *, agent, app_name):
        self.runs += 1
        return _FakeRunner(agent)


class _FakeRunner:
    def __init__(self, agent):
        self.session_service = _FakeSvc(agent)

    async def run_async(self, *, user_id, session_id, new_message, run_config=None):
        if False:
            yield None


def _profile_step(step_id: str, *, depends_on=None) -> Step:
    """A self_profile node re-stored under a per-step output_key (so siblings don't collide)."""
    return Step(id=step_id, capability="self_profile", output_key=f"out_{step_id}",
                depends_on=list(depends_on or []))


def _seeds(*step_ids: str) -> dict[str, dict]:
    return {sid: {"target": f"Entity-{sid}"} for sid in step_ids}


def _run(plan, seeds, trace):
    return asyncio.run(run_dag(
        plan, seeds=seeds, cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False, trace=trace,
    ))


# --- a 3-step linear plan runs in order → a generic Result --------------------------------- #


def test_linear_plan_runs_in_dependency_order(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    factory = FakeRunnerFactory()
    monkeypatch.setattr(orch, "InMemoryRunner", factory)

    steps = [
        _profile_step("a"),
        _profile_step("b", depends_on=["a"]),
        _profile_step("c", depends_on=["b"]),
    ]
    plan = Plan(id="p-lin", task_id="t-lin", steps=steps)
    trace: list[str] = []
    result = _run(plan, _seeds("a", "b", "c"), trace)

    # generic projection: every produced artifact keyed by its output_key, NO BiltIQ slots
    assert set(result.dashboard_payload) == {"artifacts"}
    assert set(result.dashboard_payload["artifacts"]) == {"out_a", "out_b", "out_c"}
    assert result.artifacts == ["out_a", "out_b", "out_c"]
    assert result.degraded is False
    assert result.citations  # self_profile carried a public source
    # dependency order: the "done" trace lines appear a → b → c
    done = [ln.split()[0] for ln in trace if "done →" in ln]
    assert done == ["a", "b", "c"]
    assert factory.runs == 6  # 3 steps × (pass1 + pass2)


# --- a diamond plan joins last -------------------------------------------------------------- #


def test_diamond_plan_join_runs_last(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunnerFactory())

    steps = [
        _profile_step("a"),
        _profile_step("b", depends_on=["a"]),
        _profile_step("c", depends_on=["a"]),
        _profile_step("d", depends_on=["b", "c"]),
    ]
    plan = Plan(id="p-dia", task_id="t-dia", steps=steps)
    trace: list[str] = []
    result = _run(plan, _seeds("a", "b", "c", "d"), trace)

    done = [ln.split()[0] for ln in trace if "done →" in ln]
    assert done[0] == "a"          # root first
    assert done[-1] == "d"         # join last
    assert set(done[1:3]) == {"b", "c"}
    assert len(result.dashboard_payload["artifacts"]) == 4
    assert all(s.status == "done" for s in plan.steps)


# --- structural faults raise cleanly (not degrade) ------------------------------------------ #


def test_dangling_dependency_raises_cleanly():
    steps = [
        _profile_step("a"),
        _profile_step("b", depends_on=["ghost"]),  # 'ghost' is not a step in the plan
    ]
    plan = Plan(id="p-bad", task_id="t-bad", steps=steps)
    with pytest.raises(ValueError, match="unknown step 'ghost'"):
        asyncio.run(run_dag(plan, seeds=_seeds("a", "b"), cfg=_tiered_cfg(), backend="vllm",
                            cloud_allowed=False, use_cache=False))


def test_cycle_raises_cleanly():
    steps = [
        _profile_step("a", depends_on=["b"]),
        _profile_step("b", depends_on=["a"]),
    ]
    plan = Plan(id="p-cyc", task_id="t-cyc", steps=steps)
    with pytest.raises(ValueError, match="cycle"):
        asyncio.run(run_dag(plan, seeds=_seeds("a", "b"), cfg=_tiered_cfg(), backend="vllm",
                            cloud_allowed=False, use_cache=False))


# --- the generic projector is pure + faithful ----------------------------------------------- #


def test_assemble_generic_keys_by_output_and_unions_citations():
    produced = [("self_profile", "out_a"), ("compare", "out_b")]
    results = {
        "out_a": {"sources": [_PUB.model_dump()]},
        "out_b": {"sources": [_PUB.model_dump()]},  # duplicate source → unioned to one
    }
    plan = Plan(id="p", task_id="t", steps=[])
    res = assemble_generic(plan, results, produced, missing_inputs=[], degraded=False)
    assert set(res.dashboard_payload["artifacts"]) == {"out_a", "out_b"}
    assert len(res.citations) == 1                      # de-duplicated union
    assert "self_profile" in res.summary and "compare" in res.summary


def test_assemble_generic_carries_degraded_flag():
    plan = Plan(id="p", task_id="t", steps=[])
    res = assemble_generic(plan, {"out_a": {"sources": []}}, [("self_profile", "out_a")],
                           missing_inputs=["s_x"], degraded=True)
    assert res.degraded is True
    assert res.missing_inputs == ["s_x"]
    assert res.summary.endswith("(partial)")


# --- G-04: persona cognitive framing --------------------------------------------------------- #


def test_persona_framing_injected_into_base_seed(monkeypatch):
    """Non-default persona → persona_framing written into base_seed before run_plan fires."""
    import asyncio
    from sentinel.artifacts.schemas import Persona
    from sentinel.agent import dag as dag_mod

    captured: dict = {}

    async def fake_run_plan(plan, *, assemble, **kw):
        captured.update(kw)
        from sentinel.agent.dag import assemble_generic
        from sentinel.artifacts.schemas import Result
        return Result(task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
                      dashboard_payload={"artifacts": {}})

    monkeypatch.setattr(dag_mod, "run_plan", fake_run_plan)

    plan = Plan(id="p-pf", task_id="t-pf", steps=[_profile_step("x")])
    persona = Persona(name="doctor", reading_level="graduate", tone="clinical", format="report")
    asyncio.run(run_dag(plan, seeds=_seeds("x"), cfg=_tiered_cfg(), backend="vllm",
                        cloud_allowed=False, use_cache=False, persona=persona))

    base = (captured.get("base_seed") or {})
    pf = base.get("persona_framing", "")
    assert "doctor" in pf
    assert "clinical" in pf
    assert "graduate" in pf


def test_default_persona_no_framing(monkeypatch):
    """Default Persona() → persona_framing NOT written (no noise on standard runs)."""
    import asyncio
    from sentinel.artifacts.schemas import Persona
    from sentinel.agent import dag as dag_mod

    captured: dict = {}

    async def fake_run_plan(plan, *, assemble, **kw):
        captured.update(kw)
        from sentinel.artifacts.schemas import Result
        return Result(task_id=plan.task_id, summary="ok", artifacts=[], citations=[],
                      dashboard_payload={"artifacts": {}})

    monkeypatch.setattr(dag_mod, "run_plan", fake_run_plan)

    plan = Plan(id="p-dp", task_id="t-dp", steps=[_profile_step("y")])
    asyncio.run(run_dag(plan, seeds=_seeds("y"), cfg=_tiered_cfg(), backend="vllm",
                        cloud_allowed=False, use_cache=False, persona=Persona()))

    base = (captured.get("base_seed") or {})
    assert "persona_framing" not in base


def test_run_skill_lifts_memory_and_persona_to_synthesizer(monkeypatch):
    """_run_skill passes memory_context+persona_framing from seed to build_step_agents."""
    import asyncio
    from sentinel.agent import dag as dag_mod
    from sentinel.agent.modes import spec as spec_mod

    captured_memory: list[str] = []

    def fake_build_step_agents(spec, cfg, backend, *, cloud_allowed, search_provider,
                                two_tier, memory_context=""):
        captured_memory.append(memory_context)
        return []

    monkeypatch.setattr(spec_mod, "build_step_agents", fake_build_step_agents)
    monkeypatch.setattr(dag_mod, "build_step_agents", fake_build_step_agents)

    from sentinel.agent.dag import _run_skill
    from sentinel.agent.modes.spec import SKILL_SPECS
    spec = SKILL_SPECS["self_profile"]
    seed = {"target": "BiltIQ", "memory_context": "MEMCTX", "persona_framing": "PERSONA_FRAG"}

    async def _go():
        try:
            return await _run_skill(spec, seed, cfg=_tiered_cfg(), backend="vllm",
                                    cloud_allowed=False, search_provider="duckduckgo",
                                    two_tier=False, trace=[])
        except Exception:
            return {}

    asyncio.run(_go())
    assert captured_memory, "build_step_agents was never called"
    assert "MEMCTX" in captured_memory[0]
    assert "PERSONA_FRAG" in captured_memory[0]
