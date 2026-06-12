"""Persona full-schema profiles (2026-06-12).

Until this change every named persona shipped with the identical professional/neutral/brief
defaults — ``_persona_for`` set only ``name``, so picking "student" changed one word in the
renderer prompt while the docs promised K-12 study guides and nurse checklists. These tests pin:

1. the registry gives every named persona a FULL profile (all Persona fields meaningful);
2. "enterprise" stays byte-equal to ``Persona()`` (dag._finalize_result skips the persona render
   pass on the default — a richer enterprise profile would silently add an LLM call per task);
3. per-task overrides (the form's customise-persona fields = the "custom" path) win field-by-field;
4. the profile actually reaches the renderer prompt and the web form/route.
"""

from __future__ import annotations

from typing import get_args

from fastapi.testclient import TestClient

from sentinel.agent.autonomy import GateOutcome
from sentinel.agent.orchestrator_planner import PlanProposal
from sentinel.agent.persona import persona_profile
from sentinel.artifacts.schemas import PERSONA_PROFILES, Persona, Plan, Step, persona_for
from sentinel.artifacts.schemas import Project
from sentinel.config.schema import PersonaName, ProjectSettings
from sentinel.memory.store import ProjectStore
from sentinel.web import app as web_app
from sentinel.web import render

_NOW = "2026-06-12T00:00:00Z"


# ── registry ──────────────────────────────────────────────────────────────────

def test_every_named_persona_has_a_registry_profile():
    # "custom" is deliberately absent: it starts from defaults + caller overrides.
    named = set(get_args(PersonaName)) - {"custom"}
    assert named == set(PERSONA_PROFILES)


def test_non_enterprise_profiles_are_full_schema():
    defaults = Persona()
    for name, profile in PERSONA_PROFILES.items():
        if name == "enterprise":
            continue
        for field in ("reading_level", "tone", "format", "source_policy"):
            assert profile.get(field), f"{name}.{field} missing — not a full-schema profile"
        # and the profile is actually differentiated, not the do-nothing defaults restated
        assert (profile["tone"], profile["format"]) != (defaults.tone, defaults.format), name


def test_enterprise_profile_keeps_skip_pass_invariant():
    # dag._finalize_result: persona == Persona() → skip the persona render LLM pass.
    assert persona_for("enterprise") == Persona()
    assert PERSONA_PROFILES["enterprise"] == {}


# ── builder ───────────────────────────────────────────────────────────────────

def test_persona_for_builds_full_schema_profiles():
    student = persona_for("student")
    assert "K-12" in student.reading_level
    assert student.tone == "plain"
    assert "study guide" in student.format
    assert student.source_policy  # full schema: source policy populated too

    doctor = persona_for("doctor")
    assert doctor.tone == "clinical"
    assert "peer-reviewed" in (doctor.source_policy or "")


def test_persona_for_unknown_or_blank_degrades_to_enterprise():
    assert persona_for("") == Persona()
    assert persona_for(None) == Persona()
    assert persona_for("hacker'); DROP TABLE--") == Persona()


def test_persona_for_overrides_win_field_by_field():
    # the "custom" path: defaults + whatever the form supplied
    custom = persona_for("custom", reading_level="ELI5", format="comic strip")
    assert custom.name == "custom"
    assert custom.reading_level == "ELI5"
    assert custom.format == "comic strip"
    assert custom.tone == "neutral"  # untouched field keeps the default
    # a NAMED persona customised per task: override wins, rest of profile kept
    nurse = persona_for("nurse", tone="reassuring")
    assert nurse.tone == "reassuring"
    assert "checklist" in nurse.format            # registry profile retained
    assert "clinical-guideline" in (nurse.source_policy or "")


# ── prompt wiring ─────────────────────────────────────────────────────────────

def test_full_profile_reaches_the_renderer_prompt():
    text = persona_profile(persona_for("nurse"))
    assert "nurse reader" in text
    assert "checklist" in text                     # format
    assert "clinical" in text                      # tone / reading level
    assert "source policy" in text                 # source_policy line present


# ── web form + route ──────────────────────────────────────────────────────────

def test_task_form_has_customise_persona_fields():
    html = render._task_form("p-x")
    assert "<option value='custom'>custom</option>" in html
    for field in ("reading_level", "tone", "format", "source_policy"):
        assert f"name='{field}'" in html, field
    assert "id='t-pmap'" in html                   # the JS placeholder-prefill profile map
    assert '"student"' in html and "K-12" in html  # registry profiles embedded for prefill


def test_plan_route_threads_persona_overrides(monkeypatch):
    ProjectStore().save_project(
        Project(id="p-per", name="P", created_at=_NOW, settings=ProjectSettings()))
    seen: dict[str, Persona] = {}

    async def fake_plan_task(task, registry, **kw):
        seen["persona"] = task.persona
        plan = Plan(id=f"plan-{task.id}", task_id=task.id, steps=[
            Step(id="s1", capability="self_profile", output_key="self_profile",
                 agent_spec_id="seed-self_profile-market")])
        return PlanProposal(plan=plan, created_specs=[])

    async def fake_gate(proposal, **kw):
        return GateOutcome(autonomy="propose", proposal=proposal, result=None, ran=False)

    monkeypatch.setattr(web_app, "plan_task", fake_plan_task)
    monkeypatch.setattr(web_app, "gate_proposal", fake_gate)

    # follow_redirects=False: the route PRGs to task_detail, whose stale-plan self-heal would
    # bounce our fake single-step plan back to /plan forever. The capture happens before the 303.
    resp = TestClient(web_app.app).get(
        "/projects/p-per/plan?objective=Study+photosynthesis&domain=academic"
        "&persona=student&tone=encouraging", follow_redirects=False)
    assert resp.status_code == 303
    p = seen["persona"]
    assert p.name == "student"
    assert "K-12" in p.reading_level               # registry profile applied, not bare defaults
    assert p.tone == "encouraging"                 # per-task override won
    assert "study guide" in p.format
