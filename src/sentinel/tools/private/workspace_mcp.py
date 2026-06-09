"""Private boundary — Google Workspace MCP connector (SRS FR-04 / NFR-05).

The private toolset is built from env config so the agent stays runnable before OAuth is
wired (decision Q-1). When unconfigured, ``build_private_toolset`` returns ``None`` and the
caller degrades to public-only with a flagged gap (FR-10).

Transports:
  - stdio : SENTINEL_MCP_COMMAND + SENTINEL_MCP_ARGS  (e.g. a local Workspace MCP server)
  - http  : SENTINEL_MCP_URL                          (remote streamable-HTTP MCP server)

``tool_filter`` pins the connector to read-only operations — scope enforcement at the tool
layer, not by prompt (NFR-05). Anything not in the allow-list is unreachable to the agent.
"""

from __future__ import annotations

import os
import shlex

# Read-only allow-list. Extend per the connected server's actual tool names.
READONLY_WORKSPACE_TOOLS = [
    "search_documents",
    "get_document",
    "list_calendar_events",
    "search_messages",
    "get_contact",
]


def build_private_toolset():
    """Return a configured McpToolset, or None if no MCP transport is configured."""
    transport = os.getenv("SENTINEL_MCP_TRANSPORT", "").lower()
    if not transport:
        return None

    from google.adk.tools import McpToolset
    from google.adk.tools.mcp_tool import (
        StdioConnectionParams,
        StreamableHTTPConnectionParams,
    )

    tool_filter = (
        os.getenv("SENTINEL_MCP_TOOL_FILTER", "").split(",")
        if os.getenv("SENTINEL_MCP_TOOL_FILTER")
        else READONLY_WORKSPACE_TOOLS
    )

    if transport == "stdio":
        from mcp import StdioServerParameters

        command = os.environ["SENTINEL_MCP_COMMAND"]
        args = shlex.split(os.getenv("SENTINEL_MCP_ARGS", ""))
        return McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(command=command, args=args),
            ),
            tool_filter=tool_filter,
        )

    if transport == "http":
        url = os.environ["SENTINEL_MCP_URL"]
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=url),
            tool_filter=tool_filter,
        )

    raise ValueError(f"Unknown SENTINEL_MCP_TRANSPORT={transport!r} (expected 'stdio' or 'http')")


def private_boundary_configured() -> bool:
    return bool(os.getenv("SENTINEL_MCP_TRANSPORT"))
