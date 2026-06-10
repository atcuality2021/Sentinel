"""SENTINEL-012 — UI gap closures verified during the live e2e: a task-create form on the project
detail page (the missing door to the planner) and the orchestrated Result rendered inline + persisted
to the RunStore (so a run is no longer ephemeral and '/artifacts' is no longer empty)."""

from __future__ import annotations

from sentinel.artifacts.schemas import (
    Boundary, Domain, Persona, Plan, Project, Result, Source, Step, Task,
)
from sentinel.memory.store import RunStore
from sentinel.web import render

_NOW = "2026-06-08T00:00:00Z"
_PUB = Source(boundary=Boundary.PUBLIC, label="biltiq.ai", url="https://biltiq.ai")


def _project() -> Project:
    return Project(id="p1", name="BiltIQ", website="https://biltiq.ai", created_at=_NOW)


def _task() -> Task:
    return Task(id="t1", project_id="p1", objective="Profile us and strategize",
                domain=Domain(name="market"), persona=Persona(), created_at=_NOW)


# --------------------------------------------------------------------------- #
# Gap 1: the project detail page exposes a task → planner form
# --------------------------------------------------------------------------- #


def test_project_detail_page_has_a_task_form():
    # Overview page links to the Research tab; the actual form lives on project_tasks_page.
    overview = render.project_detail_page(project=_project(), tasks=[], backend="vllm")
    assert "/projects/p1/tasks" in overview     # CTA button points to Research tab
    assert "New Research Task" in overview      # action label present

    # Research tab carries the full planner form.
    tasks_html = render.project_tasks_page(project=_project(), tasks=[], backend="vllm")
    assert "/projects/p1/plan" in tasks_html    # form targets the planner route
    assert "name='objective'" in tasks_html     # objective field
    assert "name='domain'" in tasks_html        # domain selector
    assert "Plan task" in tasks_html            # submit control
    assert "New task" in tasks_html


# --------------------------------------------------------------------------- #
# Gap 2a: an orchestrated Result renders inline on the run-complete page
# --------------------------------------------------------------------------- #


def _result(*, degraded=False) -> Result:
    return Result(
        task_id="t1", summary="produced 1 artifact(s) — self_profile",
        artifacts=["self_profile"], citations=[_PUB],
        dashboard_payload={"artifacts": {"self_profile": {"org": "BiltIQ", "sources": [_PUB.model_dump()]}}},
        degraded=degraded,
    )


def test_plan_review_page_renders_result_inline_when_ran():
    plan = Plan(id="pl", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile",
             agent_spec_id="seed-self_profile-market")])
    from sentinel.agent.orchestrator_planner import PlanProposal

    html = render.plan_review_page(
        task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
        autonomy="autonomous", backend="vllm", ran=True, result=_result(),
    )
    assert "Result" in html                                 # the result section header
    assert "produced 1 artifact" in html                    # the summary
    assert "self_profile" in html                           # the artifact block
    assert "biltiq.ai" in html                              # the citation
    assert "Citations (1)" in html
    assert "View results" not in html                       # the dead link is gone


def test_plan_review_ran_without_result_does_not_crash():
    plan = Plan(id="pl", task_id="t1", steps=[Step(id="s1", capability="self_profile",
                                                   output_key="self_profile")])
    from sentinel.agent.orchestrator_planner import PlanProposal

    html = render.plan_review_page(task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy="autonomous", backend="vllm", ran=True, result=None)
    assert "Plan review" in html                            # renders fine with no result


# --------------------------------------------------------------------------- #
# Gap 2b: the orchestrated Result is persisted to the RunStore (no schema change)
# --------------------------------------------------------------------------- #


def test_persist_run_writes_a_scoped_runrecord(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.web.app import _persist_run

    _persist_run(_task(), _result(degraded=True), "vllm")
    runs = RunStore().runs_for("profile us and strategize")  # entity is the normalised objective
    assert len(runs) == 1
    rec = runs[0]
    assert rec.project_id == "p1"
    assert rec.public == 1 and rec.private == 0              # one public citation
    assert rec.backend == "vllm"
    assert "self_profile" in rec.reference                  # the artifact ref is recorded


# --------------------------------------------------------------------------- #
# HIGH-05: domain artifacts auto-populate entity_relations so get_related() is
# non-empty on subsequent runs (knowledge graph warm-up).
# --------------------------------------------------------------------------- #


def _domain_result(art_key: str, art_data: dict) -> Result:
    return Result(
        task_id="t1", summary=f"produced 1 artifact(s) — {art_key}",
        artifacts=[art_key], citations=[],
        dashboard_payload={"artifacts": {art_key: art_data}},
        degraded=False,
    )


def test_persist_run_finance_writes_profile_relation(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import MemoryStore
    from sentinel.web.app import _persist_run

    _persist_run(_task(), _domain_result("finance", {"target": "HDFC Bank"}), "gemini")
    rels = MemoryStore().get_related("HDFC Bank")
    assert any(r.rel_type == "finance_profile" for r in rels)


def test_persist_run_software_writes_profile_and_competitor_relations(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import MemoryStore
    from sentinel.web.app import _persist_run

    art = {"target": "ChromaDB", "alternatives": ["Weaviate", "Pinecone"]}
    _persist_run(_task(), _domain_result("software", art), "gemini")
    rels = MemoryStore().get_related("ChromaDB")
    rel_types = {r.rel_type for r in rels}
    assert "software_profile" in rel_types
    assert "competitor" in rel_types
    rivals = {r.to_entity for r in rels if r.rel_type == "competitor"}
    assert "weaviate" in rivals or "Weaviate" in rivals
    assert "pinecone" in rivals or "Pinecone" in rivals


def test_persist_run_software_self_alternative_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import MemoryStore
    from sentinel.web.app import _persist_run

    art = {"target": "ChromaDB", "alternatives": ["ChromaDB", "Weaviate"]}
    _persist_run(_task(), _domain_result("software", art), "gemini")
    rels = MemoryStore().get_related("ChromaDB")
    rivals = [r.to_entity for r in rels if r.rel_type == "competitor"]
    assert not any(r.lower() == "chromadb" for r in rivals)


def test_persist_run_academic_writes_profile_relation(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import MemoryStore
    from sentinel.web.app import _persist_run

    _persist_run(_task(), _domain_result("academic", {"topic": "quantum entanglement"}), "gemini")
    rels = MemoryStore().get_related("quantum entanglement")
    assert any(r.rel_type == "academic_profile" for r in rels)


def test_persist_run_domain_missing_entity_field_skips_silently(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import MemoryStore
    from sentinel.web.app import _persist_run

    _persist_run(_task(), _domain_result("finance", {"other_field": "x"}), "gemini")
    rels = MemoryStore().get_related("x")
    assert rels == []
