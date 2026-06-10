"""Client/account-intelligence mode → Account Brief.

Pipeline (SequentialAgent):
  1. planner          decompose the account into a research plan (FR-02)
  2. public_research  Gemini grounded search — firmographics, news, filings (public boundary)
  3. private_research scoped MCP connectors — CRM/docs/calendar (private boundary)  [if configured]
  4. account_brief    merge public + private into a schema-valid AccountBrief (FR-06, FR-08)

The two research agents are *separate objects with disjoint toolsets*: the public agent has only
``google_search``; the private agent has only the MCP toolset. Private data therefore cannot reach
the public boundary (NFR-04) — structurally, not by prompt. When the private boundary is not
configured, it is omitted and the synthesizer records a gap. Model/prompt/generation come from
SentinelConfig (SENTINEL-001).
"""

from __future__ import annotations

from dataclasses import dataclass

from sentinel.agent._compat import Agent, SequentialAgent

from sentinel.agent.modes._build import maybe_strategist
from sentinel.agent.modes.spec import CLIENT_SPEC, build_step_agents
from sentinel.config import SentinelConfig, get_config
from sentinel.tools.private.workspace_mcp import private_boundary_configured


@dataclass
class ClientAgents:
    """The boundary/role/tier-correct client sub-agents (SENTINEL-011).

    Consumed by both the legacy ``SequentialAgent`` and the A2A coordinator. ``planner`` +
    ``public_research`` are the PUBLIC path; ``private_research`` (the ONLY MCP holder, present only
    when the boundary is configured) is the PRIVATE path; ``synthesizer`` is the tool-free reasoner.
    The disjoint toolsets are the SENTINEL-002 boundary — structural, not prompt-based.
    """

    planner: Agent
    public_research: Agent
    synthesizer: Agent
    private_research: Agent | None = None


def build_client_subagents(
    backend: str | None = None,
    config: SentinelConfig | None = None,
    *,
    memory_context: str = "",
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
) -> ClientAgents:
    """Construct the client sub-agents from config — the single source for both topologies.

    ``public_research`` carries only the public search tool; ``private_research`` (if the boundary
    is configured) carries only the MCP toolset. The synthesizer's ``{private_note}`` reflects
    whether the private boundary is connected.
    """
    cfg = config or get_config()
    # Delegate to the declarative builder (SENTINEL-008): it wires the public-search tool, the MCP
    # toolset (only when the boundary is configured), and the synthesizer's connected/absent
    # {private_note} — exactly as before. Group the flat list into the dataclass by output_key;
    # private_research is present iff build_step_agents included it.
    # two_tier=False: the coordinator topology keeps the single-tier synth (SENTINEL-008 fast-follow).
    by_key = {
        a.output_key: a
        for a in build_step_agents(
            CLIENT_SPEC, cfg, backend, cloud_allowed=cloud_allowed,
            search_provider=search_provider, memory_context=memory_context, two_tier=False,
        )
    }
    return ClientAgents(
        planner=by_key["research_plan"],
        public_research=by_key["public_findings"],
        synthesizer=by_key["account_brief"],
        private_research=by_key.get("private_findings"),
    )


def build_client_agent(
    backend: str | None = None,
    config: SentinelConfig | None = None,
    *,
    memory_context: str = "",
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
) -> SequentialAgent:
    """Build the client pipeline from config.

    ``backend`` swaps the *reasoning* LLM (planner, private research, synthesizer) between
    Gemini and Gemma-on-vLLM. ``cloud_allowed`` + ``search_provider`` are the SENTINEL-005
    governance inputs: when cloud is disallowed every agent is forced to vLLM (no Gemini object)
    and public grounding uses a non-cloud provider — so private-data reasoning runs entirely on
    the customer's own GPUs and no public-web call ever touches Gemini.
    ``memory_context`` is a boundary-filtered prior-memory block (SENTINEL-002) appended to the
    synthesizer instruction; empty ⇒ instruction byte-identical to SENTINEL-001 (no regression).
    """
    cfg = config or get_config()
    # Spec-driven research graph (SENTINEL-008): [planner, public, (private if configured),
    # (extractor if two_tier), synth]. Strategist appended before construction so ADK sets its parent.
    sub_agents = build_step_agents(
        CLIENT_SPEC, cfg, backend, cloud_allowed=cloud_allowed,
        search_provider=search_provider, memory_context=memory_context,
        two_tier=cfg.research.two_tier,
    )
    # Strategy overlay (SENTINEL-009): tool-free strategist reads the account brief from state.
    strategist = maybe_strategist(cfg, "client", backend=backend, cloud_allowed=cloud_allowed)
    if strategist is not None:
        sub_agents.append(strategist)
    return SequentialAgent(name=CLIENT_SPEC.name, sub_agents=sub_agents)


def client_private_boundary_status() -> str:
    return "connected" if private_boundary_configured() else "not-configured (public-only)"
