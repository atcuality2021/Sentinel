"""SENTINEL-008 — declarative research modes + two-tier extract→synthesize.

Hermetic — no live LLM/network. Models are introspected; extractor/synth outputs are seeded into
state. Test IDs map to spec ACs. The load-bearing one is AC-6: with ``two_tier=False`` the
spec-built pipeline is byte-identical to the pre-refactor bespoke builders.
"""

from __future__ import annotations

from google.adk.agents import SequentialAgent

from sentinel.agent.modes.spec import (
    CLIENT_SPEC,
    COMPETITOR_SPEC,
    ResearchModeSpec,
    StepSpec,
    build_pipeline,
)
from sentinel.artifacts.schemas import Battlecard, Boundary, Extraction, ExtractionSet, Gap, Source
from sentinel.config.defaults import build_default
from sentinel.config.schema import AgentConfig, PromptTemplate


def _names(agent) -> list[str]:
    return [s.name for s in agent.sub_agents]


# --------------------------------------------------------------------------- #
# Step 1 — AC-5: generic build_pipeline reproduces today's graph from a spec
# --------------------------------------------------------------------------- #
def test_competitor_pipeline_structure_from_spec():
    agent = build_pipeline(COMPETITOR_SPEC, build_default())
    assert isinstance(agent, SequentialAgent)
    assert agent.name == "sentinel_competitor"
    assert _names(agent) == [
        "competitor_planner", "competitor_public_research", "battlecard_synthesizer",
    ]


def test_client_pipeline_omits_private_when_boundary_absent(monkeypatch):
    monkeypatch.delenv("SENTINEL_MCP_TRANSPORT", raising=False)
    agent = build_pipeline(CLIENT_SPEC, build_default())
    assert agent.name == "sentinel_client"
    # No MCP boundary configured → the private step is omitted (synth records the absence).
    assert _names(agent) == [
        "account_planner", "account_public_research", "account_brief_synthesizer",
    ]


