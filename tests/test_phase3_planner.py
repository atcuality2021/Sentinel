"""SENTINEL-012 Phase 3 Step 15 — the orchestrator planner (AC-3 / AC-21).

Hermetic: the Plan-pass LLM is mocked (a FakeRunner injects a canned ``Plan`` into state — no
inference); the staffing pass runs for real against an in-tmp-DB :class:`AgentRegistry`. The planner
agent is also introspected offline to prove it is a sovereign, tool-free reasoner.

Proves:
- AC-21 : ``staff_plan`` REUSES a seeded capability (stamps its spec id, creates no new spec).
- AC-3  : an UNSEEN capability mints a CREATED spec that passes validation and is persisted; two
          steps sharing one new capability reuse the single created spec (no duplicate).
- AC-3  : ``plan_task`` end-to-end (mocked planner) → a valid, staffed ``PlanProposal``.
"""

from __future__ import annotations

import asyncio

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes._build import make_agent
from sentinel.agent.orchestrator_planner import (
    PLAN_KEY,
    PlanProposal,
    plan_task,
    staff_plan,
)
from sentinel.agent.registry import AgentRegistry, spec_violations
from sentinel.artifacts.schemas import Domain, Persona, Plan, Step, Task
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption
from sentinel.memory.store import SpecStore


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
        "strategist": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _task(objective="Compare us vs rivals", domain="market") -> Task:
    return Task(id="t1", project_id="p1", objective=objective,
                domain=Domain(name=domain), persona=Persona(), created_at="2026-06-08T00:00:00Z")


def _registry(tmp_path, *, seed=True) -> AgentRegistry:
    return AgentRegistry(SpecStore(tmp_path / "s.db"), seed=seed)


# --------------------------------------------------------------------------- #
# staff_plan — reuse vs create (AC-21 / AC-3)
# --------------------------------------------------------------------------- #


def test_staff_plan_reuses_seeded_capability(tmp_path):
    reg = _registry(tmp_path)                            # seeds compare/self_profile/... in 'market'
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile"),
        Step(id="s2", capability="compare", depends_on=["s1"], output_key="compare"),
    ])
    created = staff_plan(plan, _task(), reg)
    assert created == []                                 # both capabilities already staffable
    assert plan.steps[0].agent_spec_id == "seed-self_profile-market"
    assert plan.steps[1].agent_spec_id == "seed-compare-market"


def test_staff_plan_mints_validated_spec_on_miss(tmp_path):
    reg = _registry(tmp_path)
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="market_sizing", output_key="market_sizing"),  # unseen
    ])
    created = staff_plan(plan, _task(), reg)
    assert len(created) == 1
    spec = created[0]
    assert spec.origin == "created"
    assert spec_violations(spec) == []                   # AC-3: created spec is valid
    assert plan.steps[0].agent_spec_id == spec.id
    # persisted: a fresh registry over the same store now resolves the capability (reuse next time).
    assert reg.resolve("market_sizing", "market") is not None


def test_staff_plan_dedups_repeated_new_capability(tmp_path):
    reg = _registry(tmp_path)
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="market_sizing", output_key="ms_a"),
        Step(id="s2", capability="market_sizing", output_key="ms_b"),  # same new capability
    ])
    created = staff_plan(plan, _task(), reg)
    assert len(created) == 1                              # one created spec, reused for both steps
    assert plan.steps[0].agent_spec_id == plan.steps[1].agent_spec_id


def test_created_spec_is_conservative_public_toolfree(tmp_path):
    reg = _registry(tmp_path)
    plan = Plan(id="pl", task_id="t1", steps=[Step(id="s1", capability="novel", output_key="x")])
    spec = staff_plan(plan, _task(), reg)[0]
    assert spec.role == "synthesizer" and spec.tools == []   # tool-free reasoner
    assert [b.value for b in spec.boundaries] == ["public"]  # narrowest boundary, no PRIVATE escalation


# --------------------------------------------------------------------------- #
# plan_task end-to-end with a mocked planner (AC-3)
# --------------------------------------------------------------------------- #


def _fake_planner_runner(plan: Plan):
    """A FakeRunner whose session ends with ``plan`` injected under PLAN_KEY (no inference)."""

    class FakeSession:
        def __init__(self, state):
            self.id = "s1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._s = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            self._s.state[PLAN_KEY] = plan.model_dump()
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:
                yield None

    return FakeRunner


def test_plan_task_returns_staffed_proposal(monkeypatch, tmp_path):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    emitted = Plan(id="raw", task_id="WRONG", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile"),
        Step(id="s2", capability="market_sizing", depends_on=["s1"], output_key="market_sizing"),
    ])
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_planner_runner(emitted))
    reg = _registry(tmp_path)

    # An objective the deterministic template does NOT recognise → falls through to the (mocked) LLM
    # planner, which is what this test exercises (staffing + created-spec minting).
    proposal = asyncio.run(plan_task(_task(objective="Estimate the addressable market size"), reg,
                                     cfg=_tiered_cfg(), backend="vllm", cloud_allowed=False))

    assert isinstance(proposal, PlanProposal)
    assert proposal.plan.task_id == "t1"                 # bound to the task, overriding the LLM's value
    assert proposal.plan.steps[0].agent_spec_id == "seed-self_profile-market"   # reused
    assert len(proposal.created_specs) == 1              # only market_sizing was new
    assert proposal.created_specs[0].capability == "market_sizing"
    assert proposal.plan.steps[1].agent_spec_id == proposal.created_specs[0].id


