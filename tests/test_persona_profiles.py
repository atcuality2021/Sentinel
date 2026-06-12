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


# ── persona library (PersonaStore + saved-persona resolution) ─────────────────

def _saved(name: str = "CFO brief", **kw):
    from sentinel.artifacts.schemas import SavedPersona
    defaults = dict(id=f"sp-{name.replace(' ', '-')}", name=name,
                    description="finance leadership", reading_level="executive",
                    tone="direct", format="one-page memo with a numbers table",
                    source_policy="audited filings preferred", created_at=_NOW)
    defaults.update(kw)
    return SavedPersona(**defaults)


def test_persona_store_crud(tmp_path):
    from sentinel.memory.store import PersonaStore
    store = PersonaStore(tmp_path / "p.db")
    pid = store.save(_saved())
    assert store.get(pid).name == "CFO brief"
    assert store.get_by_name("cfo BRIEF").id == pid          # case-insensitive lookup
    assert [p.id for p in store.list()] == [pid]
    profiles = store.profiles_by_name()
    assert profiles["cfo brief"]["tone"] == "direct"
    assert store.delete(pid) is True
    assert store.get(pid) is None
    assert store.delete(pid) is False                        # idempotent on the second call


def test_persona_for_resolves_saved_library_profiles():
    extra = {"CFO Brief": {"reading_level": "executive", "tone": "direct",
                           "format": "memo", "source_policy": ""}}
    p = persona_for("cfo brief", extra_profiles=extra)
    assert p.name == "cfo brief"
    assert p.tone == "direct"
    assert p.source_policy is None or p.source_policy == ""  # blank field stays default


def test_saved_override_edits_a_builtin_persona():
    """A saved persona whose name matches an editable built-in OVERRIDES the code default
    (the /personas built-in editor) — full-profile override replaces the registry profile."""
    override = {"student": {"reading_level": "PhD", "tone": "sarcastic",
                            "format": "haiku", "source_policy": "arxiv only"}}
    p = persona_for("student", extra_profiles=override)
    assert p.tone == "sarcastic" and p.reading_level == "PhD"   # override won over the registry


def test_enterprise_override_is_ignored_to_keep_skip_pass_invariant():
    """enterprise must stay == Persona() even if a stray override row exists — otherwise every
    default task silently gains an LLM render pass (dag._finalize_result skip-pass)."""
    bad = {"enterprise": {"reading_level": "PhD", "tone": "x",
                          "format": "y", "source_policy": "z"}}
    assert persona_for("enterprise", extra_profiles=bad) == Persona()


# ── agent auto-selection ──────────────────────────────────────────────────────

def test_auto_persona_name_maps_domains_deterministically():
    from sentinel.artifacts.schemas import DOMAIN_DEFAULT_PERSONA, auto_persona_name
    assert auto_persona_name("academic") == "student"
    assert auto_persona_name("software") == "developer"
    assert auto_persona_name("travel") == "consumer"
    assert auto_persona_name("market") == "enterprise"
    assert auto_persona_name("no-such-domain") == "enterprise"
    # every mapped persona must exist in the registry — a typo here would 404 the profile
    assert set(DOMAIN_DEFAULT_PERSONA.values()) <= set(PERSONA_PROFILES)


def test_plan_route_auto_selects_persona_by_domain(monkeypatch):
    ProjectStore().save_project(
        Project(id="p-auto", name="P", created_at=_NOW, settings=ProjectSettings()))
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

    resp = TestClient(web_app.app).get(
        "/projects/p-auto/plan?objective=Study+photosynthesis&domain=academic&persona=auto",
        follow_redirects=False)
    assert resp.status_code == 303
    p = seen["persona"]
    assert p.name == "student"                     # academic → student via the domain map
    assert p.auto_selected is True                 # marked so the UI can say "(auto)"
    assert "K-12" in p.reading_level               # full registry profile, not name-only


def test_plan_route_resolves_saved_persona(monkeypatch):
    from sentinel.memory.store import PersonaStore
    PersonaStore().save(_saved())                  # default db = isolated SENTINEL_DATA_DIR
    ProjectStore().save_project(
        Project(id="p-lib", name="P", created_at=_NOW, settings=ProjectSettings()))
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

    resp = TestClient(web_app.app).get(
        "/projects/p-lib/plan?objective=Compare+vendors&domain=market&persona=CFO+brief",
        follow_redirects=False)
    assert resp.status_code == 303
    p = seen["persona"]
    assert p.name == "cfo brief"                   # persona_for lowercases for resolution
    assert p.tone == "direct"                      # the SAVED profile, not enterprise fallback
    assert p.auto_selected is False


