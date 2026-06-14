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

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:  # avoid importing the store at module load (keeps this file I/O-free)
    from sentinel.memory.store import ToolPreferenceStore

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


# --------------------------------------------------------------------------- #
# Cascade orchestrator (Step 4) — the deterministic find_deals tool
# --------------------------------------------------------------------------- #

# Canonical tool names recorded in ToolPreferenceStore + reported to the synthesizer.
TOOL_SHOPPING = "google_shopping_search"
TOOL_SERP = "web_search"
TOOL_FIRECRAWL = "firecrawl"

# A cascade leg: query (or, for firecrawl, a candidate URL) → normalized priced rows.
DealLeg = Callable[[str], Awaitable[list[PricedRow]]]


def _top_candidate(rows: list[PricedRow] | None) -> str:
    """First usable source URL among *rows* (the page firecrawl should deep-read), or ``""``."""
    for r in rows or []:
        if isinstance(r, dict) and r.get("source_url"):
            return str(r["source_url"])
    return ""


def build_deal_search_tool(
    *,
    domain: str,
    shopping_leg: DealLeg,
    serp_leg: DealLeg,
    firecrawl_leg: DealLeg,
    prefs: "ToolPreferenceStore | None" = None,
    min_priced: int = DEFAULT_MIN_PRICED,
) -> DealLeg:
    """Assemble the injected legs into the async ``find_deals`` tool the product-research agent calls.

    Deterministic cascade: the two query-driven legs (shopping, then SERP) run in order until one
    returns non-thin priced rows; if both are thin, the firecrawl leg deep-reads the best candidate
    URL (or the raw query) as a last resort. The winning leg is recorded in *prefs* per query-class,
    and on the next call a recorded SERP win is tried before shopping (so a query-class where
    shopping never works stops paying the wasted shopping call). Legs are injected, so this whole
    decision path is unit-tested with fakes — no network.
    """
    legmap: dict[str, tuple[DealLeg, str]] = {
        "shopping": (shopping_leg, TOOL_SHOPPING),
        "serp": (serp_leg, TOOL_SERP),
    }

    async def find_deals(query: str) -> dict:
        """Find current e-commerce prices and the best deal for a product query.

        Use this for ANY pricing question — it returns live priced listings from shopping engines
        (and per-seller offers) so you can name exact prices, sellers, and the best value. Returns
        ``{status, tool, results}`` where each result has ``title``, ``price``, ``source_url``,
        ``seller``. Cite the ``source_url``. Prefer this over generic web search for prices.
        """
        q = (query or "").strip()
        if not q:
            return {"status": "error", "message": "empty query", "results": []}

        qclass = classify_query_class(domain, q)
        order = ["shopping", "serp"]
        if prefs is not None and prefs.get(qclass) == TOOL_SERP:
            order = ["serp", "shopping"]  # learned: skip the wasted shopping call first

        best: list[PricedRow] = []
        for name in order:
            leg, tool_name = legmap[name]
            rows = await leg(q)
            if rows:
                best = rows
            if not shopping_results_thin(rows, min_priced=min_priced):
                if prefs is not None:
                    prefs.record(qclass, tool_name)
                return {"status": "success", "tool": tool_name, "results": rows}

        # last resort: deep-read the best candidate page (a real URL if we have one, else the query)
        candidate = _top_candidate(best) or q
        fc_rows = await firecrawl_leg(candidate)
        if fc_rows:
            best = fc_rows
            if not shopping_results_thin(fc_rows, min_priced=min_priced) and prefs is not None:
                prefs.record(qclass, TOOL_FIRECRAWL)
            return {"status": "success", "tool": TOOL_FIRECRAWL, "results": fc_rows}

        # everything was thin — return the richest partial set we saw, flagged thin for the synthesizer
        return {"status": "thin", "tool": legmap[order[-1]][1], "results": best}

    find_deals.__name__ = "find_deals"
    return find_deals
