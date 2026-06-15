# src/sentinel/memory/connectors/website.py
"""Website source connector — scrapes key pages via Firecrawl MCP and extracts facts."""
from __future__ import annotations

import logging

from sentinel.memory.connectors.base import SourceConnector, SourceFinding, TRUST_SCORES
from sentinel.memory.schema import DataBoundary

log = logging.getLogger(__name__)

# Common paths to probe on a company website
_PATHS = ["/", "/about", "/pricing", "/blog"]


class WebsiteConnector(SourceConnector):
    @property
    def source_type(self) -> str:
        return "website"

    async def fetch(self, entity: str, config: dict[str, object]) -> list[SourceFinding]:
        url = config.get("website_url", "")
        if not url:
            return []
        return await self._scrape_and_extract(entity, str(url))

    async def _scrape_and_extract(self, entity: str, base_url: str) -> list[SourceFinding]:
        try:
            from sentinel.tools.mcp_registry import get_mcp_tool
            firecrawl = get_mcp_tool("firecrawl")
            findings: list[SourceFinding] = []
            for path in _PATHS:
                target_url = base_url.rstrip("/") + path
                try:
                    result = await firecrawl.call("firecrawl_scrape", url=target_url)
                    text = result.get("markdown", "") or result.get("content", "")
                    if not text:
                        continue
                    extracted = await _extract_facts(entity, text, target_url)
                    findings.extend(extracted)
                except Exception as exc:
                    log.debug("scrape %s failed: %s", target_url, exc)
            return findings
        except Exception as exc:
            log.warning("WebsiteConnector error for %r: %s", entity, exc)
            return []


async def _extract_facts(entity: str, raw_text: str, url: str) -> list[SourceFinding]:
    from sentinel.memory.connectors._extractor import extract_findings
    return await extract_findings(
        entity,
        "website",
        raw_text,
        url,
        trust_score=TRUST_SCORES["website"],
        boundary=DataBoundary.PUBLIC,
    )