# ── /personas page + CRUD routes ──────────────────────────────────────────────

def test_personas_page_lists_builtins_and_saved():
    from sentinel.memory.store import PersonaStore
    PersonaStore().save(_saved())
    resp = TestClient(web_app.app).get("/personas")
    assert resp.status_code == 200
    html = resp.text
    assert "CFO brief" in html and "one-page memo" in html   # saved card
    for name in PERSONA_PROFILES:                            # built-in read-only cards
        assert f"<b>{name}</b>" in html
    assert "/personas/generate" in html                      # generator form present


def test_personas_create_and_delete_roundtrip():
    from sentinel.memory.store import PersonaStore
    client = TestClient(web_app.app)
    resp = client.post("/personas/create", data={
        "name": "Plant Manager", "description": "factory ops lead",
        "reading_level": "professional (operations)", "tone": "direct",
        "format": "shift-ready checklist", "source_policy": ""},
        follow_redirects=False)
    assert resp.status_code == 303 and "ok=" in resp.headers["location"]
    saved = PersonaStore().get_by_name("plant manager")
    assert saved is not None and saved.format == "shift-ready checklist"
    assert saved.source_policy is None                       # blank input → None, not ""

    resp = client.post(f"/personas/{saved.id}/delete", follow_redirects=False)
    assert resp.status_code == 303 and "ok=" in resp.headers["location"]
    assert PersonaStore().get(saved.id) is None


def test_personas_create_rejects_reserved_and_blank_names():
    client = TestClient(web_app.app)
    # Only enterprise + the two form sentinels are reserved now; the other built-ins are editable.
    for bad in ("enterprise", "AUTO", "custom", "   "):
        resp = client.post("/personas/create", data={"name": bad}, follow_redirects=False)
        assert resp.status_code == 303 and "err=" in resp.headers["location"], bad
    from sentinel.memory.store import PersonaStore
    assert PersonaStore().list() == []                       # nothing slipped through


