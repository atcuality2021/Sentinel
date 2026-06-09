"""A2A coordinator tests (SENTINEL-011 / ADR-0001).

Hermetic — no live LLM or network. Covers: the coordinator ships dark (AC-12), the build wraps
specialists as AgentTools per mode with the boundary preserved (AC-8/11), the orchestrator switch
is byte-identical when off and delegates when on (AC-9/10), and the zero-Gemini guarantee holds
across coordinator + specialists under on_prem (AC-5 extension).
"""

from __future__ import annotations

from google.adk.tools.agent_tool import AgentTool

from sentinel.agent.coordinator import build_coordinator
from sentinel.config.defaults import build_default
from sentinel.config.schema import BackendOption


def _tiered_cfg():
    """Default config with the Gemma-4 role map active (12B tool-callers / 26B reasoners)."""
    cfg = build_default()
    cfg.backend.default = "vllm"
    cfg.backend.roles = {
        "coordinator": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "planner": BackendOption(model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"),
        "public_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"
        ),
        "private_research": BackendOption(
            model="gemma-4-12B", api_base="https://gemma.atcuality.com/v1"
        ),
        "synthesizer": BackendOption(model="gemma-4-26B", api_base="https://omni.atcuality.com/v1"),
    }
    return cfg


def _all_tools(agent) -> list:
    """Flatten the tools held by a specialist, descending into SequentialAgent sub-agents."""
    out = list(getattr(agent, "tools", None) or [])
    for sub in getattr(agent, "sub_agents", None) or []:
        out.extend(_all_tools(sub))
    return out


def _has_mcp(agent) -> bool:
    return any("mcp" in type(t).__name__.lower() for t in _all_tools(agent))


# --- AC-12: coordinator ships dark ------------------------------------------------------- #


def test_coordinator_disabled_by_default():
    cfg = build_default()
    assert cfg.coordinator.enabled is False
    assert cfg.coordinator.remote_private is False
    assert cfg.coordinator.private_a2a_url is None


def test_coordinator_agent_and_prompt_exist():
    """The coordinator agent + prompt are present and configurable even while disabled."""
    cfg = build_default()
    assert "coordinator" in cfg.agents
    assert cfg.agents["coordinator"].role == "coordinator"
    assert "coordinator" in cfg.prompts
    assert "{target}" in cfg.prompts["coordinator"].template


def test_coordinator_config_round_trips_through_yaml():
    from sentinel.config.schema import SentinelConfig

    cfg = build_default()
    cfg.coordinator.enabled = True
    restored = SentinelConfig.model_validate(cfg.model_dump())
    assert restored.coordinator.enabled is True
    assert restored.agents["coordinator"].role == "coordinator"


# --- AC-8: build wraps specialists as AgentTools ----------------------------------------- #


