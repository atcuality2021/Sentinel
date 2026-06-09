"""Competitor-intelligence mode → Battlecard.

Pipeline (SequentialAgent):
  1. planner          decompose the competitor into a research plan (FR-02)
  2. public_research  Gemini grounded search over public sources (FR-03, public boundary)
  3. battlecard       synthesize a schema-valid Battlecard (FR-07), via the LLM gateway

There is no private boundary in competitor mode — by construction, no MCP tools are present,
so private data cannot enter this flow. Model, prompt, and generation come from SentinelConfig
(SENTINEL-001); `backend` is an optional per-run override of the configured default.
"""

from __future__ import annotations

from dataclasses import dataclass

from google.adk.agents import Agent, SequentialAgent

from sentinel.agent.modes._build import maybe_strategist
from sentinel.agent.modes.spec import COMPETITOR_SPEC, build_step_agents
from sentinel.config import SentinelConfig, get_config


@dataclass
class CompetitorAgents:
    """The boundary/role/tier-correct competitor sub-agents (SENTINEL-011).

    Built once and consumed two ways: the legacy ``SequentialAgent`` runs them in order, and the
    A2A coordinator groups them as specialists. ``planner`` + ``public_research`` are the PUBLIC
    research path (no MCP); ``synthesizer`` is the tool-free reasoner that writes the Battlecard.
    """

    planner: Agent
    public_research: Agent
    synthesizer: Agent


def build_competitor_subagents(
    backend: str | None = None,
    config: SentinelConfig | None = None,
    *,
    memory_context: str = "",
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
) -> CompetitorAgents:
    """Construct the competitor sub-agents from config — the single source for both topologies.

    Delegates to the declarative `build_step_agents(COMPETITOR_SPEC, ...)` (SENTINEL-008), then
    groups the flat list into the dataclass the coordinator consumes. No private boundary exists in
    competitor mode: only ``public_research`` carries a tool, and it is the public search provider,
    never an MCP toolset.
    """
    cfg = config or get_config()
    # two_tier=False: the coordinator topology keeps the single-tier synth; two-tier inside the
    # coordinator is an explicit SENTINEL-008 fast-follow (the Sequential path honours the flag).
    by_key = {
        a.output_key: a
        for a in build_step_agents(
            COMPETITOR_SPEC, cfg, backend, cloud_allowed=cloud_allowed,
            search_provider=search_provider, memory_context=memory_context, two_tier=False,
        )
    }
    return CompetitorAgents(
        planner=by_key["research_plan"],
        public_research=by_key["public_findings"],
        synthesizer=by_key["battlecard"],
    )


def build_competitor_agent(
    backend: str | None = None,
    config: SentinelConfig | None = None,
    *,
    memory_context: str = "",
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
) -> SequentialAgent:
    """Build the competitor pipeline from config.

    ``backend`` swaps the *reasoning* LLM (planner + synthesizer) between Gemini and
    Gemma-on-vLLM. ``cloud_allowed`` + ``search_provider`` are the SENTINEL-005 governance inputs:
    when cloud is disallowed, every agent is forced to vLLM (no Gemini object built) and the
    public-research tool is a non-cloud provider — never ``google_search``.
    ``memory_context`` is a boundary-filtered prior-memory block (SENTINEL-002) appended to the
    synthesizer instruction; empty ⇒ instruction byte-identical to SENTINEL-001 (no regression).
    """
    cfg = config or get_config()
    # Spec-driven research graph (SENTINEL-008); honours research.two_tier. The strategist overlay
    # is appended before construction so ADK sets its parent_agent (mirrors SENTINEL-009 ordering).
    sub_agents = build_step_agents(
        COMPETITOR_SPEC, cfg, backend, cloud_allowed=cloud_allowed,
        search_provider=search_provider, memory_context=memory_context,
        two_tier=cfg.research.two_tier,
    )
    # Strategy overlay (SENTINEL-009): a tool-free strategist reads the battlecard from state and
    # writes a StrategyOverlay; the orchestrator merges it. None when strategy is disabled (dark).
    strategist = maybe_strategist(cfg, "competitor", backend=backend, cloud_allowed=cloud_allowed)
    if strategist is not None:
        sub_agents.append(strategist)
    return SequentialAgent(name=COMPETITOR_SPEC.name, sub_agents=sub_agents)
