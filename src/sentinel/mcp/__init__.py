"""Sentinel MCP server package — SENTINEL-016 G-16.

Exposes Sentinel's memory and research results as MCP tools so other agents
in a multi-agent network can query the memory store, skill ratings, and
episodic run history without a direct Python import.

Usage (stdio transport, ADK client side):
    from mcp import StdioServerParameters
    from google.adk.tools import McpToolset
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="python3",
                args=["-m", "sentinel.mcp.server"],
                env={"SENTINEL_DATA_DIR": str(data_dir)},
            )
        )
    )
"""