def test_competitor_coordinator_wraps_specialists_as_agent_tools(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    coord = build_coordinator(
        "competitor", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    assert coord.name == "sentinel_coordinator"
    assert all(isinstance(t, AgentTool) for t in coord.tools)
    names = {t.agent.name for t in coord.tools}
    assert names == {"competitor_research", "battlecard_synthesizer"}
    # coordinator is a tool-caller → carries tools, never an output_schema (ADK forbids schema+tools)
    assert getattr(coord, "output_schema", None) is None


def test_coordinator_descriptions_are_set_for_tool_selection(monkeypatch):
    """Each specialist has a non-empty description — AgentTool surfaces it to the coordinator LLM."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    coord = build_coordinator(
        "competitor", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    for t in coord.tools:
        assert t.agent.description.strip(), t.agent.name


# --- SENTINEL-011b: the 009 strategist becomes a coordinator specialist when enabled ----- #


def _strat_cfg():
    """Tiered config with the 009 strategist enabled."""
    cfg = _tiered_cfg()
    cfg.strategy.enabled = True
    return cfg


def test_strategist_absent_when_strategy_disabled(monkeypatch):
    """Default (strategy off): no strategist specialist — the coordinator's tool-set is unchanged."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    for mode in ("competitor", "client"):
        coord = build_coordinator(
            mode, _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
        )
        assert not any(t.agent.name.endswith("_strategist") for t in coord.tools), mode


def test_competitor_coordinator_includes_strategist_when_enabled(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    coord = build_coordinator(
        "competitor", _strat_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    by_name = {t.agent.name: t.agent for t in coord.tools}
    assert "competitor_strategist" in by_name
    strat = by_name["competitor_strategist"]
    # the strategist writes the SAME key the SequentialAgent path uses → _merge_strategy is unchanged
    assert strat.output_key == "strategy"
    assert strat.description.strip()  # AgentTool surfaces this to the coordinator LLM
    # reasoner (26B) → tool-free (AC-7); AgentTool wrapping must not smuggle in tools
    assert not (getattr(strat, "tools", None) or [])


def test_client_coordinator_includes_strategist_when_enabled(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    coord = build_coordinator(
        "client", _strat_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    by_name = {t.agent.name: t.agent for t in coord.tools}
    assert "client_strategist" in by_name
    assert by_name["client_strategist"].output_key == "strategy"
    assert not (getattr(by_name["client_strategist"], "tools", None) or [])


def test_strategist_specialist_builds_zero_gemini_under_on_prem(monkeypatch):
    """The strategist specialist inherits sovereignty — no Gemini object under on_prem (AC-5)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    coord = build_coordinator(
        "competitor", _strat_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    strat = next(t.agent for t in coord.tools if t.agent.name == "competitor_strategist")
    assert not isinstance(strat.model, str)
    assert type(strat.model).__name__ == "LiteLlm"


# --- AC-11: boundary — private/MCP tool only in client mode ------------------------------ #


def test_competitor_coordinator_has_no_private_tool(monkeypatch):
    """A competitor coordinator registers only PUBLIC specialists — no MCP anywhere in the tree."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.delenv("SENTINEL_MCP_TRANSPORT", raising=False)
    coord = build_coordinator(
        "competitor", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    assert not any(_has_mcp(t.agent) for t in coord.tools)


def test_client_coordinator_isolates_mcp_in_private_specialist(monkeypatch):
    """Client coordinator: the MCP toolset lives ONLY in the private specialist; the public
    research path has none (SENTINEL-002 boundary, AC-11)."""
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setenv("SENTINEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("SENTINEL_MCP_URL", "http://localhost:9999/mcp")
    coord = build_coordinator(
        "client", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    by_name = {t.agent.name: t.agent for t in coord.tools}
    assert "account_private_research" in by_name  # private specialist registered
    assert _has_mcp(by_name["account_private_research"])         # MCP is HERE
    assert not _has_mcp(by_name["account_research"])             # and NOT on the public path
    # exactly one specialist holds MCP
    assert sum(_has_mcp(t.agent) for t in coord.tools) == 1


def test_client_coordinator_without_boundary_has_no_private_specialist(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.delenv("SENTINEL_MCP_TRANSPORT", raising=False)
    coord = build_coordinator(
        "client", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )
    names = {t.agent.name for t in coord.tools}
    assert "account_private_research" not in names
    assert not any(_has_mcp(t.agent) for t in coord.tools)


# --- AC-5 extension: zero Gemini across coordinator + specialists under on_prem ----------- #


def test_coordinator_builds_zero_gemini_under_on_prem(monkeypatch):
    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    monkeypatch.setenv("SENTINEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("SENTINEL_MCP_URL", "http://localhost:9999/mcp")
    coord = build_coordinator(
        "client", _tiered_cfg(), cloud_allowed=False, search_provider="duckduckgo"
    )

    def assert_vllm(agent):
        assert not isinstance(agent.model, str), f"{agent.name} got a Gemini model-id string"
        assert type(agent.model).__name__ == "LiteLlm", agent.name

    assert_vllm(coord)
    for t in coord.tools:
        a = t.agent
        if getattr(a, "sub_agents", None):
            for sub in a.sub_agents:
                assert_vllm(sub)
        else:
            assert_vllm(a)


# --- AC-9/10: orchestrator switch (dark by default) -------------------------------------- #


def test_build_agent_returns_sequential_when_coordinator_off(monkeypatch):
    """Default (coordinator off): _build_agent returns the legacy SequentialAgent — no regression."""
    from sentinel.agent.orchestrator import _build_agent

    cfg = build_default()  # coordinator.enabled is False
    agent = _build_agent("competitor", None, cfg, cloud_allowed=True, search_provider="gemini")
    assert type(agent).__name__ == "SequentialAgent"
    assert agent.name == "sentinel_competitor"


def test_build_agent_returns_coordinator_when_enabled(monkeypatch):
    """Coordinator on: _build_agent returns the LlmAgent coordinator and traces the delegation."""
    from sentinel.agent.orchestrator import _build_agent

    monkeypatch.setenv("ATCUALITY_API_KEY", "atc")
    cfg = _tiered_cfg()
    cfg.coordinator.enabled = True
    trace: list[str] = []
    agent = _build_agent(
        "competitor", None, cfg, cloud_allowed=False, search_provider="duckduckgo", trace=trace,
    )
    assert agent.name == "sentinel_coordinator"
    assert any(t.startswith("coordinator=on") for t in trace)
    assert "competitor_research" in " ".join(trace)


def test_build_agent_failsoft_degrades_to_sequential(monkeypatch):
    """A coordinator build error degrades to the SequentialAgent — the run is never taken down."""
    import sentinel.agent.coordinator as coord_mod
    from sentinel.agent.orchestrator import _build_agent

    cfg = build_default()
    cfg.coordinator.enabled = True

    def boom(*a, **k):
        raise RuntimeError("simulated coordinator misconfig")

    monkeypatch.setattr(coord_mod, "build_coordinator", boom)
    trace: list[str] = []
    agent = _build_agent("competitor", None, cfg, cloud_allowed=True, trace=trace)
    assert type(agent).__name__ == "SequentialAgent"
    assert any("degraded to sequential" in t for t in trace)