def test_client_pipeline_includes_private_when_boundary_configured(monkeypatch):
    monkeypatch.setenv("SENTINEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("SENTINEL_MCP_URL", "http://localhost:9999/mcp")
    agent = build_pipeline(CLIENT_SPEC, build_default())
    assert _names(agent) == [
        "account_planner", "account_public_research",
        "account_private_research", "account_brief_synthesizer",
    ]


# --------------------------------------------------------------------------- #
# Step 3 — AC-1: extraction schemas
# --------------------------------------------------------------------------- #
def test_extraction_carries_source_boundary():
    ext = Extraction(
        source=Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://tc.example"),
        notes=["raised series B", "hiring a VP of sales"],
    )
    assert ext.source.boundary == Boundary.PUBLIC
    assert len(ext.notes) == 2


def test_extraction_set_defaults_empty():
    es = ExtractionSet()
    assert es.extractions == [] and es.gaps == []


def test_extraction_set_holds_extractions_and_gaps():
    es = ExtractionSet(
        extractions=[Extraction(source=Source(boundary=Boundary.PUBLIC, label="SEC filing"))],
        gaps=[Gap(boundary=Boundary.PUBLIC, what_was_missing="paywalled report",
                  impact="pricing unknown")],
    )
    assert es.extractions[0].notes == []          # extractor may return a source with no notes
    assert es.gaps[0].boundary == Boundary.PUBLIC


# --------------------------------------------------------------------------- #
# Step 4 — AC-11: config ships dark + extractor agents/prompts validate
# --------------------------------------------------------------------------- #
def test_research_config_ships_dark_and_roundtrips():
    from sentinel.config.schema import SentinelConfig

    cfg = build_default()
    assert cfg.research.two_tier is False                # dark by default (AC-6/11)
    restored = SentinelConfig.model_validate(cfg.model_dump())
    assert restored.research.two_tier is False
    assert restored.research.extract_max_notes_per_source == 8


def test_extractor_agents_and_prompts_present_and_cheap():
    cfg = build_default()
    for key in ("competitor.extractor", "client.extractor"):
        assert cfg.agents[key].role == "extractor"      # cheap tool-caller tier
        assert cfg.agents[key].pin_gemini is False       # follows governance, never forces cloud
        assert key in cfg.prompts
    # two-tier synthesizer variants exist and read {extractions}, not {public_findings}
    for key in ("competitor.synthesizer_2t", "client.synthesizer_2t"):
        assert "{extractions}" in cfg.prompts[key].template
        assert "{public_findings}" not in cfg.prompts[key].template


def test_all_prompts_validate():
    """Every default prompt (incl. the new extractor + 2t variants) passes render validation."""
    from sentinel.config.render import render_prompt

    cfg = build_default()
    for tmpl in cfg.prompts.values():
        render_prompt(tmpl)             # raises on a bad/unknown variable


# --------------------------------------------------------------------------- #
# Step 5 — AC-2/3/10: two-tier injects a cheap extractor before synthesis
# --------------------------------------------------------------------------- #
def _two_tier_cfg():
    cfg = build_default()
    cfg.research.two_tier = True
    return cfg


def test_two_tier_inserts_extractor_between_research_and_synth():
    agent = build_pipeline(COMPETITOR_SPEC, _two_tier_cfg())
    assert _names(agent) == [
        "competitor_planner", "competitor_public_research",
        "competitor_extractor", "battlecard_synthesizer",
    ]


def test_extractor_is_cheap_structured_and_tool_free():
    agent = build_pipeline(COMPETITOR_SPEC, _two_tier_cfg())
    from sentinel.artifacts.schemas import ExtractionSet as ES

    ext = next(s for s in agent.sub_agents if s.name == "competitor_extractor")
    assert ext.output_schema is ES                 # structured output (AC-1)
    assert not (getattr(ext, "tools", None) or [])  # single extractor pass, no tools (NFR-1)
    assert ext.output_key == "extractions"


def test_two_tier_synthesizer_reads_extractions():
    agent = build_pipeline(COMPETITOR_SPEC, _two_tier_cfg())
    synth = next(s for s in agent.sub_agents if s.name == "battlecard_synthesizer")
    assert "{extractions}" in synth.instruction
    assert "{public_findings}" not in synth.instruction


def test_two_tier_client_pipeline_shape(monkeypatch):
    monkeypatch.delenv("SENTINEL_MCP_TRANSPORT", raising=False)
    agent = build_pipeline(CLIENT_SPEC, _two_tier_cfg())
    assert _names(agent) == [
        "account_planner", "account_public_research",
        "account_extractor", "account_brief_synthesizer",
    ]


def test_extractor_builds_vllm_under_on_prem(monkeypatch):
    """AC-10: in on_prem the extractor is a vLLM object (no Gemini), like every other agent."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    from sentinel.config.schema import BackendOption

    cfg = _two_tier_cfg()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "extractor": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    agent = build_pipeline(COMPETITOR_SPEC, cfg, cloud_allowed=False, search_provider="duckduckgo")
    ext = next(s for s in agent.sub_agents if s.name == "competitor_extractor")
    assert not isinstance(ext.model, str)              # no Gemini model-id string
    assert type(ext.model).__name__ == "LiteLlm"


# --------------------------------------------------------------------------- #
# Step 6 — AC-4: orchestrator folds extractor gaps onto the artifact, fail-soft
# --------------------------------------------------------------------------- #
from sentinel.agent.orchestrator import _merge_extraction_gaps  # noqa: E402


def test_extraction_gap_merged_onto_artifact():
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    es = ExtractionSet(
        extractions=[Extraction(source=Source(boundary=Boundary.PUBLIC, label="TechCrunch"),
                                notes=["raised series B"])],
        gaps=[Gap(boundary=Boundary.PUBLIC, what_was_missing="pricing page",
                  impact="pricing unknown")],
    )
    note = _merge_extraction_gaps(art, {"extractions": es})
    assert len(art.gaps) == 1                          # the extractor's gap surfaced (AC-4)
    assert art.gaps[0].what_was_missing == "pricing page"
    assert "1 sources, 1 gaps" in note


def test_extraction_gap_merge_dedups_existing():
    g = Gap(boundary=Boundary.PUBLIC, what_was_missing="pricing page", impact="unknown")
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y", gaps=[g])
    es = ExtractionSet(gaps=[g])                       # synthesizer already surfaced it
    _merge_extraction_gaps(art, {"extractions": es})
    assert len(art.gaps) == 1                          # not double-counted


def test_extraction_merge_is_failsoft_on_garbage():
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    note = _merge_extraction_gaps(art, {"extractions": "not-an-extraction-set"})
    assert note.startswith("extractions: skipped")     # trace note, no raise
    assert art.gaps == []


def test_extraction_merge_none_when_absent():
    art = Battlecard(target="Acme", one_line_summary="x", positioning="y")
    assert _merge_extraction_gaps(art, {}) == "extractions: none"


# --------------------------------------------------------------------------- #
# Step 7 — AC-8: run versioning + provenance persist, delta intact
# --------------------------------------------------------------------------- #
def test_run_record_persists_sources_and_increments_seq(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.memory import RunRecord, RunStore

    store = RunStore(tmp_path / "sentinel.db")
    src = Source(boundary=Boundary.PUBLIC, label="TechCrunch", url="https://tc.example")
    store.save(RunRecord(entity="Acme", target="Acme", mode="competitor", backend="vllm",
                         finding_texts=["a"], sources=[src]))
    store.save(RunRecord(entity="Acme", target="Acme", mode="competitor", backend="vllm",
                         finding_texts=["b"]))
    runs = store.runs_for("Acme")                       # newest-first
    assert [r.run_seq for r in runs] == [2, 1]          # 1-based, increments per entity
    first = runs[-1]
    assert first.sources[0].label == "TechCrunch"       # provenance round-trips
    assert first.sources[0].boundary == Boundary.PUBLIC


def test_old_rows_default_empty_sources(tmp_path, monkeypatch):
    """A pre-008 row (no sources/run_seq columns) reads back with empty/0 after migration (R-4)."""
    import sqlite3

    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    db = tmp_path / "sentinel.db"
    # Simulate a legacy table without the new columns, then let RunStore migrate it.
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE run_records (id TEXT PRIMARY KEY, entity TEXT NOT NULL, target TEXT NOT NULL, "
        "mode TEXT NOT NULL, backend TEXT NOT NULL, kind TEXT NOT NULL, public INTEGER NOT NULL, "
        "private INTEGER NOT NULL, gaps INTEGER NOT NULL, reference TEXT NOT NULL, "
        "finding_texts TEXT NOT NULL, created_at TEXT NOT NULL);"
        "INSERT INTO run_records VALUES ('old1','acme','Acme','competitor','vllm','Battlecard',"
        "1,0,0,'ref','[]','2026-06-01T00:00:00+00:00');"
    )
    conn.commit()
    conn.close()

    from sentinel.memory import RunStore

    runs = RunStore(db).runs_for("Acme")                # __init__ runs the migration
    assert len(runs) == 1
    assert runs[0].sources == [] and runs[0].run_seq == 0


# --------------------------------------------------------------------------- #
# Step 8 — AC-7: a brand-new mode is *data + config*, with NO engine edit.
# This spec's keys are absent from defaults; the only thing that makes it build
# is registering its agents/prompts and handing the spec to build_pipeline. If
# build_step_agents had a mode special-case, this test could not pass.
# --------------------------------------------------------------------------- #
NOTES_SPEC = ResearchModeSpec(
    name="sentinel_notes",
    output_schema=Battlecard,                           # reuse a shipped artifact — mode is test-only
    steps=[
        StepSpec("notes.planner", "notes_planner", "research_plan", role="plan"),
        StepSpec("notes.research", "notes_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("notes.synthesizer", "notes_synthesizer", "notes_brief",
                 output_schema=Battlecard, role="synthesize"),
    ],
)


def _register_notes_mode(cfg):
    """Add the notes mode's agents + prompts to a config — the ONLY change a new mode needs."""
    for key in ("notes.planner", "notes.research", "notes.synthesizer"):
        cfg.agents[key] = AgentConfig(role="planner")    # cheap tool-caller tier; details irrelevant
    # Prompts use only reserved ADK vars ({target}, {public_findings}) → no declared variables needed.
    cfg.prompts["notes.planner"] = PromptTemplate(template="Plan research on {target}.")
    cfg.prompts["notes.research"] = PromptTemplate(template="Research {target}.")
    cfg.prompts["notes.synthesizer"] = PromptTemplate(
        template="Summarize {public_findings} about {target}.")
    return cfg


def test_new_mode_builds_with_no_engine_edit():
    cfg = _register_notes_mode(build_default())
    agent = build_pipeline(NOTES_SPEC, cfg, search_provider="duckduckgo")
    assert isinstance(agent, SequentialAgent)
    assert agent.name == "sentinel_notes"
    assert _names(agent) == ["notes_planner", "notes_research", "notes_synthesizer"]
    # The research step got the search tool; the synthesizer carries the artifact schema — all from
    # the StepSpec fields, with build_step_agents untouched (AC-7).
    research = next(s for s in agent.sub_agents if s.name == "notes_research")
    synth = next(s for s in agent.sub_agents if s.name == "notes_synthesizer")
    assert (getattr(research, "tools", None) or [])      # a search tool was wired in
    assert synth.output_schema is Battlecard


def test_new_mode_without_two_tier_keys_has_no_extractor():
    """A spec with no extractor_key skips two-tier even when the flag is on (AC-7 / NFR-1)."""
    cfg = _register_notes_mode(build_default())
    cfg.research.two_tier = True
    agent = build_pipeline(NOTES_SPEC, cfg, search_provider="duckduckgo")
    assert _names(agent) == ["notes_planner", "notes_research", "notes_synthesizer"]  # no extractor


# --------------------------------------------------------------------------- #
# BUG-FIX: vLLM domain skills must NOT receive google_search (Gemini-only tool)
# --------------------------------------------------------------------------- #

def test_domain_vllm_search_step_gets_duckduckgo_not_google_search():
    """When build_step_agents is called with search_provider='gemini' on a vLLM backend,
    the domain research agents (pin_gemini=False) must fall back to duckduckgo.
    ADK raises ValueError if google_search is wired to a hosted_vllm model (proven live)."""
    from sentinel.agent.modes.spec import FINANCE_SPEC, build_step_agents
    from google.adk.tools.google_search_tool import GoogleSearchTool

    cfg = build_default()
    agents = build_step_agents(
        FINANCE_SPEC, cfg, "vllm", cloud_allowed=True,
        search_provider="gemini", two_tier=False, memory_context="",
    )
    research = next(a for a in agents if a.name == "finance_public_research")
    tools = getattr(research, "tools", None) or []
    assert tools, "research agent must have a search tool"
    assert not any(isinstance(t, GoogleSearchTool) for t in tools), (
        "google_search must not be used with a vLLM model — should fall back to duckduckgo"
    )


def test_self_profile_pin_gemini_agent_keeps_google_search_tool():
    """self_profile.public_research has pin_gemini=True so it stays on Gemini search even on
    a vLLM backend call — the fix must not strip its GoogleSearchTool."""
    from sentinel.agent.modes.spec import SELF_PROFILE_SPEC, build_step_agents
    from google.adk.tools.google_search_tool import GoogleSearchTool

    cfg = build_default()
    agents = build_step_agents(
        SELF_PROFILE_SPEC, cfg, "vllm", cloud_allowed=True,
        search_provider="gemini", two_tier=False, memory_context="",
    )
    research = next(a for a in agents if a.name == "self_profile_public_research")
    tools = getattr(research, "tools", None) or []
    assert any(isinstance(t, GoogleSearchTool) for t in tools), (
        "self_profile research must keep GoogleSearchTool (pin_gemini=True)"
    )
