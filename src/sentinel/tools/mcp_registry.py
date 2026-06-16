"""External MCP server registry — config-driven toolsets agents select per step.

Mirrors the private-boundary pattern (``workspace_mcp.build_private_toolset``): secrets
stay in .env (configs name the variable, never the value), a server with its secret
unset is skipped silently, and every build is fail-soft — one broken server never
blocks a research run.

Sovereignty: these servers are **cloud egress** (Firecrawl, SearchAPI). When a run is
sovereign (``cloud_allowed=False``) no external MCP toolset is offered, the same rule
that pins such runs to vLLM + non-cloud search.
"""

from __future__ import annotations

import logging
import os
import shlex

log = logging.getLogger(__name__)


def _secret_set(server) -> bool:
    """True when the env var(s) this server needs are present (value never read here)."""
    if server.transport == "stdio":
        return bool(server.api_key_env) and bool(os.getenv(server.api_key_env))
    return bool(server.url_env) and bool(os.getenv(server.url_env))


def build_mcp_toolsets(cfg, domain: str = "", *, cloud_allowed: bool = True) -> list:
    """Toolsets for every enabled+configured server matching ``domain``.

    ``domain`` matching: a server with empty ``domains`` serves all; otherwise the
    research domain must be listed. Returns ``[]`` rather than raising on any failure.
    """
    if not cloud_allowed:
        return []
    servers = getattr(cfg, "mcp_servers", None) or {}
    toolsets: list = []
    for name, server in servers.items():
        if not server.enabled or not _secret_set(server):
            continue
        if server.domains and domain not in server.domains:
            continue
        try:
            toolsets.append(_build_one(name, server))
        except Exception as exc:  # fail-soft: a bad server never sinks the run
            log.warning("mcp server %s skipped: %s", name, str(exc)[:200])
    return toolsets


def _make_safe_toolset(inner, name: str):
    """Wrap an McpToolset in a fail-soft subclass of BaseToolset.

    ADK calls get_tools() inside an async TaskGroup during session startup. Without this
    wrapper, a 429 / connection error from any MCP server propagates as an unhandled TaskGroup
    exception and kills the entire research run. With this wrapper the agent silently loses
    the MCP tools but keeps its regular search tool (duckduckgo / gemini builtin) and completes.

    Deferred import: BaseToolset is only available when google-adk is installed.
    """
    from google.adk.tools.base_toolset import BaseToolset

    class _SafeMcpToolset(BaseToolset):
        async def get_tools(self, readonly_context=None):  # type: ignore[override]
            try:
                return await inner.get_tools(readonly_context)
            except Exception as exc:
                log.warning(
                    "MCP server %r unavailable (%.200s) — falling back to native search",
                    name, exc,
                )
                return []

        async def close(self) -> None:
            try:
                await inner.close()
            except Exception:
                pass

    return _SafeMcpToolset(
        tool_filter=getattr(inner, "tool_filter", None),
        tool_name_prefix=getattr(inner, "tool_name_prefix", None),
    )


def _build_one(name: str, server):
    from google.adk.tools import McpToolset
    from google.adk.tools.mcp_tool import (
        StdioConnectionParams,
        StreamableHTTPConnectionParams,
    )

    tool_filter = server.tool_filter or None
    if server.transport == "stdio":
        from mcp import StdioServerParameters

        env = {**os.environ}  # npx needs PATH etc.; the API key rides along from .env
        inner = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=server.command, args=shlex.split(server.args), env=env,
                ),
                # ADK defaults to 5s — too short for a cold `npx -y` that must download
                # the package first (observed: firecrawl-mcp ConnectionError on first run).
                timeout=60.0,
            ),
            tool_filter=tool_filter,
        )
        return _make_safe_toolset(inner, name)
    if server.transport == "http":
        inner = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=os.environ[server.url_env],
                timeout=15.0,  # remote handshake; default 5s is tight over WAN
            ),
            tool_filter=tool_filter,
        )
        return _make_safe_toolset(inner, name)
    raise ValueError(f"unknown transport {server.transport!r} for mcp server {name!r}")


def mcp_status(cfg) -> list[dict]:
    """UI-facing status rows: name, transport, enabled, configured, domains, description."""
    servers = getattr(cfg, "mcp_servers", None) or {}
    return [
        {
            "name": name,
            "transport": s.transport,
            "enabled": s.enabled,
            "configured": _secret_set(s),
            "secret_env": s.api_key_env or s.url_env,
            "domains": s.domains,
            "tools": s.tool_filter,
            "description": s.description,
        }
        for name, s in servers.items()
    ]
