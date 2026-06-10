"""Declarative research modes (SENTINEL-008).

A research mode is **data**: an ordered list of `StepSpec`s + an output schema. `build_step_agents`
is the single, generic constructor that turns a spec into ADK agents — so adding a mode is a new
`ResearchModeSpec`, not an edit to the engine (FR-083 / AC-5, AC-7). `build_pipeline` wraps those
agents in the legacy `SequentialAgent`.

**One construction path, two groupings.** The agent objects this module builds are the *same* ones
the legacy `SequentialAgent` runs and the SENTINEL-011 coordinator regroups as specialists — so
`build_competitor_subagents`/`build_client_subagents` (the coordinator's source) delegate here and map
the flat list into their dataclass. There is no second place that constructs `competitor.planner` et
al., so the spec and the running graph cannot drift (Anti-Pattern #1).

No-regression is the load-bearing property (AC-6): with `two_tier=False` this reproduces the exact
`make_agent(...)` calls the bespoke builders made — same keys, names, order, tools, schemas, and the
`memory_context` suffix on the synthesizer — so default output is byte-identical to SENTINEL-004.
Sovereignty is inherited unchanged: every agent is built via `make_agent`/`resolve_model(cloud_allowed=)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from sentinel.agent._compat import Agent, SequentialAgent
from pydantic import BaseModel

from sentinel.agent.modes._build import make_agent
from sentinel.artifacts.schemas import (
    AccountBrief,
    AcademicBrief,
    Battlecard,
    ComparisonMatrix,
    ExtractionSet,
    FinancialProfile,
    NutritionBrief,
    SelfProfile,
    SoftwareBrief,
    TravelBrief,
)
from sentinel.config import SentinelConfig, get_config
from sentinel.config.render import render_prompt
from sentinel.tools.private.workspace_mcp import build_private_toolset
from sentinel.tools.public.web_search import get_search_tool

StepRole = Literal["plan", "research", "extract", "synthesize"]
ToolKind = Literal["search", "private"]


@dataclass(frozen=True)
class StepSpec:
    """One pipeline step, declaratively. ``tool`` selects the toolset the step carries (or none);
    ``output_schema`` is set on the structured steps (the synthesizer). ``name`` is the stable ADK
    sub-agent name the tests and run trace key on."""

    agent_key: str                                  # config key, e.g. "competitor.planner"
    name: str                                       # ADK sub-agent name (stable)
    output_key: str                                 # state key this step writes
    tool: ToolKind | None = None
    output_schema: type[BaseModel] | None = None
    role: StepRole = "research"


@dataclass(frozen=True)
class ResearchModeSpec:
    """A research mode as data: ordered steps + the artifact schema. ``has_private`` opts the mode
    into the SENTINEL-002 private boundary (a ``tool="private"`` step that is included only when the
    boundary is configured, plus the synthesizer's ``{private_note}`` substitution).

    ``extractor_key`` / ``extractor_name`` name the cheap two-tier extractor (SENTINEL-008): its
    config/prompt key and ADK sub-agent name. They're explicit (not derived) because the modes have
    no single naming convention — competitor's synth is ``battlecard_synthesizer``, client's agents
    use an ``account_*`` prefix. A spec without them set simply has no two-tier path."""

    name: str                                       # SequentialAgent name, e.g. "sentinel_competitor"
    output_schema: type[BaseModel]
    steps: list[StepSpec] = field(default_factory=list)
    has_private: bool = False
    extractor_key: str | None = None                # e.g. "competitor.extractor"
    extractor_name: str | None = None               # e.g. "competitor_extractor"
    # SENTINEL-012: a domain skill is a spec tagged with its ``capability`` (what it produces, the
    # key the Phase-3 planner staffs against) and its ``domain`` (the research area it belongs to).
    # The "mode library" below (``SKILL_SPECS``) thereby becomes the seed of the skill registry —
    # discoverable by capability/domain — without yet building the Phase-3 AgentRegistry (design §2.1).
    capability: str = ""
    domain: str = ""


# --------------------------------------------------------------------------- #
# The two shipped modes, expressed declaratively (AC-6). These reproduce the
# exact graph competitor.py / client.py built before SENTINEL-008.
# --------------------------------------------------------------------------- #
COMPETITOR_SPEC = ResearchModeSpec(
    name="sentinel_competitor",
    output_schema=Battlecard,
    capability="competitor",
    domain="market",
    extractor_key="competitor.extractor",
    extractor_name="competitor_extractor",
    steps=[
        StepSpec("competitor.planner", "competitor_planner", "research_plan", role="plan"),
        StepSpec("competitor.public_research", "competitor_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("competitor.synthesizer", "battlecard_synthesizer", "battlecard",
                 output_schema=Battlecard, role="synthesize"),
    ],
)

CLIENT_SPEC = ResearchModeSpec(
    name="sentinel_client",
    output_schema=AccountBrief,
    capability="client",
    domain="account",
    has_private=True,
    extractor_key="client.extractor",
    extractor_name="account_extractor",
    steps=[
        StepSpec("client.planner", "account_planner", "research_plan", role="plan"),
        StepSpec("client.public_research", "account_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("client.private_research", "account_private_research", "private_findings",
                 tool="private", role="research"),
        StepSpec("client.synthesizer", "account_brief_synthesizer", "account_brief",
                 output_schema=AccountBrief, role="synthesize"),
    ],
)

# --------------------------------------------------------------------------- #
# SENTINEL-012 §2.4 — the first new domain skill of the universal value chain.
# self_profile is the 'us' side of the compare: it profiles OUR OWN org/products
# (state key 'target' = our brand), the mirror of competitor's rival-facing graph.
# Same plan→research(search)→synthesize topology → reuses build_step_agents
# unchanged (no engine edit), inheriting tiering + sovereignty (AC-6).
# --------------------------------------------------------------------------- #
SELF_PROFILE_SPEC = ResearchModeSpec(
    name="sentinel_self_profile",
    output_schema=SelfProfile,
    capability="self_profile",
    domain="market",
    steps=[
        StepSpec("self_profile.planner", "self_profile_planner", "research_plan", role="plan"),
        StepSpec("self_profile.public_research", "self_profile_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("self_profile.synthesizer", "self_profile_synthesizer", "self_profile",
                 output_schema=SelfProfile, role="synthesize"),
    ],
)


# --------------------------------------------------------------------------- #
# SENTINEL-012 §2.4 — the `compare` skill: a tool-free reasoner that reads our
# SelfProfile + a rival Battlecard from seed-state and emits a ComparisonMatrix
# (win/lose/parity per axis). A degenerate one-step spec (synthesize only, no
# planner/research/tools) — the first skill whose inputs are other skills'
# outputs; the Step-10 DAG encodes that self_profile→compare←competitor edge.
# --------------------------------------------------------------------------- #
COMPARE_SPEC = ResearchModeSpec(
    name="sentinel_compare",
    output_schema=ComparisonMatrix,
    capability="compare",
    domain="market",
    steps=[
        StepSpec("compare.synthesizer", "compare_synthesizer", "comparison_matrix",
                 output_schema=ComparisonMatrix, role="synthesize"),
    ],
)


# --------------------------------------------------------------------------- #
# SENTINEL-014: universal domain specialists — one ResearchModeSpec per domain.
# All follow the same plan→research(search)→synthesize topology as competitor/
# self_profile: planner (tool-caller, 12B), public_research (search, 12B),
# synthesizer (reasoner, 26B, tool-free). No private boundary (public-only domains).
# Adding a new domain is: new spec here + prompts + agent configs in defaults.py.
# --------------------------------------------------------------------------- #

SOFTWARE_SPEC = ResearchModeSpec(
    name="sentinel_software",
    output_schema=SoftwareBrief,
    capability="software",
    domain="software",
    extractor_key="software.extractor",
    extractor_name="software_extractor",
    steps=[
        StepSpec("software.planner", "software_planner", "research_plan", role="plan"),
        StepSpec("software.public_research", "software_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("software.synthesizer", "software_synthesizer", "software_brief",
                 output_schema=SoftwareBrief, role="synthesize"),
    ],
)

FINANCE_SPEC = ResearchModeSpec(
    name="sentinel_finance",
    output_schema=FinancialProfile,
    capability="finance",
    domain="finance",
    extractor_key="finance.extractor",
    extractor_name="finance_extractor",
    steps=[
        StepSpec("finance.planner", "finance_planner", "research_plan", role="plan"),
        StepSpec("finance.public_research", "finance_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("finance.synthesizer", "finance_synthesizer", "financial_profile",
                 output_schema=FinancialProfile, role="synthesize"),
    ],
)

ACADEMIC_SPEC = ResearchModeSpec(
    name="sentinel_academic",
    output_schema=AcademicBrief,
    capability="academic",
    domain="academic",
    extractor_key="academic.extractor",
    extractor_name="academic_extractor",
    steps=[
        StepSpec("academic.planner", "academic_planner", "research_plan", role="plan"),
        StepSpec("academic.public_research", "academic_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("academic.synthesizer", "academic_synthesizer", "academic_brief",
                 output_schema=AcademicBrief, role="synthesize"),
    ],
)

NUTRITION_SPEC = ResearchModeSpec(
    name="sentinel_nutrition",
    output_schema=NutritionBrief,
    capability="nutrition",
    domain="nutrition",
    extractor_key="nutrition.extractor",
    extractor_name="nutrition_extractor",
    steps=[
        StepSpec("nutrition.planner", "nutrition_planner", "research_plan", role="plan"),
        StepSpec("nutrition.public_research", "nutrition_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("nutrition.synthesizer", "nutrition_synthesizer", "nutrition_brief",
                 output_schema=NutritionBrief, role="synthesize"),
    ],
)

TRAVEL_SPEC = ResearchModeSpec(
    name="sentinel_travel",
    output_schema=TravelBrief,
    capability="travel",
    domain="travel",
    extractor_key="travel.extractor",
    extractor_name="travel_extractor",
    steps=[
        StepSpec("travel.planner", "travel_planner", "research_plan", role="plan"),
        StepSpec("travel.public_research", "travel_public_research", "public_findings",
                 tool="search", role="research"),
        StepSpec("travel.synthesizer", "travel_synthesizer", "travel_brief",
                 output_schema=TravelBrief, role="synthesize"),
    ],
)


# The skill registry: capability → spec (design §2.1, "the mode library becomes the skill registry").
# A flat in-code seed for now; Phase 3's AgentRegistry will resolve (capability, domain) → best spec.
SKILL_SPECS: dict[str, ResearchModeSpec] = {
    spec.capability: spec
    for spec in (
        COMPETITOR_SPEC, CLIENT_SPEC, SELF_PROFILE_SPEC, COMPARE_SPEC,
        # SENTINEL-014: universal domain specialists
        SOFTWARE_SPEC, FINANCE_SPEC, ACADEMIC_SPEC, NUTRITION_SPEC, TRAVEL_SPEC,
    )
}


def build_step_agents(
    spec: ResearchModeSpec,
    cfg: SentinelConfig | None = None,
    backend: str | None = None,
    *,
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
    memory_context: str = "",
    two_tier: bool = False,
) -> list[Agent]:
    """Construct a mode's step-agents from its spec — the single source for every topology.

    Tool wiring per ``StepSpec.tool``: ``search`` → the configured public provider; ``private`` →
    the MCP toolset, and the step is **omitted** when the boundary is not configured (the synthesizer
    then records the absence via its ``{private_note}``). The synthesize step carries the artifact
    ``output_schema`` and the ``memory_context`` suffix (SENTINEL-002), and — for a ``has_private``
    mode — the connected/absent private-note substitution, exactly as the bespoke builders did.

    When ``two_tier`` (SENTINEL-008), a cheap ``<mode>.extractor`` step is inserted immediately
    before synthesis (distilling ``{public_findings}`` → typed ``{extractions}``), and the synthesizer
    renders its ``<mode>.synthesizer_2t`` prompt variant (reads ``{extractions}``). With ``two_tier``
    off this is byte-identical to the single-tier graph (AC-6).
    """
    cfg = cfg or get_config()
    # Resolve the private toolset once (mirrors the bespoke client builder; avoids double MCP build).
    private_toolset = build_private_toolset() if spec.has_private else None

    agents: list[Agent] = []
    for step in spec.steps:
        if step.tool == "private":
            if private_toolset is None:
                continue                      # boundary not configured → omit the private step
            tools: list | None = [private_toolset]
        elif step.tool == "search":
            # ADK's google_search builtin is Gemini-native — it hard-errors when given to a
            # LiteLLM (vLLM) model. Detect the mismatch: if this step's agent resolves to vLLM
            # (pin_gemini=False and mode_backend=vllm, or cloud_allowed=False) and the caller
            # passed "gemini" as the search provider, fall back to duckduckgo so the research
            # step can actually run with the 12B tool-caller.
            from sentinel.llm.gateway import resolve_backend as _rb
            _ac = cfg.agents.get(step.agent_key)
            _pin = _ac.pin_gemini if _ac else False
            _resolved = "vllm" if not cloud_allowed else ("gemini" if _pin else _rb(backend or cfg.backend.default))
            _eff_provider = (
                "duckduckgo" if (_resolved == "vllm" and search_provider == "gemini")
                else search_provider
            )
            tools = [get_search_tool(
                _eff_provider, results=cfg.search.results,
                max_calls=getattr(cfg.search, "max_calls", 0),
                stagger_s=getattr(cfg.search, "stagger_s", 0.0),
            )]
        else:
            tools = None

        note_substitutions: dict[str, str] | None = None
        instruction_suffix = ""
        prompt_key: str | None = None
        if step.role == "synthesize":
            instruction_suffix = memory_context
            mode = step.agent_key.split(".", 1)[0]
            if spec.has_private:
                key = (f"{mode}.private_note_connected" if private_toolset is not None
                       else f"{mode}.private_note_absent")
                note_substitutions = {"private_note": render_prompt(cfg.prompts[key])}
            if two_tier and spec.extractor_key:
                # Insert the cheap extractor right before synthesis, then point the synthesizer at
                # its two-tier prompt variant so it reads typed {extractions} instead of raw notes.
                agents.append(make_agent(
                    cfg, spec.extractor_key, name=spec.extractor_name or f"{mode}_extractor",
                    output_key="extractions", output_schema=ExtractionSet,
                    mode_backend=backend, cloud_allowed=cloud_allowed,
                ))
                prompt_key = f"{step.agent_key}_2t"

        agents.append(make_agent(
            cfg, step.agent_key, name=step.name, output_key=step.output_key,
            mode_backend=backend, tools=tools, output_schema=step.output_schema,
            note_substitutions=note_substitutions, instruction_suffix=instruction_suffix,
            cloud_allowed=cloud_allowed, prompt_key=prompt_key,
        ))
    return agents


def build_pipeline(
    spec: ResearchModeSpec,
    cfg: SentinelConfig | None = None,
    backend: str | None = None,
    *,
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
    memory_context: str = "",
) -> SequentialAgent:
    """Build a mode's `SequentialAgent` from its spec (AC-5). Output-preserving: with the default
    config this is the same graph competitor.py/client.py produced. The SENTINEL-009 strategist is
    *not* a research step — the mode builders append it after this pipeline, as before."""
    cfg = cfg or get_config()
    sub_agents = build_step_agents(
        spec, cfg, backend, cloud_allowed=cloud_allowed,
        search_provider=search_provider, memory_context=memory_context,
        two_tier=cfg.research.two_tier,
    )
    return SequentialAgent(name=spec.name, sub_agents=sub_agents)
