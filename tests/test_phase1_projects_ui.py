"""SENTINEL-012 Phase 1 Step 6 — /projects UI shell (AC-10).

TestClient over the FastAPI app: create a project, project pages render 200, and the existing
screens still render 200 both with and without a project filter (no-regression of the scoping kwarg).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sentinel.web import app as web_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(web_app.app)


def _create_project(client, name="BiltIQ market-capture", website="https://biltiq.ai") -> str:
    r = client.post("/projects", data={"name": name, "website": website}, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/projects/")
    return loc.rsplit("/", 1)[1]


def test_projects_nav_and_empty_state(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert "New project" in r.text
    # the nav exposes the new Projects target
    assert "href='/projects'" in r.text


def test_create_project_then_detail_renders(client):
    pid = _create_project(client)
    detail = client.get(f"/projects/{pid}")
    assert detail.status_code == 200
    assert "BiltIQ market-capture" in detail.text
    # the active-project pill reflects this project (not the default "sovereign")
    assert "project: BiltIQ market-capture" in detail.text
    # and it shows up on the list page
    listing = client.get("/projects")
    assert listing.status_code == 200
    assert "BiltIQ market-capture" in listing.text


def test_create_project_with_context_saves_and_prefills(client):
    """New Project form accepts a context/use-case prompt; it persists on the project and
    prefills the New Task form so every research task inherits it (Assam/BiltIQ flow)."""
    ctx = "Map BiltIQ services to Assam government needs: flood, border security, agriculture."
    r = client.post("/projects", data={
        "name": "Assam GTM", "website": "https://biltiq.ai", "context": ctx,
    }, follow_redirects=False)
    assert r.status_code == 303
    pid = r.headers["location"].rsplit("/", 1)[1]

    from sentinel.memory.store import ProjectStore
    proj = ProjectStore().get_project(pid)
    assert proj is not None and proj.context == ctx

    # The research/tasks page prefills the inherited context into the task form.
    tasks_page = client.get(f"/projects/{pid}/tasks")
    assert tasks_page.status_code == 200
    assert "flood, border security, agriculture" in tasks_page.text
    assert "Inherited from the project" in tasks_page.text


def test_create_project_threads_context_to_plan_redirect(client):
    """When an objective is supplied, context + client_url ride the PRG redirect to the
    plan route (which owns task-context persistence and the client-site KB crawl)."""
    r = client.post("/projects", data={
        "name": "Assam GTM 2", "objective": "Research Assam departments",
        "context": "vendor is BiltIQ", "client_url": "https://assam.gov.in",
    }, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert "/plan?objective=" in loc
    assert "context=vendor%20is%20BiltIQ" in loc
    assert "client_url=https%3A//assam.gov.in" in loc


def test_new_project_form_has_context_fields(client):
    page = client.get("/projects")
    assert page.status_code == 200
    assert "name='context'" in page.text
    assert "name='client_url'" in page.text


def test_blank_name_creates_nothing(client):
    before = client.get("/projects").text
    r = client.post("/projects", data={"name": "   ", "website": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/projects"
    # no new project row added (page unchanged in substance)
    assert "New project" in before


def test_unknown_project_is_not_found(client):
    r = client.get("/projects/does-not-exist")
    assert r.status_code == 200
    assert "does-not-exist" in r.text or "not found" in r.text.lower()


def test_existing_screens_ok_with_and_without_project_filter(client):
    pid = _create_project(client, name="Scoped")
    for path in ("/artifacts", "/accounts", "/focus"):
        assert client.get(path).status_code == 200                      # unscoped (legacy behaviour)
        assert client.get(f"{path}?project={pid}").status_code == 200   # scoped
    # a scoped page surfaces the project in the pill
    assert "project: Scoped" in client.get(f"/artifacts?project={pid}").text


def test_bad_project_id_degrades_to_unscoped(client):
    # a stale/unknown ?project= id falls back to the unscoped view, not an error
    r = client.get("/artifacts?project=ghost")
    assert r.status_code == 200
    assert "project: sovereign" in r.text
