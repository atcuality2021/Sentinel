# src/sentinel/memory/connectors/youtube.py
"""YouTube source connector — searches for channel/entity videos via SearchAPI MCP."""
from __future__ import annotations

import logging

from sentinel.memory.connectors.base import SourceConnector, SourceFinding, TRUST_SCORES
from sentinel.memory.schema import DataBoundary

log = logging.getLogger(__name__)


class YouTubeConnector(SourceConnector):
    @property
    def source_type(self) -> str:
        return "youtube"

    async def fetch(self, entity: str, config: dict[str, object]) -> list[SourceFinding]:
        channel = config.get("youtube_channel", "")
        query = f"site:youtube.com {channel or entity}"
        return await self._search_and_extract(entity, query)

    async def _search_and_extract(self, entity: str, query: str) -> list[SourceFinding]:
        try:
            from sentinel.tools.mcp_registry import get_mcp_tool
            searchapi = get_mcp_tool("searchapi")
            result = await searchapi.call("youtube_search", q=query, num=3)
            videos = result.get("organic_results", [])[:3]
            if not videos:
                return []
            raw = "\n\n".join(
                f"Title: {v.get('title', '')}\nDescription: {v.get('description', '')}"
                f"\nSnippet: {v.get('snippet', '')}\nCaptions: {v.get('captions', '')}"
                for v in videos
            )
            urls = [v.get("link", "") for v in videos]
            from sentinel.memory.connectors._extractor import extract_findings
            return await extract_findings(
                entity,
                "youtube",
                raw,
                urls[0] if urls else "",
                trust_score=TRUST_SCORES["youtube"],
                boundary=DataBoundary.PUBLIC,
            )
        except Exception as exc:
            log.warning("YouTubeConnector error for %r: %s", entity, exc)
            return []
