"""SENTINEL-012 — the orchestration-visible flow UX: a persona dimension on the task form, each DAG
step's call boundary (web/public vs MCP/private vs reasoner), the post-run execution trace, and the
public/private provenance view. These make 'project → task → which agent → what it calls → result'
legible in the UI."""

from __future__ import annotations

from sentinel.agent.orchestrator_planner import PlanProposal
from sentinel.artifacts.schemas import (
    Boundary, Domain, Persona, Plan, Project, Result, Source, Step,
)
from sentinel.web import render

_NOW = "2026-06-08T00:00:00Z"
_PUB = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")
_PRV = Source(boundary=Boundary.PRIVATE, label="CRM", url=None)


def _task(persona="developer") -> "object":
    from sentinel.artifacts.schemas import Task
    return Task(id="t1", project_id="p1", objective="Profile us", domain=Domain(name="market"),
                persona=Persona(name=persona), created_at=_NOW)


def test_task_form_offers_a_persona_dimension():
    html = render.project_detail_page(project=Project(id="p1", name="X", created_at=_NOW),
                                      tasks=[], backend="vllm")
    assert "name='persona'" in html
    assert "enterprise" in html and "developer" in html      # persona options surfaced


def test_dag_shows_each_step_call_boundary():
    # self_profile/competitor call the public web; a client (account) step calls private MCP.
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market"),
        Step(id="s2", capability="client", output_key="brief", agent_spec_id="seed-client-account"),
    ])
    html = render.plan_review_page(task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy="propose", backend="vllm", ran=False)
    assert "web search · public" in html                     # public-boundary call surfaced
    assert "MCP · private" in html                           # private-boundary (MCP) call surfaced
    assert "Calls" in html and "Assigned agent" in html      # the assignment columns


def test_persona_shown_in_header():
    plan = Plan(id="pl", task_id="t1", steps=[Step(id="s1", capability="self_profile",
                                                   output_key="self_profile")])
    html = render.plan_review_page(task=_task(persona="doctor"),
                                   proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy="propose", backend="vllm", ran=False)
    assert "persona:" in html and "doctor" in html


def test_execution_trace_renders_after_run():
    plan = Plan(id="pl", task_id="t1", steps=[Step(id="s1", capability="self_profile",
                                                   output_key="self_profile")])
    result = Result(task_id="t1", summary="produced 1 artifact(s)", artifacts=["self_profile"],
                    citations=[_PUB, _PRV], dashboard_payload={"artifacts": {"self_profile": {"org": "X"}}})
    trace = ["s1 (self_profile): done → self_profile", "s2 (compare): skipped — missing deps ['s2']"]
    html = render.plan_review_page(task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy="autonomous", backend="vllm", ran=True,
                                   result=result, trace=trace)
    assert "Execution trace" in html
    assert "done → self_profile" in html                     # the run log is visible
    assert "skipped" in html                                 # fail-soft degradation shown honestly


def test_provenance_bar_splits_public_and_private():
    bar = render._provenance_bar(3, 1)
    assert "Public" in bar and "3" in bar
    assert "Private" in bar and "1" in bar
    assert render._provenance_bar(0, 0) == "<span class='pill'>no cited sources</span>"


# --------------------------------------------------------------------------- #
# capability-aware per-step seed targets (substantive multi-step output)
# --------------------------------------------------------------------------- #


def test_plan_seeds_targets_self_rival_and_carries_objective():
    from sentinel.web.app import _plan_seeds
    from sentinel.artifacts.schemas import Task as _T

    task = _T(id="t1", project_id="p1",
              objective="Profile BiltIQ AI and compare against Crayon",
              domain=Domain(name="market"), persona=Persona(), created_at=_NOW)
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile"),
        Step(id="s2", capability="competitor", output_key="competitor"),
        Step(id="s3", capability="compare", output_key="compare", depends_on=["s1", "s2"]),
    ])
    seeds = _plan_seeds(task, plan, Project(id="p1", name="BiltIQ", created_at=_NOW))

    assert seeds["s1"]["target"] == "BiltIQ AI"      # the 'us' side → our org, extracted
    assert seeds["s2"]["target"] == "Crayon"         # the rival side → the named competitor
    assert seeds["s3"]["target"]                      # reasoner gets the objective (non-empty)
    assert all(v["vertical_context"] == task.objective for v in seeds.values())


def test_plan_seeds_falls_back_when_no_rival_named():
    from sentinel.web.app import _plan_seeds
    from sentinel.artifacts.schemas import Task as _T

    task = _T(id="t1", project_id="p1", objective="Research the market for AI agents",
              domain=Domain(name="market"), persona=Persona(), created_at=_NOW)
    plan = Plan(id="pl", task_id="t1",
                steps=[Step(id="s2", capability="competitor", output_key="competitor")])
    seeds = _plan_seeds(task, plan, None)
    assert seeds["s2"]["target"] == task.objective    # no 'against X' → fail-soft to the objective


# --------------------------------------------------------------------------- #
# task lifecycle: status badge, clickable task-detail route, create→plan funnel
# --------------------------------------------------------------------------- #


