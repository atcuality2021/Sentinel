# src/sentinel/memory/connectors/social.py
"""Social connector — searches Twitter/LinkedIn via SearchAPI MCP and extracts public facts."""
from __future__ import annotations

import json
import logging

from sentinel.memory.connectors.base import SourceConnector, SourceFinding, TRUST_SCORES
from sentinel.memory.schema import DataBoundary

log = logging.getLogger(__name__)


class SocialConnector(SourceConnector):
    @property
    def source_type(self) -> str:
        return "social"

    async def fetch(self, entity: str, config: dict[str, object]) -> list[SourceFinding]:
        handles_raw = config.get("social_handles", "{}")
        try:
            handles: dict[str, str] = (
                json.loads(handles_raw) if isinstance(handles_raw, str) else (handles_raw or {})
            )
        except Exception as exc:
            log.debug("social.py: malformed social_handles config %r — %s", handles_raw, exc)
            handles = {}

        query_parts: list[str] = []
        if handles.get("twitter"):
            query_parts.append(f"site:twitter.com {handles['twitter']}")
        if handles.get("linkedin"):
            query_parts.append(f"site:linkedin.com {entity}")
        if not query_parts:
            query_parts = [f"site:twitter.com OR site:linkedin.com {entity}"]

        return await self._search_and_extract(entity, " OR ".join(query_parts))

    async def _search_and_extract(self, entity: str, query: str) -> list[SourceFinding]:
        try:
            from sentinel.tools.mcp_registry import get_mcp_tool
            searchapi = get_mcp_tool("searchapi")
            result = await searchapi.call("google_search", q=query, num=5)
            items = result.get("organic_results", [])[:5]
            if not items:
                return []
            raw = "\n\n".join(
                f"Title: {r.get('title', '')}\nSnippet: {r.get('snippet', '')}"
                for r in items
            )
            url = items[0].get("link", "") if items else ""
            from sentinel.memory.connectors._extractor import extract_findings
            return await extract_findings(
                entity,
                "social",
                raw,
                url,
                trust_score=TRUST_SCORES["social"],
                boundary=DataBoundary.PUBLIC,
            )
        except Exception as exc:
            log.warning("SocialConnector error for %r: %s", entity, exc)
            return []
