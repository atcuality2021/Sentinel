"""SENTINEL-022 Step 5 — search-provider collision guard + product_research cascade wiring.

AC1: the gemini builtin google_search must not coexist with function-tools (it 400s). AC6: the
sovereign path (cloud_allowed=False) attaches no cascade and no cloud MCP, and never mixes the
builtin with function-tools. The pure helper is tested across all branches; the wiring is checked
by introspecting the built research-step agent's tool list.
"""

import pytest

from sentinel.agent.modes.spec import (
    PRODUCT_RESEARCH_SPEC,
    _resolve_search_tools,
    build_step_agents,
)
from sentinel.config.schema import SentinelConfig


# --------------------------------------------------------------------------- #
# Pure helper — every branch (AC1). Returns (effective_provider, keep_mcp).
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "requested,resolved,pin,has_mcp,fallback,expected",
    [
        # gemini + vLLM-resolved → fallback (builtin can't run on vLLM); keep MCP
        ("gemini", "vllm", False, False, "duckduckgo", ("duckduckgo", True)),
        ("gemini", "vllm", True, True, "serpapi", ("serpapi", True)),
        # gemini + cloud + no function-tools → keep the builtin
        ("gemini", "gemini", False, False, "duckduckgo", ("gemini", True)),
        ("gemini", "gemini", True, False, "duckduckgo", ("gemini", True)),
        # gemini + MCP + pin_gemini → left exactly as-is (out of scope): builtin + keep MCP
        ("gemini", "gemini", True, True, "duckduckgo", ("gemini", True)),
        # gemini + MCP + NOT pinned → MCP WINS, swap to fallback (the product_research path)
        ("gemini", "gemini", False, True, "brave", ("brave", True)),
        # an explicit non-gemini provider is always honored as-is; keep MCP
        ("duckduckgo", "gemini", True, True, "brave", ("duckduckgo", True)),
        ("brave", "vllm", False, False, "duckduckgo", ("brave", True)),
    ],
)
def test_resolve_search_tools_branches(requested, resolved, pin, has_mcp, fallback, expected):
    assert _resolve_search_tools(
        requested=requested, resolved=resolved, pin_gemini=pin,
        has_mcp_funcs=has_mcp, onprem_fallback=fallback,
    ) == expected


# --------------------------------------------------------------------------- #
# Wiring — introspect the research-step agent's tools
# --------------------------------------------------------------------------- #

def _research_agent(agents):
    return next(a for a in agents if "public_research" in a.name)


def _tool_names(agent):
    # function-tools expose __name__ ("search", "find_deals"); MCP toolsets fall back to class name
    return [getattr(t, "__name__", type(t).__name__) for t in (getattr(agent, "tools", None) or [])]


def test_ac6_sovereign_has_no_cascade_no_mcp_no_builtin(monkeypatch, tmp_path):
    """cloud_allowed=False: function-tool search only — no find_deals, no MCP, no gemini builtin."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    agents = build_step_agents(
        PRODUCT_RESEARCH_SPEC, SentinelConfig.default(),
        backend="vllm", cloud_allowed=False, search_provider="gemini",
    )
    names = _tool_names(_research_agent(agents))
    assert "find_deals" not in names              # no cascade on the sovereign path
    assert "McpToolset" not in names and "MCPToolset" not in names  # no SearchAPI/Firecrawl
    assert names and names[0] == "search"          # function-tool search, NOT the gemini builtin


def test_cloud_product_research_attaches_find_deals(monkeypatch, tmp_path):
    """cloud_allowed=True + product_research → the deterministic find_deals cascade is attached."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")  # construction only, no live call
    agents = build_step_agents(
        PRODUCT_RESEARCH_SPEC, SentinelConfig.default(),
        backend="gemini", cloud_allowed=True, search_provider="duckduckgo",
    )
    assert "find_deals" in _tool_names(_research_agent(agents))


def test_ac1_mcp_attach_drops_gemini_builtin(monkeypatch, tmp_path):
    """When MCP function-tools attach on a gemini request, the builtin is swapped for a function-tool."""
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    def _fake_mcp_tool(query: str) -> dict:
        """Stand-in for an MCP function-tool surface (a real callable, as ADK requires)."""
        return {}

    monkeypatch.setattr(
        "sentinel.tools.mcp_registry.build_mcp_toolsets",
        lambda *a, **k: [_fake_mcp_tool],
    )
    agents = build_step_agents(
        PRODUCT_RESEARCH_SPEC, SentinelConfig.default(),
        backend="gemini", cloud_allowed=True, search_provider="gemini",
    )
    names = _tool_names(_research_agent(agents))
    assert names[0] == "search"          # AC1 swap fired: function-tool, not the gemini builtin
    assert "find_deals" in names         # cascade still attached
    assert "_fake_mcp_tool" in names     # the (fake) MCP function-tool is present
