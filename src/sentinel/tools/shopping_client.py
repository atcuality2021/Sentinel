"""SENTINEL-022 — programmatic SearchAPI MCP client for e-commerce price discovery.

The SearchAPI shopping engines are reachable only over the MCP transport: the token embedded in
``SEARCHAPI_MCP_URL`` authenticates the streamable-HTTP MCP session, *not* the REST ``api_key``
endpoint (which 401s). So this client speaks MCP programmatically — using the official ``mcp`` SDK's
``streamablehttp_client`` + ``ClientSession`` — rather than ADK's ``McpToolset`` (which only exposes
tools *to* an agent and gives the cascade no callable handle).

Two calls, verified live 2026-06-14 against the real engine:

* :func:`call_shopping_search` — ``google_shopping_search`` → candidate models with a ``product_token``.
* :func:`call_google_product` — ``google_product`` → per-seller ``offers`` for one token (direct
  retailer links + merchant = best-deal-across-sellers).

Every public call is **fail-soft**: a missing URL, transport error, or parse failure returns ``[]``
so the cascade advances to its SERP/Firecrawl fallback instead of breaking the research run. The
``SEARCHAPI_MCP_URL`` value is read from the environment and never logged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sentinel.tools.shopping import PricedRow

logger = logging.getLogger(__name__)

_SEARCHAPI_URL_ENV = "SEARCHAPI_MCP_URL"


def _searchapi_url() -> str | None:
    url = os.getenv(_SEARCHAPI_URL_ENV)
    return url.strip() if url else None


def _extract_json(result: Any) -> dict | None:
    """Pull the JSON payload out of an MCP ``CallToolResult``.

    SearchAPI returns the engine JSON as a text content block; some servers also populate
    ``structuredContent``. Try text first, then structured, then give up (``None``).
    """
    if result is None:
        return None
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                parsed = json.loads(text)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    structured = getattr(result, "structuredContent", None)
    return structured if isinstance(structured, dict) else None


def _norm_merchant(value: object) -> str:
    """Seller name as a string. ``google_product`` offers carry ``merchant`` as a
    ``{"name", "favicon"}`` dict (verified live); ``google_shopping_search`` carries a plain string.
    """
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    return str(value or "").strip()


def _norm_price(row: dict) -> str:
    """Prefer a human-readable currency string; fall back to the numeric ``extracted_*`` field."""
    for key in ("total_price", "price"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    for key in ("extracted_total_price", "extracted_price"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def normalize_shopping(payload: dict | None) -> list[PricedRow]:
    """Map a ``google_shopping_search`` payload to :class:`PricedRow`s (verified field names)."""
    if not isinstance(payload, dict):
        return []
    rows: list[PricedRow] = []
    for r in payload.get("shopping_results") or []:
        if not isinstance(r, dict):
            continue
        row: PricedRow = {
            "title": str(r.get("title") or "").strip(),
            "price": _norm_price(r),
            "source_url": str(r.get("product_link") or r.get("offers_link") or "").strip(),
            "seller": _norm_merchant(r.get("seller")),
            "product_token": str(r.get("product_token") or "").strip(),
        }
        if row["title"]:
            rows.append(row)
    return rows


def normalize_offers(payload: dict | None) -> list[PricedRow]:
    """Map a ``google_product`` payload's ``offers[]`` to per-seller :class:`PricedRow`s.

    These carry the *direct retailer* ``link`` and ``merchant`` — the best-deal-across-sellers view.
    """
    if not isinstance(payload, dict):
        return []
    rows: list[PricedRow] = []
    for o in payload.get("offers") or []:
        if not isinstance(o, dict):
            continue
        merchant = _norm_merchant(o.get("merchant"))
        row: PricedRow = {
            "title": str(o.get("title") or "").strip() or merchant,
            "price": _norm_price(o),
            "source_url": str(o.get("link") or "").strip(),
            "seller": merchant,
        }
        if row["seller"] or row["source_url"]:
            rows.append(row)
    return rows


async def _call_tool(tool_name: str, arguments: dict, *, url: str | None = None) -> dict | None:
    """Open a one-shot MCP session, call *tool_name*, return the parsed JSON payload (or ``None``).

    Fail-soft: any transport/protocol error is logged by exception type (never the URL) and yields
    ``None`` so callers degrade to ``[]``.
    """
    target = url or _searchapi_url()
    if not target:
        logger.warning("searchapi MCP: %s is not set; shopping unavailable", _SEARCHAPI_URL_ENV)
        return None
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(target) as (read, write, _get_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
        if getattr(result, "isError", False):
            logger.warning("searchapi MCP: tool %s returned isError", tool_name)
            return None
        return _extract_json(result)
    except Exception as exc:  # noqa: BLE001 — fail-soft boundary; cascade falls back on []
        logger.warning("searchapi MCP call %s failed: %s", tool_name, type(exc).__name__)
        return None


async def call_shopping_search(
    query: str, *, gl: str = "in", url: str | None = None
) -> list[PricedRow]:
    """Run ``google_shopping_search`` for *query*; return normalized priced rows (``[]`` on failure)."""
    if not query or not query.strip():
        return []
    payload = await _call_tool("google_shopping_search", {"q": query.strip(), "gl": gl}, url=url)
    return normalize_shopping(payload)


async def call_google_product(
    product_token: str, *, gl: str = "in", url: str | None = None
) -> list[PricedRow]:
    """Run ``google_product`` for *product_token*; return per-seller offers (``[]`` on failure)."""
    if not product_token or not product_token.strip():
        return []
    payload = await _call_tool(
        "google_product", {"product_token": product_token.strip(), "gl": gl}, url=url
    )
    return normalize_offers(payload)
