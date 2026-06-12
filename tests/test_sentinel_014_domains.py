"""SENTINEL-014 — universal domain specialists: software, finance, academic, nutrition, travel.

Hermetic: no network/secrets — offline construction + FakeRunner execution.
Each domain is verified to:
  (a) be registered in SKILL_SPECS under the correct capability/domain key
  (b) follow plan→research(search)→synthesize topology with no private boundary
  (c) build under sovereign role-tiering (zero Gemini objects under on_prem_required)
  (d) keep the synthesizer tool-free (reasoner role)
  (e) produce a schema-valid artifact through run_step
  (f) carry extractor_key/extractor_name for two-tier eligibility
  (g) appear in KNOWN_OUTPUT_SCHEMAS so the planner can staff them
"""

from __future__ import annotations

import asyncio

import pytest
from google.adk.agents.run_config import StreamingMode

from sentinel.agent import orchestrator as orch
from sentinel.agent.modes.spec import (
    ACADEMIC_SPEC,
    FINANCE_SPEC,
    NUTRITION_SPEC,
    SKILL_SPECS,
    SOFTWARE_SPEC,
    TRAVEL_SPEC,
    build_step_agents,
)
from sentinel.artifacts.schemas import (
    KNOWN_OUTPUT_SCHEMAS,
    AcademicBrief,
    Boundary,
    FinancialProfile,
    Finding,
    NutritionBrief,
    SoftwareBrief,
    Source,
    TravelBrief,
)
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption

# ── helpers ──────────────────────────────────────────────────────────────────

_ALL_SPECS = [SOFTWARE_SPEC, FINANCE_SPEC, ACADEMIC_SPEC, NUTRITION_SPEC, TRAVEL_SPEC]
_DOMAIN_MAP = {
    "software": SOFTWARE_SPEC,
    "finance": FINANCE_SPEC,
    "academic": ACADEMIC_SPEC,
    "nutrition": NUTRITION_SPEC,
    "travel": TRAVEL_SPEC,
}


def _tiered_cfg():
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "extractor": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


# ── (a) registration ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("capability,domain,spec", [
    ("software", "software", SOFTWARE_SPEC),
    ("finance", "finance", FINANCE_SPEC),
    ("academic", "academic", ACADEMIC_SPEC),
    ("nutrition", "nutrition", NUTRITION_SPEC),
    ("travel", "travel", TRAVEL_SPEC),
])
def test_registered_in_skill_specs(capability, domain, spec):
    assert SKILL_SPECS[capability] is spec
    assert spec.capability == capability
    assert spec.domain == domain


# ── (b) topology ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("spec", _ALL_SPECS)
def test_topology_plan_research_synthesize(spec):
    roles = [s.role for s in spec.steps]
    assert roles == ["plan", "research", "synthesize"], f"{spec.name}: bad topology {roles}"
    tools = [s.tool for s in spec.steps]
    assert tools == [None, "search", None], f"{spec.name}: bad tool wiring {tools}"
    assert spec.has_private is False


# ── (c) sovereign build (zero Gemini under on_prem_required) ─────────────────

@pytest.mark.parametrize("spec", _ALL_SPECS)
def test_sovereign_build_zero_gemini(spec):
    cfg = _tiered_cfg()
    agents = build_step_agents(spec, cfg, cloud_allowed=False)
    for agent in agents:
        model = getattr(agent, "model", None) or ""
        assert "gemini" not in str(model).lower(), (
            f"{spec.name}/{agent.name}: Gemini object present under on_prem_required"
        )


# ── (d) synthesizer is tool-free ─────────────────────────────────────────────

@pytest.mark.parametrize("spec", _ALL_SPECS)
def test_synthesizer_is_tool_free(spec):
    cfg = _tiered_cfg()
    agents = build_step_agents(spec, cfg, cloud_allowed=False)
    synth = agents[-1]  # synthesizer is always last
    tools = getattr(synth, "tools", None) or []
    assert not tools, f"{spec.name}: synthesizer '{synth.name}' has tools {tools}"