def test_personas_generate_prefills_create_form(monkeypatch):
    import litellm
    from types import SimpleNamespace

    async def fake_acompletion(**kw):
        content = ('{"reading_level": "executive", "tone": "direct", '
                   '"format": "one-page memo", "source_policy": "audited filings"}')
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=content))])

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    resp = TestClient(web_app.app).post(
        "/personas/generate", data={"description": "a CFO comparing vendors", "name": "CFO"},
        follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert "gen_rl=executive" in loc and "gen_tone=direct" in loc
    assert "gen_name=CFO" in loc
    # and the page actually prefills the form from those params
    page = TestClient(web_app.app).get(loc)
    assert "value='executive'" in page.text and "value='direct'" in page.text


def test_personas_generate_fails_soft(monkeypatch):
    import litellm

    async def boom(**kw):
        raise RuntimeError("backend down")

    monkeypatch.setattr(litellm, "acompletion", boom)
    resp = TestClient(web_app.app).post(
        "/personas/generate", data={"description": "anything"}, follow_redirects=False)
    assert resp.status_code == 303 and "err=" in resp.headers["location"]


# ── task-form integration ─────────────────────────────────────────────────────

def test_task_form_defaults_to_auto_and_lists_saved_personas():
    html = render._task_form("p-x", saved_personas=[_saved()])
    assert "<option value='auto' selected>auto — let the agent pick</option>" in html
    assert "<option value='CFO brief'>CFO brief</option>" in html
    assert html.index("value='auto'") < html.index("value='enterprise'")  # auto is FIRST
    assert html.rindex("value='custom'") > html.index("value='CFO brief'")  # custom stays LAST
    assert '"CFO brief"' in html                   # saved profile embedded in the prefill map
    assert "(agent picks by domain)" in html       # the auto explainer placeholders


def test_profile_map_json_is_script_safe():
    # Stored-XSS guard: user-controlled values inside <script type='application/json'> must
    # never contain a literal "<" (a "</script>" in a saved field would close the block early).
    evil = {"</script><img src=x onerror=alert(1)>": {
        "reading_level": "</script>", "tone": "<!--", "format": "x", "source_policy": ""}}
    blob = render._persona_profile_map_json(evil)
    assert "<" not in blob
    import json as _json
    parsed = _json.loads(blob)                     # < round-trips to the same JSON value
    assert "</script><img src=x onerror=alert(1)>" in parsed


def test_personas_create_rejects_markup_in_names():
    client = TestClient(web_app.app)
    resp = client.post("/personas/create", data={"name": "</script><b>x"},
                       follow_redirects=False)
    assert resp.status_code == 303 and "err=" in resp.headers["location"]
    from sentinel.memory.store import PersonaStore
    assert PersonaStore().list() == []


def test_persona_pill_marks_auto_selected():
    auto = persona_for("student")
    auto.auto_selected = True
    assert "(auto)" in render._persona_label(auto)
    assert "(auto)" not in render._persona_label(persona_for("student"))


# ── built-in persona CRUD (override model, 2026-06-12) ────────────────────────

def test_create_route_allows_builtin_name_as_override():
    """Saving a built-in's name (except enterprise) is now allowed — it creates an override."""
    from sentinel.memory.store import PersonaStore
    client = TestClient(web_app.app)
    resp = client.post("/personas/create",
                       data={"name": "developer", "reading_level": "PhD", "tone": "snarky",
                             "format": "haiku", "source_policy": "arxiv"},
                       follow_redirects=False)
    assert resp.status_code == 303 and "ok=" in resp.headers["location"]
    ov = PersonaStore().get_by_name("developer")
    assert ov is not None and ov.reading_level == "PhD"
    # and it resolves ahead of the code default
    assert persona_for("developer", extra_profiles=PersonaStore().profiles_by_name()).tone == "snarky"


def test_create_route_still_blocks_enterprise_and_sentinels():
    from sentinel.memory.store import PersonaStore
    client = TestClient(web_app.app)
    for name in ("enterprise", "auto", "custom"):
        resp = client.post("/personas/create", data={"name": name}, follow_redirects=False)
        assert resp.status_code == 303 and "err=" in resp.headers["location"], name
    assert PersonaStore().list() == []


def test_create_route_edits_in_place_no_duplicate_rows():
    """Re-saving the same name replaces the row instead of stacking duplicates."""
    from sentinel.memory.store import PersonaStore
    client = TestClient(web_app.app)
    client.post("/personas/create", data={"name": "developer", "tone": "v1"}, follow_redirects=False)
    client.post("/personas/create", data={"name": "developer", "tone": "v2"}, follow_redirects=False)
    rows = [p for p in PersonaStore().list() if p.name.lower() == "developer"]
    assert len(rows) == 1 and rows[0].tone == "v2"


def test_reset_builtin_override_via_delete_restores_default():
    from sentinel.memory.store import PersonaStore
    client = TestClient(web_app.app)
    client.post("/personas/create", data={"name": "developer", "tone": "snarky"}, follow_redirects=False)
    ov = PersonaStore().get_by_name("developer")
    client.post(f"/personas/{ov.id}/delete", follow_redirects=False)
    assert PersonaStore().get_by_name("developer") is None         # override gone
    assert persona_for("developer").tone == "technical"            # code default restored


def test_builtin_card_shows_edit_and_overridden_controls():
    from sentinel.artifacts.schemas import SavedPersona
    ov = SavedPersona(id="ov1", name="developer", description="my devs",
                      reading_level="PhD", tone="snarky", format="haiku",
                      source_policy="arxiv", created_at=_NOW)
    html = render.personas_page([ov], backend="vllm", builtin_overrides={"developer": ov})
    assert ">Edit<" in html
    assert "Reset to default" in html and "/personas/ov1/delete" in html
    assert "overridden" in html
    # enterprise must remain read-only (no Edit affordance on its card row)
    assert "enterprise" in html and "kept read-only" in html


def test_overridden_builtin_not_duplicated_in_task_form():
    from sentinel.artifacts.schemas import SavedPersona
    ov = SavedPersona(id="ov2", name="developer", reading_level="PhD", tone="snarky",
                      format="haiku", source_policy="arxiv", created_at=_NOW)
    form = render._task_form("proj1", saved_personas=[ov])
    assert form.count("value='developer'") == 1


def test_builtin_override_not_listed_in_saved_section():
    """An override shows on its built-in card only — not duplicated as a 'Saved personas' card."""
    from sentinel.artifacts.schemas import SavedPersona
    ov = SavedPersona(id="ov3", name="developer", reading_level="PhD", tone="snarky",
                      format="haiku", source_policy="arxiv", created_at=_NOW)
    lib = SavedPersona(id="lib1", name="CFO brief", reading_level="executive", tone="direct",
                       format="memo", source_policy=None, created_at=_NOW)
    html = render.personas_page([ov, lib], backend="vllm", builtin_overrides={"developer": ov})
    saved_section = html.split("Built-in personas")[0]
    assert "CFO brief" in saved_section                  # genuine library persona listed
    assert saved_section.count("/personas/ov3/delete") == 0   # override NOT in saved section
    assert "/personas/ov3/delete" in html               # but its Reset (delete) IS on the built-in card
