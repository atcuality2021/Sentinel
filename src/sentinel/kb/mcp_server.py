"""
Sentinel KB MCP server — exposes search_project_kb as an MCP tool.

Run as a subprocess (stdio transport) by ADK agents:
    SENTINEL_DATA_DIR=/path/to/data python3 -m sentinel.kb.mcp_server

ADK wiring (in orchestrator):
    from mcp import StdioServerParameters
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
    toolset = MCPToolset(StdioServerParameters(
        command="python3",
        args=["-m", "sentinel.kb.mcp_server"],
        env={"SENTINEL_DATA_DIR": str(data_dir), "EMBED_API_KEY": "...", "RERANK_API_KEY": "..."},
    ))
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .search import hybrid_search

_DATA_DIR = Path(os.environ.get("SENTINEL_DATA_DIR", "data"))

mcp = FastMCP(
    name="sentinel-kb",
    instructions=(
        "Search the project's Knowledge Base built from crawled web pages, "
        "social profiles, and uploaded documents. Use this tool BEFORE doing "
        "an open web search when the query is about the project or its domain."
    ),
)


@mcp.tool()
def search_project_kb(
    query: str,
    project_id: str,
    source_type: str = "all",
    top_k: int = 5,
) -> list[dict]:
    """
    Search the project Knowledge Base using hybrid BM25 + semantic retrieval
    with cross-encoder reranking.

    Args:
        query: Natural language search query (e.g. "What products does biltiq offer?")
        project_id: Project whose KB to search
        source_type: Filter by source — "web", "social", "document", or "all"
        top_k: Number of results (1-10)

    Returns:
        List of {url, title, text, source_type, score} dicts, best match first.
    """
    st = None if source_type == "all" else source_type
    results = hybrid_search(
        project_id=project_id,
        data_dir=_DATA_DIR,
        query=query,
        source_type=st,
        rerank_top_k=min(max(top_k, 1), 10),
    )
    return [r.to_dict() for r in results]


def run_server() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