# ── (e) schema-valid artifact via FakeRunner ─────────────────────────────────

def _fake_software() -> dict:
    src = Source(boundary=Boundary.PUBLIC, label="GitHub", url="https://github.com/example/repo")
    return SoftwareBrief(
        target="ExampleLib",
        one_line_summary="A fast async HTTP client library.",
        category="HTTP client",
        tech_stack=[Finding(text="Written in Python 3.11.", source=src)],
        community_health=[Finding(text="12k GitHub stars, 200 contributors.", source=src)],
        sources=[src],
    ).model_dump()


def _fake_finance() -> dict:
    src = Source(boundary=Boundary.PUBLIC, label="Reuters", url="https://reuters.com/example")
    return FinancialProfile(
        target="ExampleCorp",
        one_line_summary="Mid-cap FMCG with stable margins.",
        financial_summary="Revenue ₹500 Cr, 12% YoY growth, EBITDA 18%.",
        key_metrics=[Finding(text="Revenue ₹500 Cr FY26.", source=src)],
        sources=[src],
    ).model_dump()


def _fake_academic() -> dict:
    src = Source(boundary=Boundary.PUBLIC, label="Nature 2024", url="https://nature.com/example")
    return AcademicBrief(
        topic="transformer attention mechanisms",
        one_line_summary="Self-attention is well-studied; linear-attention scaling is open.",
        topic_overview="Transformers use scaled dot-product attention. Flash-Attention improves speed.",
        key_findings=[Finding(text="Flash-Attention reduces memory by 10x (Dao et al. 2022).", source=src)],
        sources=[src],
    ).model_dump()


def _fake_nutrition() -> dict:
    src = Source(boundary=Boundary.PUBLIC, label="PubMed 2023", url="https://pubmed.ncbi.nlm.nih.gov/example")
    return NutritionBrief(
        topic="omega-3 fatty acids",
        one_line_summary="Strong evidence for cardiovascular benefit at ≥1g EPA+DHA/day.",
        evidence_quality="strong RCT evidence",
        key_claims=[Finding(text="1g EPA+DHA reduces triglycerides by ~15%.", source=src)],
        sources=[src],
    ).model_dump()


def _fake_travel() -> dict:
    src = Source(boundary=Boundary.PUBLIC, label="Lonely Planet", url="https://lonelyplanet.com/japan")
    return TravelBrief(
        destination="Kyoto, Japan",
        one_line_summary="Historic city with 17 UNESCO sites; best in spring and autumn.",
        destination_overview="Former imperial capital; dense with temples, shrines, and traditional culture.",
        highlights=[Finding(text="Fushimi Inari shrine: thousands of torii gates.", source=src)],
        best_time="Mar–May, Oct–Nov",
        budget_range="₹8,000–15,000/day",
        sources=[src],
    ).model_dump()


_FAKE_OUTPUTS = {
    "software": _fake_software,
    "finance": _fake_finance,
    "academic": _fake_academic,
    "nutrition": _fake_nutrition,
    "travel": _fake_travel,
}


@pytest.mark.parametrize("capability,schema_cls", [
    ("software", SoftwareBrief),
    ("finance", FinancialProfile),
    ("academic", AcademicBrief),
    ("nutrition", NutritionBrief),
    ("travel", TravelBrief),
])
def test_artifact_is_schema_valid(capability, schema_cls):
    """FakeRunner injects the artifact dict; schema_cls.model_validate must not raise."""
    artifact_dict = _FAKE_OUTPUTS[capability]()
    validated = schema_cls.model_validate(artifact_dict)
    assert validated is not None