# --------------------------------------------------------------------------- #
# the planner agent is a sovereign, tool-free reasoner
# --------------------------------------------------------------------------- #


def test_planner_agent_is_sovereign_toolfree(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    planner = make_agent(
        _tiered_cfg(), "orchestrator.planner", name="orchestrator_planner",
        output_key=PLAN_KEY, output_schema=Plan, mode_backend="vllm", cloud_allowed=False,
    )
    assert not isinstance(planner.model, str)            # no Gemini id string under on_prem
    assert type(planner.model).__name__ == "LiteLlm"
    assert "26B" in planner.model.model                  # strategist → reasoner tier
    assert not getattr(planner, "tools", None)           # tool-free: it plans, it does not research


def test_plan_id_is_task_scoped_not_llm_chosen(monkeypatch, tmp_path):
    # The LLM often reuses a step slug ('s1') or constant as the plan id → save_plan(INSERT OR REPLACE
    # by id) collapses every task's plan into one row. plan_task must force a unique per-task id.
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    emitted = Plan(id="s1", task_id="WRONG", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile")])
    monkeypatch.setattr(orch, "InMemoryRunner", _fake_planner_runner(emitted))
    task = _task()
    proposal = asyncio.run(plan_task(task, _registry(tmp_path), cfg=_tiered_cfg(), backend="vllm",
                                     cloud_allowed=False))
    assert proposal.plan.id == f"plan-{task.id}"     # unique per task → no collision in the store
    assert proposal.plan.task_id == task.id


def test_capability_catalogue_describes_self_vs_rival(tmp_path):
    from sentinel.agent.orchestrator_planner import _capability_catalogue
    cat = _capability_catalogue(_registry(tmp_path))
    assert "self_profile" in cat and "OUR OWN" in cat        # the planner can tell 'us'...
    assert "competitor" in cat and "RIVAL" in cat            # ...from 'them' (the #1 mislabel)


def test_template_plan_emits_canonical_compare_chain():
    from sentinel.agent.orchestrator_planner import _template_plan
    plan = _template_plan(_task(objective="Profile BiltIQ AI and compare it against Crayon"))
    caps = [s.capability for s in plan.steps]
    assert caps == ["self_profile", "competitor", "compare"]      # exactly one 'us', one rival, one compare
    cmp = next(s for s in plan.steps if s.capability == "compare")
    assert set(cmp.depends_on) == {"self_profile", "competitor"}   # compare waits on both


def test_template_plan_adds_strategy_when_requested():
    from sentinel.agent.orchestrator_planner import _template_plan
    plan = _template_plan(_task(objective="Profile us, compare vs Crayon, and a market-capture strategy"))
    caps = [s.capability for s in plan.steps]
    assert caps == ["self_profile", "competitor", "compare", "program_strategy"]
    strat = plan.steps[-1]
    assert strat.depends_on == ["compare"] and strat.inputs == {"compare": "compare"}


def test_template_plan_profile_only_and_fallback():
    from sentinel.agent.orchestrator_planner import _template_plan
    only = _template_plan(_task(objective="Profile BiltIQ AI and list its strengths"))
    assert [s.capability for s in only.steps] == ["self_profile"]
    # SENTINEL-014: single-step domains get a deterministic 1-step plan (not LLM).
    nutrition_plan = _template_plan(_task(objective="Find a recipe for biryani", domain="nutrition"))
    assert nutrition_plan is not None
    assert [s.capability for s in nutrition_plan.steps] == ["nutrition"]
    # Truly novel domain (no registered template) → falls through to LLM planner.
    assert _template_plan(_task(objective="Random query", domain="custom_novel_xyz")) is None


def test_plan_task_uses_template_without_calling_llm(monkeypatch, tmp_path):
    # A recognised market objective must NOT hit the LLM planner — if it tried, there's no runner mocked,
    # so a non-template path would error. Success proves the deterministic path ran.
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    task = _task(objective="Profile BiltIQ AI and compare it against Crayon")
    proposal = asyncio.run(plan_task(task, _registry(tmp_path), cfg=_tiered_cfg(), backend="vllm",
                                     cloud_allowed=False))
    assert [s.capability for s in proposal.plan.steps] == ["self_profile", "competitor", "compare"]
    assert proposal.plan.id == f"plan-{task.id}"
    assert all(s.agent_spec_id for s in proposal.plan.steps)      # every step staffed (reused seeds)
