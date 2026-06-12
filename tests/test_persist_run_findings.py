"""Tests for _extract_finding_texts — the bug was that _persist_run never set finding_texts,
so every task-based RunRecord had finding_texts=[] regardless of artifact content."""
from __future__ import annotations

from types import SimpleNamespace


def _make_result(citations=None, payload=None, persona_rendered="", summary=""):
    from sentinel.artifacts.schemas import Result
    return Result(
        task_id="t1",
        citations=citations or [],
        dashboard_payload=payload or {},
        persona_rendered=persona_rendered,
        summary=summary,
    )


def _ft(result):
    from sentinel.web.app import _extract_finding_texts
    return _extract_finding_texts(result)


# --------------------------------------------------------------------------- #
# Empty / degenerate inputs
# --------------------------------------------------------------------------- #

def test_empty_result_returns_empty_list():
    result = _make_result()
    assert _ft(result) == []


def test_no_artifacts_in_payload_returns_empty():
    result = _make_result(payload={"other": "data"})
    assert _ft(result) == []


# --------------------------------------------------------------------------- #
# Citation-level text
# --------------------------------------------------------------------------- #

def test_citations_without_text_field_return_no_findings():
    # Source schema has no text field — citations alone produce no finding texts.
    # Content comes from dashboard_payload instead.
    from sentinel.artifacts.schemas import Boundary, Source
    cit = Source(label="web", url="https://example.com", boundary=Boundary.PUBLIC)
    result = _make_result(citations=[cit])
    assert _ft(result) == []


# --------------------------------------------------------------------------- #
# dashboard_payload — artifacts dict
# --------------------------------------------------------------------------- #

def test_top_level_description_field_extracted():
    payload = {"artifacts": {"self_profile": {"description": "A B2B SaaS competitive intelligence platform."}}}
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert "A B2B SaaS competitive intelligence platform." in texts


def test_positioning_field_extracted():
    payload = {"artifacts": {"competitor": {"positioning": "Market leader in CI for revenue teams."}}}
    result = _make_result(payload=payload)
    assert "Market leader in CI for revenue teams." in _ft(result)


def test_list_text_field_strengths_extracted():
    payload = {"artifacts": {"competitor": {"strengths": ["Fast search", "Integrates with Salesforce"]}}}
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert "Fast search" in texts
    assert "Integrates with Salesforce" in texts


def test_nested_products_description_extracted():
    payload = {
        "artifacts": {
            "self_profile": {
                "org": "Crayon",
                "products": [
                    {
                        "name": "Crayon CI",
                        "description": "Tracks competitor moves in real time.",
                        "strengths": ["Real-time alerts", "CRM sync"],
                    }
                ],
            }
        }
    }
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert "Tracks competitor moves in real time." in texts
    assert "Real-time alerts" in texts
    assert "CRM sync" in texts


def test_dict_items_in_list_text_field_extracted():
    payload = {
        "artifacts": {
            "software": {
                "key_findings": [
                    {"text": "Raised $100M Series C in 2024."},
                    {"text": "Expanding to APAC market."},
                ]
            }
        }
    }
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert "Raised $100M Series C in 2024." in texts
    assert "Expanding to APAC market." in texts


def test_empty_strings_filtered_out():
    payload = {"artifacts": {"profile": {"description": "", "positioning": "  "}}}
    result = _make_result(payload=payload)
    assert _ft(result) == []


def test_non_dict_artifact_skipped():
    payload = {"artifacts": {"bad": "just a string"}}
    result = _make_result(payload=payload)
    assert _ft(result) == []


def test_multiple_artifacts_all_collected():
    payload = {
        "artifacts": {
            "profile_a": {"description": "First artifact content."},
            "profile_b": {"positioning": "Second artifact content."},
        }
    }
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert "First artifact content." in texts
    assert "Second artifact content." in texts


# --------------------------------------------------------------------------- #
# Real-world shape: Crayon self_profile partial run
# --------------------------------------------------------------------------- #

def test_crayon_self_profile_shape_extracts_content():
    payload = {
        "artifacts": {
            "self_profile": {
                "org": "Crayon",
                "products": [
                    {
                        "name": "Crayon Competitive Intelligence Platform",
                        "category": "Competitive Intelligence Software",
                        "positioning": "A comprehensive platform designed to help B2B revenue teams.",
                        "strengths": [
                            "Comprehensive market movement tracking",
                            "Actionable insights for revenue teams",
                        ],
                    }
                ],
                "sources": [],
                "gaps": [],
            }
        }
    }
    result = _make_result(payload=payload)
    texts = _ft(result)
    assert len(texts) > 0
    assert any("B2B revenue teams" in t for t in texts)
    assert "Comprehensive market movement tracking" in texts


# --------------------------------------------------------------------------- #
# _persist_run account entity — sentences are not organisations
# --------------------------------------------------------------------------- #

def _persist(task_objective, payload, project_name="Laptop Project", domain="product_research"):
    from sentinel.artifacts.schemas import Domain, Persona, Project, Task
    from sentinel.memory.store import ProjectStore, RunStore
    from sentinel.web.app import _persist_run

    now = "2026-06-12T00:00:00Z"
    store = ProjectStore()
    store.save_project(Project(id="p-ent", name=project_name, created_at=now))
    task = Task(id="t-ent", project_id="p-ent", objective=task_objective,
                domain=Domain(name=domain), persona=Persona(), created_at=now)
    _persist_run(task, _make_result(payload=payload), backend="vllm")
    recs = RunStore().all()
    return recs[-1] if not hasattr(recs, "keys") else recs


def test_entity_prefers_extracted_org():
    rec = _persist("Profile us vs Crayon",
                   {"artifacts": {"self_profile": {"org": "BiltIQ AI"}}}, domain="market")
    assert rec.entity.lower() == "biltiq ai"   # RunStore normalises case


def test_entity_without_org_falls_back_to_project_name_not_objective():
    """A product-research objective is a sentence, not an organisation — it must never become an
    'account'. The Accounts/focus pages were a junk list of full objectives (e2e audit 2026-06-12)."""
    obj = "i want new laptop under 500000 inr with atleast 42 gb ram"
    rec = _persist(obj, {"artifacts": {"product_research": {"products": []}}})
    assert rec.entity.lower() == "laptop project"  # the project, not the sentence
    assert rec.entity.lower() != obj.lower()


def test_entity_org_equal_to_objective_is_rejected():
    # an upstream extractor that "extracted" the whole objective is the same junk in disguise
    obj = "research the best laptops in india"
    rec = _persist(obj, {"artifacts": {"x": {"org": obj}}})
    assert rec.entity.lower() == "laptop project"