def test_task_status_badge_distinguishes_states():
    assert ">created<" in render._task_status_badge("created")
    assert ">done<" in render._task_status_badge("done")
    assert "16a34a" in render._task_status_badge("done")        # done is green
    assert "b78a00" in render._task_status_badge("failed")      # failed is amber


def test_task_rows_link_to_task_detail():
    from sentinel.artifacts.schemas import Task as _T
    proj = Project(id="p9", name="X", created_at=_NOW)
    task = _T(id="task-9", project_id="p9", objective="Profile us", domain=Domain(name="market"),
              persona=Persona(), created_at=_NOW, status="done")
    html = render.project_detail_page(project=proj, tasks=[task], backend="vllm")
    assert "/projects/p9/tasks/task-9" in html               # the row is a link to the task
    assert ">done<" in html                                  # real status, not 'created'


def test_task_detail_route_reopens_the_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from sentinel.artifacts.schemas import Task as _T
    from sentinel.web import app as web_app

    from sentinel.memory.store import ProjectStore
    store = ProjectStore()
    store.save_project(Project(id="pd", name="D", created_at=_NOW))
    store.save_task(_T(id="t-d", project_id="pd", objective="Profile us",
                       domain=Domain(name="market"), persona=Persona(), created_at=_NOW))
    store.save_plan(Plan(id="pl-d", task_id="t-d", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market")]))

    resp = TestClient(web_app.app).get("/projects/pd/tasks/t-d")
    assert resp.status_code == 200
    assert "self_profile" in resp.text                       # the persisted plan DAG re-opens
    assert "Approve" in resp.text                            # with the run control


def test_create_project_with_objective_redirects_into_planning(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from sentinel.web import app as web_app

    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post("/projects", data={"name": "Acme", "website": "", "objective": "Profile us"})
    assert resp.status_code == 303
    assert "/plan?objective=" in resp.headers["location"]    # flows straight to planning the first task


def test_create_project_without_objective_lands_on_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from sentinel.web import app as web_app

    client = TestClient(web_app.app, follow_redirects=False)
    resp = client.post("/projects", data={"name": "Acme2", "website": "", "objective": ""})
    assert resp.status_code == 303
    assert "/plan?" not in resp.headers["location"]          # no objective → land on the project page


# --------------------------------------------------------------------------- #
# beautiful output (typed HTML, not JSON), visual DAG, task delete
# --------------------------------------------------------------------------- #


def test_artifact_html_renders_typed_not_json():
    sp = {"org": "BiltIQ AI", "products": [
        {"name": "Sentinel", "category": "intel", "positioning": "sovereign", "strengths": ["air-gap"]}]}
    html = render._artifact_html("self_profile", sp)
    assert "Self profile" in html and "BiltIQ AI" in html and "Sentinel" in html
    assert "air-gap" in html
    assert "{" not in html.split("Self profile")[1][:200]      # not a raw JSON dump

    cm = {"subject": "BiltIQ", "rival": "Crayon", "axes": [
        {"axis": "pricing", "ours": "flat", "theirs": "seat", "verdict": "win"}]}
    h2 = render._artifact_html("compare", cm)
    assert "Comparison matrix" in h2 and "Crayon" in h2 and "pricing" in h2 and ">win<" in h2

    ps = {"assessment": "strong", "action_plan": [
        {"action": "ship X", "priority": "high", "timeline": "this week", "rationale": "gap"}]}
    h3 = render._artifact_html("strategy", ps)
    assert "strategy" in h3.lower() and "ship X" in h3 and ">high<" in h3


def test_artifact_html_falls_back_to_json_for_unknown_shape():
    html = render._artifact_html("weird", {"foo": 1})
    assert "weird" in html and "foo" in html                   # unknown shape → labelled JSON, no crash


def test_dag_graph_lays_out_nodes_by_depth():
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market"),
        Step(id="s2", capability="competitor", output_key="competitor",
             agent_spec_id="seed-competitor-market"),
        Step(id="s3", capability="compare", output_key="compare", depends_on=["s1", "s2"],
             agent_spec_id="seed-compare-market"),
    ])
    g = render._dag_graph(plan)
    assert "Flow" in g and "self_profile" in g and "compare" in g
    assert "&rarr;" in g                                        # an arrow between dependency columns


def test_delete_task_route_removes_task(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient
    from sentinel.artifacts.schemas import Task as _T
    from sentinel.memory.store import ProjectStore
    from sentinel.web import app as web_app

    store = ProjectStore()
    store.save_project(Project(id="pz", name="Z", created_at=_NOW))
    store.save_task(_T(id="t-z", project_id="pz", objective="x", domain=Domain(name="market"),
                       persona=Persona(), created_at=_NOW))
    assert store.get_task("t-z") is not None

    resp = TestClient(web_app.app, follow_redirects=False).post("/projects/pz/tasks/t-z/delete")
    assert resp.status_code == 303
    assert ProjectStore().get_task("t-z") is None               # gone
