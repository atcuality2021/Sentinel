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


def test_rerun_guidance_prompt_lands_in_task_context(monkeypatch):
    """The re-run form's optional steering prompt persists onto task.context (where _plan_seeds
    injects it into every agent's vertical_context) — and repeated re-runs REPLACE the guidance
    block instead of stacking it."""
    task = _task(tid="t-guide")
    task.context = "vendor is BiltIQ"
    _seed(task, _plan(tid="t-guide"))

    async def fake_gate(proposal, **kw):
        return GateOutcome(autonomy="autonomous", proposal=proposal, ran=True,
                           result=Result(task_id="t-guide", summary="ok"))

    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)
    c = _client(follow=False)

    c.post("/projects/p-pr/tasks/t-guide/run", data={"context": "focus more on pricing"})
    got = ProjectStore().get_task("t-guide").context
    assert got == "vendor is BiltIQ\n\n[Re-run guidance] focus more on pricing"

    # second re-run with new guidance: old guidance replaced, base context kept
    c.post("/projects/p-pr/tasks/t-guide/run", data={"context": "add citations per claim"})
    got = ProjectStore().get_task("t-guide").context
    assert got == "vendor is BiltIQ\n\n[Re-run guidance] add citations per claim"

    # blank guidance leaves context untouched
    c.post("/projects/p-pr/tasks/t-guide/run", data={"context": "  "})
    assert ProjectStore().get_task("t-guide").context == got


def test_running_task_shows_live_timeline_not_popup(monkeypatch):
    """While a run is in flight the task page IS the loader: a per-step timeline polling
    status.json — not a blocking popup overlay."""
    task = _task(tid="t-live", caps=("self_profile",))
    plan = _plan(tid="t-live")
    _seed(task, plan)
    web_app._ACTIVE_RUNS["t-live"] = {"plan": plan, "state": "running", "error": None}
    try:
        page = _client().get("/projects/p-pr/tasks/t-live")
        assert page.status_code == 200
        assert "Agents running" in page.text
        assert "status.json" in page.text                       # the poller is wired
        assert "data-step='self_profile'" in page.text          # each plan step is a timeline row
        assert "tl-agent" in page.text                          # active-agent banner present
        assert "tl-handover" in page.text                       # hand-over flash element wired

        st = _client().get("/projects/p-pr/tasks/t-live/status.json")
        assert st.status_code == 200
        body = st.json()
        assert body["state"] == "running"
        assert body["steps"][0]["status"] == "pending"          # not started → pending
        # who's working + on what: agent spec id + a model label derived from the two-pass split
        # (self_profile carries a search tool step → 12B tools pass then 26B reasoning).
        assert body["steps"][0]["agent"] == "seed-self_profile-market"
        assert "Gemma-12B" in body["steps"][0]["model"]
        assert "Gemma-26B" in body["steps"][0]["model"]

        # dag stamps started_at but leaves status='pending' → endpoint derives 'running'
        plan.steps[0].started_at = _NOW
        assert _client().get("/projects/p-pr/tasks/t-live/status.json").json()["steps"][0]["status"] == "running"
    finally:
        web_app._ACTIVE_RUNS.pop("t-live", None)


def test_step_models_mirrors_two_pass_split():
    """The timeline's model labels come from the same truth the DAG partitions on: tool-carrying
    capabilities ride 12B→26B two-pass; synth-only ones (compare) ride the 26B reasoner alone;
    a gemini run is labelled Gemini regardless of capability."""
    from sentinel.web.app import _step_models
    assert _step_models("self_profile", "vllm") == "Gemma-12B tools → Gemma-26B reasoning"
    assert _step_models("compare", "vllm") == "Gemma-26B reasoning"            # no tool steps
    assert _step_models("made_up_minted_cap", "vllm") == "Gemma-26B reasoning"  # planner-minted synth
    assert _step_models("self_profile", "gemini") == "Gemini"


def test_status_endpoint_terminates_after_run_completes(monkeypatch):
    """After the background run lands, status.json reports the terminal state so the poller
    reloads into the persisted Result."""
    _seed(_task(tid="t-fin"), _plan(tid="t-fin"))

    async def fake_gate(proposal, **kw):
        return GateOutcome(autonomy="autonomous", proposal=proposal, ran=True,
                           result=Result(task_id="t-fin", summary="done"))

    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)
    resp = _client(follow=False).post("/projects/p-pr/tasks/t-fin/run")
    assert resp.status_code == 303
    # TestClient runs BackgroundTasks before returning — the run has landed.
    assert ProjectStore().get_task("t-fin").status == "done"
    assert _client().get("/projects/p-pr/tasks/t-fin/status.json").json()["state"] == "done"
    # and the task page now renders the result, not the timeline
    page = _client().get("/projects/p-pr/tasks/t-fin")
    assert "Agents running" not in page.text


def test_task_page_renders_persisted_result(monkeypatch):
    task = _task(tid="t-show")
    task.result = Result(task_id="t-show", summary="headline", artifacts=["self_profile"])
    _seed(task, _plan(tid="t-show"))

    resp = _client().get("/projects/p-pr/tasks/t-show")
    assert resp.status_code == 200
    assert "View full plan" in resp.text               # result-first: plan collapsed behind toggle
    assert "Approve" not in resp.text                  # approve button only shown pre-run


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
