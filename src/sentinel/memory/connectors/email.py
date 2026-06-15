# src/sentinel/memory/connectors/email.py
"""Email source connector — reads Gmail threads via Gmail MCP and extracts private facts."""
from __future__ import annotations

import logging

from sentinel.memory.connectors.base import SourceConnector, SourceFinding, TRUST_SCORES
from sentinel.memory.schema import DataBoundary

log = logging.getLogger(__name__)


class EmailConnector(SourceConnector):
    source_type = "email"

    async def fetch(self, entity: str, config: dict[str, object]) -> list[SourceFinding]:
        email_filter = config.get("email_filter", "")
        if not email_filter:
            return []
        findings = await self._read_and_extract(entity, str(email_filter))
        # Defense-in-depth: force PRIVATE regardless of extractor output.
        # Email content is always user-private; the extractor must never tag it PUBLIC.
        return [f.model_copy(update={"boundary": DataBoundary.PRIVATE}) for f in findings]

    async def _read_and_extract(self, entity: str, email_filter: str) -> list[SourceFinding]:
        try:
            from sentinel.tools.mcp_registry import get_mcp_tool
            gmail = get_mcp_tool("gmail")
            result = await gmail.call("search_emails", query=email_filter, max_results=10)
            emails = result.get("messages", [])[:10]
            if not emails:
                return []
            raw = "\n\n".join(
                f"Subject: {e.get('subject', '')}\nSnippet: {e.get('snippet', '')}"
                for e in emails
            )
            from sentinel.memory.connectors._extractor import extract_findings
            return await extract_findings(
                entity,
                "email",
                raw,
                "gmail://",
                trust_score=TRUST_SCORES["email"],
                boundary=DataBoundary.PRIVATE,
            )
        except Exception as exc:
            log.warning("EmailConnector error for %r: %s", entity, exc)
            return []
