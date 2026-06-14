"""Minimal Semantic Memory — extraction + store (Phase 1).

Tests cover:
- MemoryType.SEMANTIC_FACT exists in the enum
- write_semantic_fact persists and list_semantic_facts retrieves
- Dedup: writing same content twice produces one entry
- _persist_run writes product_research winner as a semantic fact
- _persist_run writes govt_proposal summary as a semantic fact
- project_memory_page renders Semantic section as live when facts exist
"""

from __future__ import annotations

import pytest

from sentinel.artifacts.schemas import Boundary, Domain, Persona, Plan, Project, Result, Source, Step, Task
from sentinel.memory.schema import MemoryType
from sentinel.memory.store import MemoryStore
from sentinel.web import render

_NOW = "2026-06-11T00:00:00Z"


def _project() -> Project:
    return Project(id="sem-p1", name="SemanticTest", created_at=_NOW)


def _task(tid="sem-t1") -> Task:
    return Task(id=tid, project_id="sem-p1", objective="Best laptop under 80k",
                domain=Domain(name="product_research"), persona=Persona(), created_at=_NOW)


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #

def test_semantic_fact_in_memory_type_enum():
    assert MemoryType.SEMANTIC_FACT.value == "semantic_fact"


# --------------------------------------------------------------------------- #
# Store: write + list
# --------------------------------------------------------------------------- #

