# tests/test_memory_brain_connectors.py
"""Tests for the four Self-Driving Memory Brain source connectors (Task 5 of 10).

All tests mock the internal _scrape_and_extract / _search_and_extract /
_read_and_extract methods so the MCP / LLM infrastructure is never invoked.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from sentinel.memory.connectors.base import SourceFinding, TRUST_SCORES
from sentinel.memory.schema import DataBoundary


@pytest.mark.asyncio
async def test_website_connector_returns_findings():
    from sentinel.memory.connectors.website import WebsiteConnector
    connector = WebsiteConnector()
    mock_findings = [
        SourceFinding(text="Acme HQ in Mumbai.", boundary=DataBoundary.PUBLIC,
                      source_type="website", source_url="https://acme.com",
                      source_label="Acme website", trust_score=TRUST_SCORES["website"])
    ]
    with patch.object(connector, "_scrape_and_extract", new=AsyncMock(return_value=mock_findings)):
        result = await connector.fetch("Acme Corp", {"website_url": "https://acme.com"})
    assert len(result) == 1
    assert result[0].trust_score == 0.8


@pytest.mark.asyncio
async def test_website_connector_returns_empty_when_no_url():
    from sentinel.memory.connectors.website import WebsiteConnector
    result = await WebsiteConnector().fetch("Acme Corp", {})
    assert result == []


@pytest.mark.asyncio
async def test_youtube_connector_returns_findings():
    from sentinel.memory.connectors.youtube import YouTubeConnector
    connector = YouTubeConnector()
    mock_findings = [
        SourceFinding(text="Acme demo video June 2026.", boundary=DataBoundary.PUBLIC,
                      source_type="youtube", source_url="https://youtube.com/watch?v=abc",
                      source_label="YouTube — Acme demo", trust_score=TRUST_SCORES["youtube"])
    ]
    with patch.object(connector, "_search_and_extract", new=AsyncMock(return_value=mock_findings)):
        result = await connector.fetch("Acme Corp", {"youtube_channel": "@acmecorp"})
    assert result[0].trust_score == 0.7


@pytest.mark.asyncio
async def test_email_connector_findings_are_always_private():
    from sentinel.memory.connectors.email import EmailConnector
    connector = EmailConnector()
    mock_findings = [
        SourceFinding(text="Deal signed.", boundary=DataBoundary.PUBLIC,  # intentionally wrong
                      source_type="email", source_url="gmail://",
                      source_label="Email", trust_score=TRUST_SCORES["email"])
    ]
    with patch.object(connector, "_read_and_extract", new=AsyncMock(return_value=mock_findings)):
        result = await connector.fetch("Acme Corp", {"email_filter": "from:acme.com"})
    assert all(f.boundary == DataBoundary.PRIVATE for f in result)


@pytest.mark.asyncio
async def test_email_connector_returns_empty_when_no_filter():
    from sentinel.memory.connectors.email import EmailConnector
    result = await EmailConnector().fetch("Acme Corp", {})
    assert result == []


@pytest.mark.asyncio
async def test_social_connector_returns_findings():
    from sentinel.memory.connectors.social import SocialConnector
    connector = SocialConnector()
    mock_findings = [
        SourceFinding(text="Acme raised Series A.", boundary=DataBoundary.PUBLIC,
                      source_type="social", source_url="https://twitter.com/acme/status/1",
                      source_label="Twitter — @acmecorp", trust_score=TRUST_SCORES["social"])
    ]
    with patch.object(connector, "_search_and_extract", new=AsyncMock(return_value=mock_findings)):
        result = await connector.fetch("Acme Corp", {"social_handles": '{"twitter": "@acmecorp"}'})
    assert result[0].trust_score == 0.5