@pytest.mark.parametrize("spec,fake_key,output_key", [
    (SOFTWARE_SPEC, "software", "software_brief"),
    (FINANCE_SPEC, "finance", "financial_profile"),
    (ACADEMIC_SPEC, "academic", "academic_brief"),
    (NUTRITION_SPEC, "nutrition", "nutrition_brief"),
    (TRAVEL_SPEC, "travel", "travel_brief"),
])
def test_run_step_produces_valid_artifact(spec, fake_key, output_key, monkeypatch):
    fake_output = _FAKE_OUTPUTS[fake_key]()

    class FakeSession:
        def __init__(self, state):
            self.id = "s1"
            self.state = dict(state)

    class FakeSvc:
        def __init__(self):
            self._s: FakeSession | None = None

        async def create_session(self, *, app_name, user_id, state):
            self._s = FakeSession(state)
            return self._s

        async def get_session(self, *, app_name, user_id, session_id):
            self._s.state[output_key] = fake_output
            return self._s

    class FakeRunner:
        def __init__(self, *, agent, app_name):
            self.session_service = FakeSvc()

        async def run_async(self, *, user_id, session_id, new_message, run_config=None):
            if False:
                yield None

    monkeypatch.setattr(orch, "InMemoryRunner", FakeRunner)
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")

    cfg = build_default()
    agents = build_step_agents(spec, cfg, cloud_allowed=True)
    synth_agent = agents[-1]

    state = asyncio.run(
        orch.run_step(
            synth_agent,
            message_text="TestTarget",
            seed_state={"target": "TestTarget", "public_findings": "some findings"},
            streaming=StreamingMode.NONE,
            trace=[],
        )
    )
    assert output_key in state, f"Expected '{output_key}' in state keys: {list(state.keys())}"
    assert state[output_key] is not None


# ── (f) extractor_key/extractor_name set ─────────────────────────────────────

@pytest.mark.parametrize("spec,expected_extractor_key", [
    (SOFTWARE_SPEC, "software.extractor"),
    (FINANCE_SPEC, "finance.extractor"),
    (ACADEMIC_SPEC, "academic.extractor"),
    (NUTRITION_SPEC, "nutrition.extractor"),
    (TRAVEL_SPEC, "travel.extractor"),
])
def test_extractor_key_set(spec, expected_extractor_key):
    assert spec.extractor_key == expected_extractor_key
    assert spec.extractor_name is not None


# ── (g) KNOWN_OUTPUT_SCHEMAS ─────────────────────────────────────────────────

@pytest.mark.parametrize("schema_name,schema_cls", [
    ("SoftwareBrief", SoftwareBrief),
    ("FinancialProfile", FinancialProfile),
    ("AcademicBrief", AcademicBrief),
    ("NutritionBrief", NutritionBrief),
    ("TravelBrief", TravelBrief),
])
def test_known_output_schemas(schema_name, schema_cls):
    assert schema_name in KNOWN_OUTPUT_SCHEMAS
    assert KNOWN_OUTPUT_SCHEMAS[schema_name] is schema_cls


# ── nutrition disclaimer is immutable ────────────────────────────────────────

def test_nutrition_disclaimer_always_present():
    """The NutritionBrief disclaimer cannot be blanked — it defaults to the safe string."""
    brief = NutritionBrief(
        topic="Vitamin C",
        one_line_summary="Antioxidant with strong evidence for immune support.",
        evidence_quality="strong RCT evidence",
    )
    assert "Not medical" in brief.disclaimer
    assert "clinical advice" in brief.disclaimer


def test_nutrition_disclaimer_survives_round_trip():
    """model_validate must preserve the disclaimer even if not explicitly passed."""
    data = {"topic": "Iron", "one_line_summary": "Essential mineral.", "evidence_quality": "strong"}
    brief = NutritionBrief.model_validate(data)
    assert brief.disclaimer


# ── planner orchestrator recognises all new capabilities ─────────────────────