def test_write_and_list_semantic_facts(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = MemoryStore()
    store.write_semantic_fact("proj-1", "Lenovo LOQ", "Winner: Lenovo LOQ — best value at ₹79k", "product_research")
    store.write_semantic_fact("proj-1", "Dell G15", "Good mid-range option", "product_research")

    facts = store.list_semantic_facts("proj-1")
    assert len(facts) == 2
    assert all(f.memory_type == MemoryType.SEMANTIC_FACT for f in facts)
    entities = {f.entity for f in facts}
    assert "lenovo loq" in entities
    assert "dell g15" in entities


def test_list_semantic_facts_scoped_to_project(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = MemoryStore()
    store.write_semantic_fact("proj-A", "EntityA", "Fact for A", "source")
    store.write_semantic_fact("proj-B", "EntityB", "Fact for B", "source")

    facts_a = store.list_semantic_facts("proj-A")
    facts_b = store.list_semantic_facts("proj-B")
    assert len(facts_a) == 1 and facts_a[0].entity == "entitya"
    assert len(facts_b) == 1 and facts_b[0].entity == "entityb"


def test_write_semantic_fact_dedup(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = MemoryStore()
    store.write_semantic_fact("proj-1", "ASUS TUF", "Best budget gaming laptop", "product_research")
    store.write_semantic_fact("proj-1", "ASUS TUF", "Best budget gaming laptop", "product_research")

    facts = store.list_semantic_facts("proj-1")
    assert len(facts) == 1  # deduped by content_hash


def test_list_semantic_facts_empty_project(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    facts = MemoryStore().list_semantic_facts("no-such-project")
    assert facts == []


# --------------------------------------------------------------------------- #
# _persist_run integration
# --------------------------------------------------------------------------- #

def _result_with_payload(payload: dict) -> Result:
    return Result(
        task_id="sem-t1", summary="done", artifacts=list(payload.get("artifacts", {}).keys()),
        citations=[], dashboard_payload=payload,
    )


def test_persist_run_product_research_writes_winner_fact(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import ProjectStore
    from sentinel.web.app import _persist_run

    store = ProjectStore()
    store.save_project(Project(id="sem-p1", name="Test", created_at=_NOW))
    store.save_task(_task())

    payload = {"artifacts": {"product_research": {
        "criteria": "laptop under 80k",
        "one_line_summary": "Lenovo LOQ is the best value buy at ₹79,990.",
        "winner": "Lenovo LOQ",
        "winner_rationale": "Best GPU at this price.",
        "products_found": [],
        "value_ranking": [],
    }}}
    _persist_run(_task(), _result_with_payload(payload), "vllm")

    mem = MemoryStore()
    facts = mem.list_semantic_facts("sem-p1")
    assert any("Lenovo LOQ" in f.content or "lenovo loq" in f.entity for f in facts)


def test_persist_run_govt_proposal_writes_summary_fact(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory.store import ProjectStore
    from sentinel.web.app import _persist_run

    store = ProjectStore()
    store.save_project(Project(id="sem-p1", name="Test", created_at=_NOW))
    gov_task = Task(id="sem-t2", project_id="sem-p1",
                    objective="Propose BiltIQ to Assam Govt",
                    domain=Domain(name="govt_proposal"), persona=Persona(), created_at=_NOW)
    store.save_task(gov_task)

    payload = {"artifacts": {"govt_proposal": {
        "client": "Assam State Government",
        "vendor": "BiltIQ AI",
        "one_line_summary": "BiltIQ delivers sovereign AI for Assam digital services.",
        "executive_summary": "",
        "client_challenges": [],
        "vendor_capabilities": [],
    }}}
    _persist_run(gov_task, _result_with_payload(payload), "vllm")

    facts = MemoryStore().list_semantic_facts("sem-p1")
    assert any("Assam" in f.content or "assam" in f.entity for f in facts)


# --------------------------------------------------------------------------- #
# Render: memory page shows Semantic as live when facts exist
# --------------------------------------------------------------------------- #

def test_memory_page_semantic_live_when_facts_present(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    store = MemoryStore()
    store.write_semantic_fact("sem-p1", "Lenovo LOQ", "Winner at ₹79k", "product_research")
    facts = store.list_semantic_facts("sem-p1")

    html = render.project_memory_page(
        project=_project(), records=[], backend="vllm", semantic_facts=facts,
    )
    assert "Semantic facts" in html          # OD card header rendered
    assert "Winner at" in html               # fact content visible
    assert "live heads" in html              # live-heads pill in header
    assert "badge ok" in html                # fact shown as a live head


def test_memory_page_semantic_empty_when_no_facts():
    html = render.project_memory_page(
        project=_project(), records=[], backend="vllm", semantic_facts=[],
    )
    assert "Semantic facts" in html                     # OD card always present
    assert "No entity facts accumulated yet." in html   # empty state shown
    assert "live heads" not in html                     # no live-heads pill when empty


# --------------------------------------------------------------------------- #
# KB enrichment: plan_review_page renders KB panel when sources are present
# --------------------------------------------------------------------------- #

def test_plan_review_page_shows_kb_panel_with_indexed_source():
    from sentinel.artifacts.schemas import Plan, Step
    from sentinel.agent.orchestrator_planner import PlanProposal

    plan = Plan(id="p1", task_id="t1", steps=[
        Step(id="s1", capability="govt_proposal", output_key="govt_proposal")])
    sources = [
        {"url": "https://biltiq.ai", "source_type": "web", "status": "indexed", "chunk_count": 42},
        {"url": "https://assam.gov.in", "source_type": "web", "status": "crawling", "chunk_count": 0},
    ]
    html = render.plan_review_page(
        task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
        autonomy="propose", backend="vllm", ran=False,
        kb_sources=sources,
    )
    assert "KB context" in html
    assert "biltiq.ai" in html
    assert "assam.gov.in" in html
    assert "42 chunks" in html
    assert "crawling" in html or "indexing" in html
    # auto-reload script injected when any source is still pending/crawling
    assert "setTimeout" in html


def test_plan_review_page_no_kb_panel_when_no_sources():
    from sentinel.artifacts.schemas import Plan, Step
    from sentinel.agent.orchestrator_planner import PlanProposal

    plan = Plan(id="p2", task_id="t1", steps=[
        Step(id="s1", capability="self_profile", output_key="self_profile")])
    html = render.plan_review_page(
        task=_task(), proposal=PlanProposal(plan=plan, created_specs=[]),
        autonomy="propose", backend="vllm", ran=False,
        kb_sources=[],
    )
    assert "KB context" not in html


def test_task_form_contains_client_url_field():
    html = render.project_tasks_page(project=_project(), tasks=[], backend="vllm")
    assert "client_url" in html
    assert "Client" in html or "client" in html
