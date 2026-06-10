"""SENTINEL-012 — the per-task result route (PRG) + stale-plan self-heal.

A run used to render its Result inside the ``POST /projects/run-plan`` response body, so the URL bar
stayed on the shared action endpoint and the output was neither bookmarkable nor refresh-safe. And a
task whose plan predated the deterministic template kept re-showing a lopsided ``[competitor,
competitor]`` chain (the duplicate-battlecard bug). These tests pin the fixes:

- Approve & run **303-redirects to the task's own URL** ``/projects/{pid}/tasks/{tid}`` (PRG), having
  persisted the Result onto the task.
- Re-opening the task renders that persisted Result (no re-run).
- A stale plan (capabilities ≠ what the template now produces) **redirects to re-plan** on open; a
  matching plan does not.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from sentinel.agent.autonomy import GateOutcome
from sentinel.artifacts.schemas import Domain, Persona, Plan, Project, Result, Step, Task
from sentinel.memory.store import ProjectStore
from sentinel.web import app as web_app
from sentinel.web.app import _plan_is_stale

_NOW = "2026-06-08T00:00:00Z"


def _client(follow=True) -> TestClient:
    return TestClient(web_app.app, follow_redirects=follow)


def _task(tid="t-pr", obj="Profile us", caps=("self_profile",)) -> Task:
    return Task(id=tid, project_id="p-pr", objective=obj,
                domain=Domain(name="market"), persona=Persona(), created_at=_NOW)


def _plan(tid="t-pr", caps=("self_profile",)) -> Plan:
    return Plan(id=f"plan-{tid}", task_id=tid, steps=[
        Step(id=c, capability=c, output_key=c, agent_spec_id=f"seed-{c}-market") for c in caps])


def _seed(task: Task, plan: Plan) -> None:
    store = ProjectStore()
    store.save_project(Project(id=task.project_id, name="PR", created_at=_NOW))
    store.save_task(task)
    store.save_plan(plan)


# --------------------------------------------------------------------------- #
# PRG — Approve & run lands on the task's own URL, with the result persisted
# --------------------------------------------------------------------------- #


def test_run_redirects_to_task_url_and_persists_result(monkeypatch):
    _seed(_task(), _plan())

    async def fake_gate(proposal, **kw):
        return GateOutcome(autonomy="autonomous", proposal=proposal, ran=True,
                           result=Result(task_id="t-pr", summary="done", artifacts=["self_profile"]))

    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)
    resp = _client(follow=False).post("/projects/p-pr/tasks/t-pr/run")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/projects/p-pr/tasks/t-pr"     # PRG: its own route, not run-plan
    assert ProjectStore().get_task("t-pr").result.summary == "done"    # result persisted on the task


def test_run_plan_alias_also_redirects_to_task_url(monkeypatch):
    _seed(_task(tid="t-alias"), _plan(tid="t-alias"))

    async def fake_gate(proposal, **kw):
        return GateOutcome(autonomy="autonomous", proposal=proposal, ran=True,
                           result=Result(task_id="t-alias", summary="ok"))

    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)
    resp = _client(follow=False).post("/projects/run-plan", data={"task_id": "t-alias"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/projects/p-pr/tasks/t-alias"


def test_task_page_renders_persisted_result(monkeypatch):
    task = _task(tid="t-show")
    task.result = Result(task_id="t-show", summary="headline", artifacts=["self_profile"])
    _seed(task, _plan(tid="t-show"))

    resp = _client().get("/projects/p-pr/tasks/t-show")
    assert resp.status_code == 200
    assert "Run complete" in resp.text                 # the ran banner, not the propose banner
    assert "Approve" not in resp.text or "Run complete" in resp.text


# --------------------------------------------------------------------------- #
# stale-plan self-heal
# --------------------------------------------------------------------------- #


def test_stale_lopsided_plan_redirects_to_replan():
    # A pre-template plan with two competitor steps (the duplicate-battlecard bug) for a compare task.
    _seed(_task(tid="t-stale", obj="Profile us and benchmark against Crayon"),
          _plan(tid="t-stale", caps=("competitor", "competitor")))
    resp = _client(follow=False).get("/projects/p-pr/tasks/t-stale")
    assert resp.status_code == 303
    assert "/plan?objective=" in resp.headers["location"]     # re-planned into the canonical chain


def test_matching_plan_does_not_redirect():
    _seed(_task(tid="t-ok", obj="Profile us"), _plan(tid="t-ok", caps=("self_profile",)))
    resp = _client(follow=False).get("/projects/p-pr/tasks/t-ok")
    assert resp.status_code == 200                            # template would produce [self_profile] too


def test_save_plan_keeps_one_plan_per_task(tmp_path, monkeypatch):
    # A stale sibling row (old id-collision debris, e.g. a step-slug 's1' plan) must be dropped when the
    # canonical plan is saved — else plan_for_task can serve the stale one and loop the heal redirect.
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = ProjectStore()
    store.save_plan(Plan(id="s1", task_id="t-dup", steps=[
        Step(id="s1", capability="competitor", output_key="competitor")]))           # legacy/stale row
    store.save_plan(Plan(id="plan-t-dup", task_id="t-dup", steps=[
        Step(id="self_profile", capability="self_profile", output_key="self_profile")]))  # canonical
    got = store.plan_for_task("t-dup")
    assert got.id == "plan-t-dup"                              # the canonical plan, deterministically
    assert [s.capability for s in got.steps] == ["self_profile"]
    assert store.get_plan("s1") is None                       # the stale sibling was removed


def test_plan_is_stale_unit():
    # compare objective: template = [self_profile, competitor, compare]; a 2×competitor plan is stale.
    t = _task(obj="Profile us vs Crayon")
    assert _plan_is_stale(t, _plan(caps=("competitor", "competitor"))) is True
    assert _plan_is_stale(t, _plan(caps=("self_profile", "competitor", "compare"))) is False
    # novel domain (no template at all) → _template_plan returns None → never second-guessed → not stale.
    novel = Task(id="n", project_id="p", objective="Find a biryani recipe",
                 domain=Domain(name="custom_novel_xyz"), persona=Persona(), created_at=_NOW)
    assert _plan_is_stale(novel, _plan(caps=("anything",))) is False
    # SENTINEL-014: nutrition IS a known single-step domain; a plan with a wrong capability IS stale.
    nutrition_task = Task(id="nt", project_id="p", objective="Research omega-3",
                          domain=Domain(name="nutrition"), persona=Persona(), created_at=_NOW)
    assert _plan_is_stale(nutrition_task, _plan(caps=("anything",))) is True
    assert _plan_is_stale(nutrition_task, _plan(caps=("nutrition",))) is False
