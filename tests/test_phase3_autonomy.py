"""SENTINEL-012 Phase 3 Step 16 — the autonomy gate + plan-review UI (AC-4 / AC-13).

Proves the safety boundary: a new project defaults to ``propose``; in ``propose`` mode the gate runs
NOTHING (``run_dag`` is never called); ``autonomous`` is an explicit opt-in that executes the plan.
The last test runs a seeded plan for real (hermetic FakeRunner) to prove "autonomous runs" end to
end, and the render test proves the plan-review screen states plainly that nothing has executed.
"""

from __future__ import annotations

import asyncio

from sentinel.agent import autonomy as autonomy_mod
from sentinel.agent import orchestrator as orch
from sentinel.agent.autonomy import GateOutcome, gate_proposal
from sentinel.agent.orchestrator_planner import PlanProposal
from sentinel.artifacts.schemas import (
    AgentSpec,
    Boundary,
    Domain,
    Persona,
    Plan,
    ProductProfile,
    Result,
    SelfProfile,
    Source,
    Step,
    Task,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption, ProjectSettings
from sentinel.web import render

_PUB = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")


def _task() -> Task:
    return Task(id="t1", project_id="p1", objective="Profile us", domain=Domain(name="market"),
                persona=Persona(), created_at="2026-06-08T00:00:00Z")


def _proposal(*, created=()) -> PlanProposal:
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market"),
    ])
    return PlanProposal(plan=plan, created_specs=list(created))


# --------------------------------------------------------------------------- #
# AC-4/13: the propose default and the no-run guarantee
# --------------------------------------------------------------------------- #


def test_new_project_defaults_to_propose():
    assert ProjectSettings().autonomy == "propose"      # the safe default, by schema


def test_propose_mode_runs_nothing(monkeypatch):
    calls = []
    async def _spy(*a, **k):
        calls.append((a, k))
        return Result(task_id="t1", summary="ran", artifacts=[], citations=[])
    monkeypatch.setattr(autonomy_mod, "run_dag", _spy)

    outcome = asyncio.run(gate_proposal(_proposal(), autonomy="propose"))
    assert isinstance(outcome, GateOutcome)
    assert outcome.ran is False
    assert outcome.result is None
    assert outcome.proposal.plan.status == "proposed"
    assert calls == []                                   # run_dag was NEVER invoked


def test_autonomous_mode_runs_the_plan(monkeypatch):
    sentinel_result = Result(task_id="t1", summary="done", artifacts=["self_profile"], citations=[])
    calls = []
    async def _spy(plan, **k):
        calls.append(k)
        return sentinel_result
    monkeypatch.setattr(autonomy_mod, "run_dag", _spy)

    outcome = asyncio.run(gate_proposal(
        _proposal(), autonomy="autonomous", seeds={"s1": {"target": "BiltIQ"}}, cfg=build_default(),
    ))
    assert outcome.ran is True
    assert outcome.result is sentinel_result
    assert len(calls) == 1                               # executed exactly once
    assert calls[0]["seeds"] == {"s1": {"target": "BiltIQ"}}


# --------------------------------------------------------------------------- #
# AC-13 end-to-end: an autonomous seeded plan actually executes (hermetic)
# --------------------------------------------------------------------------- #

_OUTPUTS = {
    "self_profile": SelfProfile(
        org="BiltIQ",
        products=[ProductProfile(name="Sentinel", category="intel", positioning="sovereign",
                                 strengths=["air-gap"])],
        sources=[_PUB],
    ).model_dump(),
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
        return type("R", (), {"session_service": _FakeSvc(agent),
                              "run_async": _noop_run_async})()


async def _noop_run_async(self, *, user_id, session_id, new_message, run_config=None):
    if False:
        yield None


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def test_autonomous_seeded_plan_executes_for_real(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setattr(orch, "InMemoryRunner", _FakeRunnerFactory())
    outcome = asyncio.run(gate_proposal(
        _proposal(), autonomy="autonomous", seeds={"s1": {"target": "BiltIQ"}},
        cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False,
        search_provider="duckduckgo", use_cache=False,
    ))
    assert outcome.ran is True
    assert outcome.result.artifacts == ["self_profile"]  # the seeded step actually produced output
    assert outcome.result.citations                      # carried the public source through


# --------------------------------------------------------------------------- #
# the plan-review screen states plainly that nothing has run
# --------------------------------------------------------------------------- #


def test_plan_review_page_shows_propose_and_steps():
    created = [AgentSpec(id="created-market-novel", name="novel_specialist", capability="novel",
                         domain="market", role="synthesizer", skill_prompt="x", tools=[],
                         output_schema_ref="ProgramStrategy", boundaries=[Boundary.PUBLIC],
                         origin="created")]
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market"),
        Step(id="s2", capability="novel", depends_on=["s1"], output_key="novel",
             agent_spec_id="created-market-novel"),
    ])
    html = render.plan_review_page(
        task=_task(), proposal=PlanProposal(plan=plan, created_specs=created),
        autonomy="propose", backend="vllm", ran=False,
    )
    assert "nothing has run" in html.lower()             # the safety banner
    assert "self_profile" in html and "novel" in html    # both steps shown
    assert "novel_specialist" in html                    # the proposed new agent surfaced
    assert "Approve" in html                             # the explicit run control
    assert ">reuse<" in html and ">new<" in html         # reuse vs new badges


def test_plan_routes_registered_and_guarded():
    # the plan-review + approve routes exist; a GET on a missing project short-circuits to
    # not_found BEFORE any planner/backend call (hermetic — proves the wiring without inference).
    from fastapi.testclient import TestClient

    from sentinel.web import app as web_app

    paths = {getattr(rt, "path", "") for rt in web_app.app.routes}
    assert "/projects/{project_id}/plan" in paths
    assert "/projects/run-plan" in paths

    resp = TestClient(web_app.app).get("/projects/does-not-exist/plan?objective=x")
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()
