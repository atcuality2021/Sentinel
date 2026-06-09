"""SENTINEL-012 TD-4 — hermetic happy-path tests for the two live-planner web routes.

The reflect flagged that ``GET /projects/{id}/plan`` and ``POST /projects/run-plan`` were only wired-
and-guard tested (route exists; missing project → not_found): their *bodies* were never exercised
because they call the live planner/gate. These tests mock ``plan_task``/``gate_proposal`` at the app
module so the full route logic runs hermetically — proposal → persist task+plan → gate → render —
proving the GET persists what Approve later reloads, and that POST reloads the persisted plan and runs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel.agent.autonomy import GateOutcome
from sentinel.agent.orchestrator_planner import PlanProposal
from sentinel.artifacts.schemas import Domain, Persona, Plan, Project, Result, Step, Task
from sentinel.config.schema import ProjectSettings
from sentinel.memory.store import ProjectStore
from sentinel.web import app as web_app

_NOW = "2026-06-08T00:00:00Z"


def _proposal(task_id: str) -> PlanProposal:
    plan = Plan(id=f"plan-{task_id}", task_id=task_id, steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market"),
    ])
    return PlanProposal(plan=plan, created_specs=[])


def _client() -> TestClient:
    return TestClient(web_app.app)


def test_get_plan_route_plans_persists_and_renders(monkeypatch):
    proj = Project(id="p1", name="Acme", created_at=_NOW, settings=ProjectSettings())  # autonomy=propose
    ProjectStore().save_project(proj)
    seen = {}

    async def fake_plan_task(task, registry, **kw):
        seen["task_id"] = task.id                      # capture the route-generated id
        return _proposal(task.id)

    async def fake_gate(proposal, **kw):
        # propose mode: nothing runs (the route forwards the project's autonomy setting)
        return GateOutcome(autonomy="propose", proposal=proposal, result=None, ran=False)

    monkeypatch.setattr(web_app, "plan_task", fake_plan_task)
    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)

    resp = _client().get("/projects/p1/plan?objective=Profile+us&domain=market")
    assert resp.status_code == 200
    assert "self_profile" in resp.text                 # the proposed DAG rendered
    assert "nothing has run" in resp.text.lower()      # propose banner — execution gated

    # the route persisted task + plan so Approve can reload the EXACT plan (no re-plan)
    store = ProjectStore()
    assert store.get_task(seen["task_id"]) is not None
    assert store.plan_for_task(seen["task_id"]) is not None


def test_get_plan_route_requires_an_objective(monkeypatch):
    ProjectStore().save_project(Project(id="p2", name="B", created_at=_NOW))
    resp = _client().get("/projects/p2/plan?objective=+")
    assert resp.status_code == 200
    assert "objective is required" in resp.text.lower()  # guard fires before any planner call


def test_post_run_plan_reloads_persisted_plan_and_runs(monkeypatch):
    # Pre-seed a project + task + plan (as the GET route would have), then approve-and-run.
    store = ProjectStore()
    store.save_project(Project(id="p3", name="C", created_at=_NOW))
    task = Task(id="task-xyz", project_id="p3", objective="Profile us",
                domain=Domain(name="market"), persona=Persona(), created_at=_NOW)
    store.save_task(task)
    store.save_plan(_proposal("task-xyz").plan)

    ran = {}

    async def fake_gate(proposal, **kw):
        ran["autonomy"] = kw.get("autonomy")
        return GateOutcome(autonomy="autonomous", proposal=proposal,
                           result=Result(task_id="task-xyz", summary="done", artifacts=["self_profile"]),
                           ran=True)

    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)

    resp = _client().post("/projects/run-plan", data={"task_id": "task-xyz"})
    assert resp.status_code == 200
    assert ran["autonomy"] == "autonomous"             # approve = explicit opt-in to run
    assert "self_profile" in resp.text                 # the reloaded plan rendered after the run
    assert "no plan found" not in resp.text.lower()    # the persisted plan was found + reused


def test_post_run_plan_missing_task_is_guarded():
    resp = _client().post("/projects/run-plan", data={"task_id": "nope"})
    assert resp.status_code == 200
    assert "not found" in resp.text.lower()            # guarded before any gate/planner call
