"""SENTINEL-022 — deterministic price-discovery cascade for product research.

The agent proved it skips ``google_shopping_search`` even when the tool is on its menu (spec
Evidence: a real run returned 0 products while the tool sat unused). So the price path is taken
out of the model's hands: a single ``find_deals`` function-tool owns a deterministic
shopping → SERP → Firecrawl cascade, and the prompt merely directs the agent to call it.

This module is split by concern:

* **Pure policy** (this file, Step 2) — :func:`shopping_results_thin` (the cascade's branch
  pivot) and :func:`classify_query_class` (the learning key). No I/O, no ``mcp``/network import,
  so the cascade's branch logic is unit-tested with zero transport.
* **Cascade orchestrator** (:func:`build_deal_search_tool`, Step 4) — assembles injected legs into
  the ADK ``find_deals`` tool.
* **MCP shopping client** (``tools/shopping_client.py``, Step 3) — the real shopping leg.

:class:`PricedRow` is the data contract the policy defines and the client (Step 3) produces.
"""

from __future__ import annotations

from typing import TypedDict

# OQ-3 (design): "thin" shopping results = fewer than this many rows carrying a usable price.
# One named constant so the threshold is one-line tunable and pinned by a unit test.
DEFAULT_MIN_PRICED = 3


class PricedRow(TypedDict, total=False):
    """One normalized priced listing. The shopping client emits these; the cascade consumes them.

    ``total=False`` because a SERP/Firecrawl fallback row may carry only a subset (e.g. a title +
    url with no parsed price) — :func:`shopping_results_thin` is what decides whether the subset is
    rich enough to stop the cascade.
    """

    title: str
    price: str
    source_url: str
    seller: str
    product_token: str


def _is_priced(row: object) -> bool:
    """True when *row* carries a non-empty price value.

    A price of ``None`` or an empty/whitespace string is "not priced" — those rows are listings the
    cascade cannot turn into a :class:`~sentinel.artifacts.schemas.ProductOption`.
    """
    if not isinstance(row, dict):
        return False
    price = row.get("price")
    return price is not None and str(price).strip() != ""


def shopping_results_thin(
    results: list[PricedRow] | None, *, min_priced: int = DEFAULT_MIN_PRICED
) -> bool:
    """Return True when *results* are too thin to stop the cascade (fewer than *min_priced* priced rows).

    This is the single deterministic decision the cascade pivots on: a non-thin shopping result
    short-circuits the fallbacks; a thin one advances to the next leg (SERP, then Firecrawl).
    Empty/``None`` is always thin.
    """
    if not results:
        return True
    priced = sum(1 for r in results if _is_priced(r))
    return priced < min_priced


# Coarse intent buckets — bounded so the tool_preference table never grows with raw query text.
_BUYING_HINTS = (
    "price", "buy", "deal", "cheap", "cheapest", "under", "below", "best value",
    "discount", "offer", "lowest", "₹", "rs.", "rs ", "$", "budget",
)


def classify_query_class(domain: str, target: str) -> str:
    """Map (domain, query) to a coarse, bounded preference key, e.g. ``"product_research:shopping"``.

    The key is intentionally low-cardinality — ``{domain}:{intent}`` where *intent* is one of two
    buckets (``shopping`` when the query reads like a buying request, else ``research``). This caps
    the :class:`~sentinel.memory.store.ToolPreferenceStore` at a handful of rows and lets the learned
    signal generalize across similar buying queries instead of memorizing each phrasing.
    """
    d = (domain or "general").strip().lower().replace(" ", "_") or "general"
    t = (target or "").lower()
    intent = "shopping" if any(h in t for h in _BUYING_HINTS) else "research"
    return f"{d}:{intent}"
