"""A2A coordinator — Goal→Plan→Delegate→Merge over specialist agents (SENTINEL-011 / ADR-0001).

When ``coordinator.enabled`` is on, the orchestrator builds this ``LlmAgent`` (the 12B tool-caller)
instead of the per-mode ``SequentialAgent``. It delegates to the SAME boundary/role/tier-correct
sub-agents — regrouped as **specialists** and wrapped with ``google.adk.tools.AgentTool`` — and the
specialists' ``output_key`` writes propagate back to the orchestrator's session state via ADK's
state-delta forwarding, so the existing ``state[output_key]`` extraction path is untouched.

Boundary (SENTINEL-002, AC-11): the private/MCP toolset lives in exactly one specialist
(``private_research``), registered only in client mode. A competitor coordinator therefore has no
path to private tools — structurally, mirroring the SequentialAgent topology.

Sovereignty (SENTINEL-005, AC-5): every specialist and the coordinator are built via
``make_agent``/``resolve_model(cloud_allowed=)``, so ``on_prem_required`` builds zero Gemini objects
across the whole graph — provable by introspection. Remote A2A (a separate on-prem private node) is
Phase 2 (AC-14): it needs the ``a2a-sdk`` dependency + an ADR and is not built here.
"""

from __future__ import annotations

from sentinel.agent._compat import Agent, SequentialAgent
from google.adk.tools.agent_tool import AgentTool

from sentinel.agent.modes._build import make_agent, maybe_strategist
from sentinel.agent.modes.client import build_client_subagents
from sentinel.agent.modes.competitor import build_competitor_subagents
from sentinel.artifacts.schemas import Mode
from sentinel.config import SentinelConfig, get_config


def _describe(agent: Agent, text: str) -> Agent:
    """Give a specialist a description — AgentTool surfaces it as the tool's function description,
    which is how the coordinator LLM decides what to call."""
    agent.description = text
    return agent


def _maybe_strategist_specialist(mode: Mode, backend, cfg, *, cloud_allowed) -> Agent | None:
    """Build the 009 strategist as a coordinator specialist, or None when strategy is disabled.

    Same builder as the SequentialAgent path (``maybe_strategist``) — a tool-free reasoner emitting
    ``StrategyOverlay`` under ``output_key="strategy"``. Wrapped as an AgentTool, its description tells
    the coordinator to call it LAST (after synthesis), since it overlays strategy onto the finished
    artifact. Its ``output_key`` delta reaches the orchestrator's session, so ``_merge_strategy`` runs
    unchanged for both topologies (SENTINEL-011b).
    """
    strategist = maybe_strategist(cfg, mode, backend=backend, cloud_allowed=cloud_allowed)
    if strategist is None:
        return None
    return _describe(
        strategist,
        "Recommend strategy and next actions from the synthesized brief. Call this LAST, after "
        "synthesis has produced the artifact. Writes a strategy overlay (assessment + actions).",
    )


def _competitor_specialists(
    backend, cfg, *, memory_context, cloud_allowed, search_provider
) -> list[Agent]:
    a = build_competitor_subagents(
        backend, cfg, memory_context=memory_context,
        cloud_allowed=cloud_allowed, search_provider=search_provider,
    )
    research = SequentialAgent(
        name="competitor_research",
        description=(
            "Plan and run PUBLIC web research on the target competitor. Call this FIRST. "
            "Writes research_plan and public_findings to shared state."
        ),
        sub_agents=[a.planner, a.public_research],
    )
    synth = _describe(
        a.synthesizer,
        "Synthesize the final competitor battlecard from public_findings. Call this after "
        "research has run.",
    )
    specialists: list[Agent] = [research, synth]
    strategist = _maybe_strategist_specialist("competitor", backend, cfg, cloud_allowed=cloud_allowed)
    if strategist is not None:
        specialists.append(strategist)
    return specialists


def _client_specialists(
    backend, cfg, *, memory_context, cloud_allowed, search_provider
) -> list[Agent]:
    a = build_client_subagents(
        backend, cfg, memory_context=memory_context,
        cloud_allowed=cloud_allowed, search_provider=search_provider,
    )
    research = SequentialAgent(
        name="account_research",
        description=(
            "Plan and run PUBLIC web research on the target account (firmographics, news, "
            "filings). Call this FIRST. Writes research_plan and public_findings."
        ),
        sub_agents=[a.planner, a.public_research],
    )
    specialists: list[Agent] = [research]
    # The PRIVATE specialist is the ONLY MCP holder and exists only when the boundary is configured
    # — the structural boundary (SENTINEL-002): a public run never has this tool.
    if a.private_research is not None:
        specialists.append(
            _describe(
                a.private_research,
                "Retrieve PRIVATE account data via authorized internal connectors "
                "(CRM / documents / calendar). Writes private_findings. Never use for public data.",
            )
        )
    specialists.append(
        _describe(
            a.synthesizer,
            "Merge public_findings and private_findings into the final account brief. Call this "
            "after research (and private research, if available) have run.",
        )
    )
    strategist = _maybe_strategist_specialist("client", backend, cfg, cloud_allowed=cloud_allowed)
    if strategist is not None:
        specialists.append(strategist)
    return specialists


def build_coordinator(
    mode: Mode,
    config: SentinelConfig | None = None,
    *,
    backend: str | None = None,
    cloud_allowed: bool = True,
    search_provider: str = "gemini",
    memory_context: str = "",
) -> Agent:
    """Build the A2A coordinator for a mode: an LlmAgent delegating to AgentTool-wrapped specialists.

    The coordinator is a tool-caller (role ``coordinator`` → 12B under tiering) and carries NO
    ``output_schema`` (ADK forbids schema + tools together); the synthesis specialist owns the
    schema and writes the artifact key, which propagates to the parent session via AgentTool's
    state-delta forwarding. ``memory_context`` is appended to the synthesis specialist's instruction
    (same seam as the SequentialAgent path).
    """
    cfg = config or get_config()
    if mode == "competitor":
        specialists = _competitor_specialists(
            backend, cfg, memory_context=memory_context,
            cloud_allowed=cloud_allowed, search_provider=search_provider,
        )
    elif mode == "client":
        specialists = _client_specialists(
            backend, cfg, memory_context=memory_context,
            cloud_allowed=cloud_allowed, search_provider=search_provider,
        )
    else:
        raise ValueError(f"Unknown mode {mode!r} (expected 'competitor' or 'client')")

    tools = [AgentTool(agent=s) for s in specialists]
    # output_key is a throwaway for the coordinator's own final text; the artifact reaches the
    # orchestrator via the synthesis specialist's output_key delta, not the coordinator's.
    return make_agent(
        cfg,
        "coordinator",
        name="sentinel_coordinator",
        output_key="coordinator_summary",
        mode_backend=backend,
        tools=tools,
        cloud_allowed=cloud_allowed,
    )
