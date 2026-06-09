"""SENTINEL-012 TD-1 — created-capability EXECUTION (the seam the reflect flagged as missing).

Phase 3 shipped with every unit green while an autonomous run *through* a planner-created capability
still degraded fail-soft: `_execute_plan` staffed purely by `SKILL_SPECS`, so a step on a capability
the registry minted (no SKILL_SPECS entry) hit `assert spec is not None` and failed. The green suite
never caught it because no test crossed the seam between *minting/persisting* a created spec and
*running* a plan that contains one.

This file is that seam test. It builds a registry with a minted created spec, puts it in a plan, and
runs the plan autonomously through the real `run_dag`/gate — asserting the created step actually
produces its artifact (executes), and that a *missing* spec still degrades fail-soft (the guard).

Hermetic: the FakeRunner injects the created agent's output into session state by `output_key`, so no
model is called; the registry is a tmp-file SQLite DB.
"""

from __future__ import annotations

import asyncio

from sentinel.agent import orchestrator as orch
from sentinel.agent.autonomy import gate_proposal
from sentinel.agent.dag import run_dag
from sentinel.agent.orchestrator_planner import PlanProposal, _mint_created_spec
from sentinel.agent.registry import AgentRegistry
from sentinel.artifacts.schemas import Plan, ProgramStrategy, Step
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.memory.store import SpecStore

_CREATED_CAP = "market_capture_brief"
_OUT_KEY = "market_capture_brief"
_SPEC_ID = f"created-market-{_CREATED_CAP}"

# What the created specialist "produces" — injected by the FakeRunner keyed on the agent's output_key.
_OUTPUTS = {
    _OUT_KEY: ProgramStrategy(assessment="Capture mid-market via sovereign positioning.").model_dump(),
}


class _FakeSvc:
    def __init__(self, agent):
        self.agent = agent
        self._s = None

    async def create_session(self, *, app_name, user_id, state):
        self._s = type("S", (), {"id": "s1", "state": dict(state)})()
        return self._s

    async def get_session(self, *, app_name, user_id, session_id):
        for a in [self.agent, *(getattr(self.agent, "sub_agents", []) or [])]:
            if getattr(a, "output_key", None) in _OUTPUTS:
                self._s.state[a.output_key] = _OUTPUTS[a.output_key]
        return self._s


class _FakeRunnerFactory:
    def __call__(self, *, agent, app_name):
        return type("R", (), {"session_service": _FakeSvc(agent), "run_async": _noop_run_async})()


async def _noop_run_async(self, *, user_id, session_id, new_message, run_config=None):
    if False:
        yield None


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _registry(tmp_path) -> AgentRegistry:
    reg = AgentRegistry(store=SpecStore(tmp_path / "specs.db"))
    reg.register(_mint_created_spec(_CREATED_CAP, "market", "ProgramStrategy"))  # validated on register
    return reg


def _created_plan() -> Plan:
    return Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability=_CREATED_CAP, output_key=_OUT_KEY, agent_spec_id=_SPEC_ID),
    ])


# --------------------------------------------------------------------------- #
# the seam: an autonomous plan THROUGH a created step actually executes
# --------------------------------------------------------------------------- #


def test_created_capability_step_executes_via_run_dag(monkeypatch, tmp_path):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())

    result = asyncio.run(run_dag(
        _created_plan(), registry=_registry(tmp_path), cfg=_tiered_cfg(), backend="vllm",
        cloud_allowed=False, search_provider="duckduckgo", use_cache=False,
        seeds={"s1": {"target": "BiltIQ"}},
    ))
    assert result.artifacts == [_OUT_KEY]          # the created step PRODUCED output (did not degrade)
    assert result.degraded is False
    assert result.dashboard_payload["artifacts"][_OUT_KEY]["assessment"].startswith("Capture")


def test_created_capability_executes_through_autonomy_gate(monkeypatch, tmp_path):
    # End-to-end through the real gate (autonomous): proposal → gate → run_dag → built specialist runs.
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())

    proposal = PlanProposal(plan=_created_plan(), created_specs=[])
    outcome = asyncio.run(gate_proposal(
        proposal, autonomy="autonomous", registry=_registry(tmp_path), cfg=_tiered_cfg(),
        backend="vllm", cloud_allowed=False, search_provider="duckduckgo", use_cache=False,
        seeds={"s1": {"target": "BiltIQ"}},
    ))
    assert outcome.ran is True
    assert outcome.result.artifacts == [_OUT_KEY]   # created specialist executed inside the gated run


def test_created_step_without_a_spec_degrades_fail_soft(monkeypatch, tmp_path):
    # The guard: a created capability whose spec is absent from the registry degrades just that step —
    # the run still completes honestly (degraded=True), it never crashes (AC-15).
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())
    empty = AgentRegistry(store=SpecStore(tmp_path / "empty.db"))

    result = asyncio.run(run_dag(
        _created_plan(), registry=empty, cfg=_tiered_cfg(), backend="vllm",
        cloud_allowed=False, search_provider="duckduckgo", use_cache=False,
        seeds={"s1": {"target": "BiltIQ"}},
    ))
    assert result.artifacts == []                   # nothing produced — but no crash
    assert result.degraded is True
    assert "s1" in result.missing_inputs