def test_orchestrator_planner_capability_catalogue_includes_new_domains():
    """The planner's capability catalogue (used in the prompt) must include all 5 new domains."""
    from sentinel.agent.orchestrator_planner import _CAPABILITY_DESCRIPTIONS
    for cap in ("software", "finance", "academic", "nutrition", "travel"):
        assert cap in _CAPABILITY_DESCRIPTIONS, (
            f"'{cap}' missing from _CAPABILITY_DESCRIPTIONS — planner won't pick it"
        )


# ── render dispatch: domain briefs must not be shadowed by ProgramStrategy ────
# Regression (2026-06-12): an academic photosynthesis run produced a valid AcademicBrief
# but rendered as "Market-capture strategy". Root cause: _artifact_html infers type by
# field-presence and checked the generic ProgramStrategy branch (action_plan + assessment)
# BEFORE the domain briefs. Those two fields are a subset of every brief, so any brief whose
# LLM emitted both was greedily mis-rendered. Found live by the doc-grounded e2e matrix.

def _full_brief_dicts() -> dict[str, tuple[dict, str]]:
    """Each domain brief as a FULL model_dump (so action_plan + assessment keys are present —
    the exact condition that tripped ProgramStrategy), paired with its expected render title."""
    from sentinel.artifacts.schemas import RecommendedAction
    act = [RecommendedAction(priority="high", action="x", rationale="y", timeline="now")]
    src = Source(boundary="public", label="ref", url="https://example.com")
    fnd = lambda t: Finding(text=t, source=src)
    academic = AcademicBrief(
        topic="Photosynthesis", one_line_summary="s", topic_overview="o",
        key_findings=[fnd("f")], assessment="where the field stands", action_plan=act)
    software = SoftwareBrief(
        target="FastAPI", one_line_summary="s", category="web framework",
        tech_stack=[fnd("t")], community_health=[fnd("c")],
        assessment="a", action_plan=act)
    finance = FinancialProfile(
        target="Index funds", one_line_summary="s", financial_summary="fs",
        key_metrics=[fnd("m")], assessment="a", action_plan=act)
    nutrition = NutritionBrief(
        topic="Gluten-free", one_line_summary="s", evidence_quality="observational",
        key_claims=[fnd("k")], assessment="a", action_plan=act)
    travel = TravelBrief(
        destination="Kerala", one_line_summary="s", destination_overview="d",
        highlights=[fnd("h")], assessment="a", action_plan=act)
    return {
        "academic": (academic.model_dump(), "Academic brief"),
        "software": (software.model_dump(), "Software brief"),
        "finance": (finance.model_dump(), "Financial profile"),
        "nutrition": (nutrition.model_dump(), "Nutrition brief"),
        "travel": (travel.model_dump(), "Travel brief"),
    }


@pytest.mark.parametrize("domain", ["academic", "software", "finance", "nutrition", "travel"])
def test_domain_brief_not_rendered_as_program_strategy(domain):
    """A full domain brief (action_plan + assessment populated) renders under its OWN title,
    never the generic 'Market-capture strategy' aggregator."""
    from sentinel.web import render
    art, expected_title = _full_brief_dicts()[domain]
    assert "action_plan" in art and "assessment" in art, "test must exercise the conflicting keys"
    html = render._artifact_html(domain, art)
    assert expected_title in html, f"{domain} brief lost its template"
    assert "Market-capture strategy" not in html, f"{domain} brief shadowed by ProgramStrategy"


def test_program_strategy_still_renders_itself():
    """The genuine ProgramStrategy aggregator (no brief discriminators) keeps its title —
    the non-greedy guard must not over-correct."""
    from sentinel.web import render
    from sentinel.artifacts.schemas import ProgramStrategy, RecommendedAction
    strat = ProgramStrategy(
        assessment="cross-product standing",
        action_plan=[RecommendedAction(priority="high", action="ship", rationale="r", timeline="Q3")])
    html = render._artifact_html("program_strategy", strat.model_dump())
    assert "Market-capture strategy" in html
