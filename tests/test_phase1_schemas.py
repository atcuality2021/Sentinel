"""SENTINEL-012 Phase 1 Step 3 — core orchestration-layer schemas.

Hermetic: pure pydantic construction/round-trip + the high-stakes domain gate. No LLM/network.
Test IDs → spec ACs: AC-1 (project/task model), AC-2 (plan/agent-spec model), AC-14 (high-stakes gate).
"""

from __future__ import annotations

import pytest

from sentinel.artifacts.schemas import (
    KNOWN_OUTPUT_SCHEMAS,
    AgentSpec,
    ComparisonAxis,
    ComparisonMatrix,
    Domain,
    GradeReport,
    Persona,
    Plan,
    Project,
    ProgramStrategy,
    Result,
    RubricScore,
    SelfProfile,
    Step,
    Task,
    is_high_stakes,
)
from sentinel.config.schema import ProjectSettings


# --- AC-1: Project / Task round-trip ------------------------------------------------------ #


def test_project_and_task_round_trip():
    proj = Project(id="p1", name="BiltIQ", website="https://biltiq.ai", created_at="2026-06-08T00:00:00Z")
    assert proj.settings.autonomy == "propose"  # safe default (AC-13)
    assert Project.model_validate(proj.model_dump()) == proj

    task = Task(
        id="t1", project_id="p1", objective="map products vs rivals",
        domain=Domain(name="market"), persona=Persona(name="enterprise"),
        created_at="2026-06-08T00:00:00Z",
    )
    assert task.status == "created"
    assert Task.model_validate(task.model_dump()) == task


def test_project_settings_inherit_when_none():
    s = ProjectSettings()
    assert s.backend_pref is None and s.compliance is None  # None ⇒ inherit global config


# --- AC-2: Plan / Step / AgentSpec model -------------------------------------------------- #


def test_plan_step_round_trip():
    plan = Plan(
        id="pl1", task_id="t1",
        steps=[
            Step(id="s1", capability="self_profile", output_key="self_profile"),
            Step(id="s2", capability="compare", depends_on=["s1"], output_key="comparison"),
        ],
    )
    assert plan.status == "proposed"
    assert plan.steps[1].depends_on == ["s1"]
    assert Plan.model_validate(plan.model_dump()) == plan


def test_agent_spec_carries_reuse_keys():
    spec = AgentSpec(
        id="a1", name="self-profiler", capability="self_profile", domain="market",
        role="synthesizer", skill_prompt="profile our products",
        output_schema_ref="SelfProfile", version=2, eval_score=0.91,
    )
    assert spec.origin == "registry" and spec.active is True
    assert spec.output_schema_ref in KNOWN_OUTPUT_SCHEMAS
    assert AgentSpec.model_validate(spec.model_dump()) == spec


def test_rubric_score_bounds_enforced():
    RubricScore(relevance=5, faithfulness=4, completeness=3, actionability=2, persona_fit=1, justification="ok")
    with pytest.raises(Exception):
        RubricScore(relevance=6, faithfulness=4, completeness=3, actionability=2, persona_fit=1, justification="x")


# --- AC-14: high-stakes domain gate ------------------------------------------------------- #


@pytest.mark.parametrize("name", ["medicine", "Clinical Research", "med-device", "legal", "Health-Tech", "drug-discovery"])
def test_high_stakes_domains_recognised(name):
    assert is_high_stakes(name) is True


@pytest.mark.parametrize("name", ["market", "food", "software", "academic", "legalese-checker", "healthy-snacks-b2c"])
def test_standard_domains_not_flagged(name):
    # token-level match: "legalese"/"healthy" are not the markers "legal"/"health"
    assert is_high_stakes(name) is False


# --- value-chain + eval schemas validate -------------------------------------------------- #


def test_value_chain_schemas_construct():
    SelfProfile(org="BiltIQ")
    ComparisonMatrix(
        subject="ATC Manthan", rival="Glean",
        axes=[ComparisonAxis(axis="pricing", ours="flat", theirs="per-seat", verdict="win")],
    )
    ProgramStrategy(assessment="strong in sovereignty", ran_on_partial_data=True)
    GradeReport(passed=False, hard_failures=["schema_valid"], checks={"schema_valid": False})
    Result(task_id="t1", summary="done", degraded=True, missing_inputs=["s3"])


# --- CRITICAL-01/02 wiring: user_id and handoff_id on Task -------------------------------- #


def test_task_user_id_and_handoff_id_round_trip():
    """Task serialises user_id and handoff_id; model_validate restores them exactly (G-14/G-17)."""
    task = Task(
        id="t2", project_id="p1", objective="HDFC Bank credit risk",
        domain=Domain(name="finance"), created_at="2026-06-10T00:00:00Z",
        user_id="credit-analyst-01", handoff_id="abc123",
    )
    restored = Task.model_validate(task.model_dump())
    assert restored.user_id == "credit-analyst-01"
    assert restored.handoff_id == "abc123"


def test_task_user_id_handoff_id_default_none():
    """Existing Task rows without user_id/handoff_id deserialise with None — backward compat."""
    task = Task(
        id="t3", project_id="p1", objective="legacy task",
        domain=Domain(name="market"), created_at="2026-06-10T00:00:00Z",
    )
    assert task.user_id is None
    assert task.handoff_id is None
    # A JSON payload that predates these fields also deserialises cleanly.
    old_json = '{"id":"t3","project_id":"p1","objective":"legacy","domain":{"name":"market"},' \
               '"created_at":"2026-06-10T00:00:00Z"}'
    import json
    restored = Task.model_validate(json.loads(old_json))
    assert restored.user_id is None
    assert restored.handoff_id is None
