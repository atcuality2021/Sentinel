"""External MCP registry — config defaults, secret gating, domain scoping, sovereignty."""
from __future__ import annotations

import pytest

from sentinel.config.defaults import build_default
from sentinel.config.schema import MCPServerConfig
from sentinel.tools.mcp_registry import build_mcp_toolsets, mcp_status


@pytest.fixture()
def cfg():
    return build_default()


def test_defaults_ship_firecrawl_searchapi_gdrive(cfg):
    assert "firecrawl" in cfg.mcp_servers
    assert "searchapi" in cfg.mcp_servers
    assert "gdrive" in cfg.mcp_servers
    fc = cfg.mcp_servers["firecrawl"]
    assert fc.transport == "stdio" and fc.command == "npx"
    assert fc.api_key_env == "FIRECRAWL_API_KEY"
    assert "firecrawl_search" in fc.tool_filter
    sa = cfg.mcp_servers["searchapi"]
    assert sa.transport == "http" and sa.url_env == "SEARCHAPI_MCP_URL"
    gd = cfg.mcp_servers["gdrive"]
    assert gd.transport == "stdio" and gd.api_key_env == "CLIENT_ID"
    # Read-only enforcement: the write tool must NOT be in the allow-list.
    assert "gsheets_update_cell" not in gd.tool_filter
    assert set(gd.tool_filter) == {"gdrive_search", "gdrive_read_file"}


def test_no_secret_means_no_toolset(cfg, monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    assert build_mcp_toolsets(cfg, "product_research") == []


def test_sovereign_run_gets_no_cloud_mcp(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    assert build_mcp_toolsets(cfg, "product_research", cloud_allowed=False) == []


def test_disabled_server_skipped(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    cfg.mcp_servers["firecrawl"].enabled = False
    assert build_mcp_toolsets(cfg, "product_research") == []


def test_domain_scoping(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    cfg.mcp_servers["firecrawl"].domains = ["finance"]
    # wrong domain → excluded without even building (no McpToolset constructed)
    assert build_mcp_toolsets(cfg, "product_research") == []


def test_configured_server_builds_toolset(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    built = []

    def fake_build(name, server):
        built.append(name)
        return f"toolset-{name}"

    monkeypatch.setattr("sentinel.tools.mcp_registry._build_one", fake_build)
    out = build_mcp_toolsets(cfg, "product_research")
    assert out == ["toolset-firecrawl"] and built == ["firecrawl"]


def test_build_failure_is_fail_soft(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)

    def boom(name, server):
        raise RuntimeError("npx not found")

    monkeypatch.setattr("sentinel.tools.mcp_registry._build_one", boom)
    assert build_mcp_toolsets(cfg, "product_research") == []  # never raises


def test_mcp_status_rows(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    rows = {r["name"]: r for r in mcp_status(cfg)}
    assert rows["firecrawl"]["configured"] is True
    assert rows["searchapi"]["configured"] is False
    assert rows["firecrawl"]["secret_env"] == "FIRECRAWL_API_KEY"


def test_old_yaml_without_mcp_section_still_loads():
    # mcp_servers has a default_factory — a pre-existing sentinel.config.yaml
    # without the section must validate cleanly.
    from sentinel.config.schema import SentinelConfig

    base = build_default()
    data = base.model_dump()
    data.pop("mcp_servers")
    cfg = SentinelConfig.model_validate(data)
    assert cfg.mcp_servers == {}


def test_custom_server_roundtrip():
    s = MCPServerConfig(
        transport="http", url_env="MY_MCP_URL", domains=["finance"],
        tool_filter=["quote"], description="test",
    )
    assert s.enabled is True
    assert MCPServerConfig.model_validate(s.model_dump()) == s
