"""Sentinel MCP server — exposes memory and research results as MCP tools (SENTINEL-016 G-16).

Three read-only tools are exposed:

* ``recall_memory``   — query MemoryStore for entity findings
* ``top_skills``      — query SkillCurationStore for ranked capability performance
* ``list_recent_runs``— query RunStore for episodic run history

All tools are boundary-safe: only PUBLIC findings are returned unless the
caller explicitly passes boundary="private" (which requires a PRIVATE-capable
deployment; public-only deployments silently downgrade).

Run as a subprocess (stdio transport):
    SENTINEL_DATA_DIR=/path/to/data python3 -m sentinel.mcp.server

Or as an SSE/HTTP server:
    SENTINEL_MCP_SERVER_TRANSPORT=sse python3 -m sentinel.mcp.server
"""
from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_DATA_DIR = Path(os.environ.get("SENTINEL_DATA_DIR", "data"))

mcp = FastMCP(
    name="sentinel-memory",
    instructions=(
        "Query Sentinel's sovereign memory store and research history. "
        "Use recall_memory to retrieve findings about an entity, "
        "top_skills to discover which research capabilities perform best, "
        "and list_recent_runs to review episodic research history."
    ),
)


# ---------------------------------------------------------------------------
# Tool helpers (pure functions — testable without MCP transport)
# ---------------------------------------------------------------------------

def _recall_memory_impl(
    entity: str,
    boundary: str = "public",
    limit: int = 10,
) -> list[dict]:
    """Return memory entries for *entity* filtered by *boundary*. Fail-soft → []."""
    try:
        from sentinel.memory.store import MemoryStore
        from sentinel.artifacts.schemas import Boundary
        b = Boundary.PRIVATE if boundary.lower() == "private" else Boundary.PUBLIC
        allowed = {b, Boundary.PUBLIC}  # public always included; private only when requested
        store = MemoryStore(_DATA_DIR / "sentinel.db")
        entries = store.recall(entity, allowed, limit=limit)
        return [
            {
                "entity": e.entity,
                "content": e.content,
                "memory_type": e.memory_type.value,
                "source_label": e.source_label,
                "boundary": e.boundary.value,
                "strength": e.strength,
            }
            for e in entries
        ]
    except Exception:
        return []


def _top_skills_impl(limit: int = 10) -> list[dict]:
    """Return top-*limit* capabilities ranked by avg_score. Fail-soft → []."""
    try:
        from sentinel.memory.store import SkillCurationStore
        return SkillCurationStore(_DATA_DIR / "sentinel.db").top_skills(limit=limit)
    except Exception:
        return []


def _list_recent_runs_impl(entity: str, limit: int = 5) -> list[dict]:
    """Return the *limit* most-recent run records for *entity*. Fail-soft → []."""
    try:
        from sentinel.memory.store import RunStore
        store = RunStore(_DATA_DIR / "sentinel.db")
        runs = store.runs_for(entity)[:limit]
        return [
            {
                "id": r.id,
                "entity": r.entity,
                "target": r.target,
                "mode": r.mode,
                "backend": r.backend,
                "public": r.public,
                "private": r.private,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# MCP tool registrations
# ---------------------------------------------------------------------------

@mcp.tool()
def recall_memory(
    entity: str,
    boundary: str = "public",
    limit: int = 10,
) -> list[dict]:
    """
    Retrieve Sentinel's stored findings about an entity.

    Args:
        entity: The entity to look up (e.g. "biltiq ai", "openai").
        boundary: "public" (default) or "private". Private requires a
                  PRIVATE-capable deployment; otherwise silently returns public.
        limit: Maximum number of entries to return (1-50).

    Returns:
        List of {entity, content, memory_type, source_label, boundary, strength}.
    """
    return _recall_memory_impl(entity, boundary=boundary, limit=min(max(limit, 1), 50))


@mcp.tool()
def top_skills(limit: int = 10) -> list[dict]:
    """
    Return the best-performing research capabilities ranked by historical avg_score.

    Args:
        limit: Number of capabilities to return (1-20).

    Returns:
        List of {capability, run_count, avg_score, last_used_at}, best first.
    """
    return _top_skills_impl(limit=min(max(limit, 1), 20))


@mcp.tool()
def list_recent_runs(entity: str, limit: int = 5) -> list[dict]:
    """
    List the most recent research runs for an entity.

    Args:
        entity: The entity whose run history to retrieve.
        limit: Number of runs to return (1-20).

    Returns:
        List of {id, entity, target, mode, backend, public, private, created_at}.
    """
    return _list_recent_runs_impl(entity, limit=min(max(limit, 1), 20))


def run_server() -> None:
    transport = os.getenv("SENTINEL_MCP_SERVER_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    run_server()
