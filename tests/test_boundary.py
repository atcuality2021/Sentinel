"""Boundary-enforcement tests (SRS NFR-04 / FR-05).

These assert the public/private separation *structurally* — by inspecting how the agents are
constructed — rather than trusting prompt instructions. The invariant: the PRIVATE workspace
toolset never reaches a public agent. External research MCPs (Firecrawl, SearchAPI — public
web data) ARE sanctioned on public search steps since the mcp_registry landed; the structural
tests below therefore run with external-MCP env cleared so they check exactly the private
boundary, and ``test_external_mcp_rides_public_search_when_configured`` covers the sanctioned
path. Agents are built from an explicit default config so no config file is read or written.
"""

from __future__ import annotations

import pytest
from google.adk.tools import google_search

from sentinel.agent.modes.client import build_client_agent
from sentinel.agent.modes.competitor import build_competitor_agent
from sentinel.config import SentinelConfig

CFG = SentinelConfig.default()

# Env vars that activate external research MCP servers (see config.defaults._default_mcp_servers).
_EXTERNAL_MCP_ENV = ("FIRECRAWL_API_KEY", "SEARCHAPI_MCP_URL", "CLIENT_ID")


@pytest.fixture(autouse=True)
def _no_external_mcp(monkeypatch):
    """Structural boundary tests must not depend on the developer's .env contents."""
    for var in _EXTERNAL_MCP_ENV:
        monkeypatch.delenv(var, raising=False)


def _tool_names(agent) -> list[str]:
    names = []
    for t in getattr(agent, "tools", []) or []:
        names.append(type(t).__name__)
    return names


def test_competitor_pipeline_has_no_private_tools():
    agent = build_competitor_agent(config=CFG)
    for sub in agent.sub_agents:
        assert "McpToolset" not in _tool_names(sub), f"{sub.name} must not hold an MCP tool"
        assert "MCPToolset" not in _tool_names(sub)


def test_competitor_public_agent_uses_only_grounded_search():
    agent = build_competitor_agent(config=CFG)
    public = next(s for s in agent.sub_agents if "public_research" in s.name)
    assert public.tools == [google_search]


def test_synthesizer_has_no_tools_when_output_schema_set():
    agent = build_competitor_agent(config=CFG)
    synth = next(s for s in agent.sub_agents if "synthesizer" in s.name)
    assert not getattr(synth, "tools", None)
    assert synth.output_schema is not None


def test_client_public_agent_never_holds_mcp_tool():
    agent = build_client_agent(config=CFG)
    public = next(s for s in agent.sub_agents if "public_research" in s.name)
    assert public.tools == [google_search]
    assert "McpToolset" not in _tool_names(public)


def test_public_research_pinned_to_gemini_even_when_backend_is_vllm():
    # AC-7: grounding is Gemini-native — public_research must stay on the Gemini model id
    # regardless of the reasoning backend.
    cfg = SentinelConfig.default()
    cfg.backend.default = "vllm"
    agent = build_competitor_agent(config=cfg)
    public = next(s for s in agent.sub_agents if "public_research" in s.name)
    assert public.model == cfg.backend.gemini.model  # a string id, not a LiteLlm
    assert isinstance(public.model, str)


def test_external_mcp_rides_public_search_when_configured(monkeypatch):
    """The sanctioned path: a configured external research MCP (public web data) joins the
    public search step's tool list. Constructed only — no real npx spawn (lazy connect)."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    agent = build_competitor_agent(config=SentinelConfig.default())
    public = next(s for s in agent.sub_agents if "public_research" in s.name)
    assert "McpToolset" in _tool_names(public)


def test_external_mcp_absent_on_sovereign_run(monkeypatch):
    """Sovereignty: cloud egress MCPs never appear when cloud is disallowed."""
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    from sentinel.tools.mcp_registry import build_mcp_toolsets

    assert build_mcp_toolsets(SentinelConfig.default(), "account", cloud_allowed=False) == []
