"""SENTINEL-022 — find_deals cascade tests.

Step 2 covers the pure policy (shopping_results_thin, classify_query_class). Step 4 appends the
orchestrator tests (the shopping → SERP → Firecrawl branch logic with injected fake legs).
"""

import asyncio

from sentinel.tools.shopping import (
    DEFAULT_MIN_PRICED,
    TOOL_FIRECRAWL,
    TOOL_SERP,
    TOOL_SHOPPING,
    build_deal_search_tool,
    classify_query_class,
    shopping_results_thin,
)


# --------------------------------------------------------------------------- #
# shopping_results_thin (the cascade's deterministic pivot)
# --------------------------------------------------------------------------- #

def _row(price):
    return {"title": "Lenovo LOQ", "price": price, "source_url": "https://x", "seller": "Flipkart"}


def test_three_priced_rows_is_not_thin():
    rows = [_row("₹63,990"), _row("₹75,999"), _row("₹88,000")]
    assert shopping_results_thin(rows) is False


def test_two_priced_plus_priceless_is_thin():
    rows = [_row("₹63,990"), _row("₹75,999"), _row(None), _row(""), _row("   ")]
    # only 2 carry a usable price < default min of 3
    assert shopping_results_thin(rows) is True


def test_empty_and_none_are_thin():
    assert shopping_results_thin([]) is True
    assert shopping_results_thin(None) is True


def test_min_priced_threshold_is_tunable():
    rows = [_row("₹1"), _row("₹2")]
    assert shopping_results_thin(rows, min_priced=2) is False
    assert shopping_results_thin(rows, min_priced=3) is True


def test_default_min_priced_constant():
    assert DEFAULT_MIN_PRICED == 3


def test_non_dict_rows_are_not_priced():
    # a malformed leg returning strings must not crash the pivot
    assert shopping_results_thin(["junk", 42, None]) is True


# --------------------------------------------------------------------------- #
# classify_query_class (bounded learning key)
# --------------------------------------------------------------------------- #

def test_buying_queries_share_one_bounded_key():
    a = classify_query_class("product_research", "best laptop under 80000 INR")
    b = classify_query_class("product_research", "cheapest phone with the best price")
    assert a == b == "product_research:shopping"


def test_non_buying_query_is_research_bucket():
    assert classify_query_class("software", "compare orchestration frameworks") \
        == "software:research"


def test_domain_is_normalized():
    assert classify_query_class("Product Research", "buy cheap thing") \
        == "product_research:shopping"


def test_empty_domain_falls_back_to_general():
    assert classify_query_class("", "buy now").startswith("general:")


# --------------------------------------------------------------------------- #
# build_deal_search_tool — the deterministic cascade (injected fake legs, no network)
# --------------------------------------------------------------------------- #

def _priced(n, price="₹9,999"):
    return [{"title": f"item {i}", "price": price, "source_url": f"https://x/{i}",
             "seller": "Flipkart"} for i in range(n)]


class _Spy:
    """A fake async leg that records the inputs it was called with and returns canned rows."""
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    async def __call__(self, arg):
        self.calls.append(arg)
        return self.rows


class _DictPrefs:
    """In-memory stand-in for ToolPreferenceStore (no DB)."""
    def __init__(self, seed=None):
        self.d = dict(seed or {})
        self.records = []
    def get(self, qc):
        return self.d.get(qc)
    def record(self, qc, tool):
        self.d[qc] = tool
        self.records.append((qc, tool))


def test_path_a_shopping_hits_skips_fallbacks_and_records():
    shopping, serp, fc = _Spy(_priced(5)), _Spy(_priced(5)), _Spy(_priced(5))
    prefs = _DictPrefs()
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=prefs)
    out = asyncio.run(tool("best laptop under 80000 price"))
    assert out["status"] == "success" and out["tool"] == TOOL_SHOPPING
    assert len(out["results"]) == 5
    assert len(shopping.calls) == 1
    assert serp.calls == [] and fc.calls == []          # fallbacks NOT called
    assert prefs.d["product_research:shopping"] == TOOL_SHOPPING


def test_path_b_shopping_thin_falls_to_serp():
    shopping, serp, fc = _Spy(_priced(1)), _Spy(_priced(5)), _Spy(_priced(5))
    prefs = _DictPrefs()
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=prefs)
    out = asyncio.run(tool("buy cheap laptop"))
    assert out["tool"] == TOOL_SERP
    assert len(shopping.calls) == 1 and len(serp.calls) == 1
    assert fc.calls == []                                # firecrawl NOT reached
    assert prefs.d["product_research:shopping"] == TOOL_SERP


def test_path_c_both_thin_firecrawl_gets_concrete_candidate():
    # shopping returns 1 priced row with a real URL; serp thin → firecrawl must receive THAT url,
    # not merely be called (anti-vacuous-spy / AP#10).
    shopping = _Spy([{"title": "Lenovo", "price": "₹63,990",
                      "source_url": "https://flipkart.com/loq", "seller": "Flipkart"}])
    serp, fc = _Spy([]), _Spy(_priced(5))
    prefs = _DictPrefs()
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=prefs)
    out = asyncio.run(tool("buy laptop deal"))
    assert out["tool"] == TOOL_FIRECRAWL
    assert fc.calls == ["https://flipkart.com/loq"]      # concrete top-candidate, not the query
    assert prefs.d["product_research:shopping"] == TOOL_FIRECRAWL


def test_path_c_no_candidate_url_falls_back_to_query():
    shopping, serp, fc = _Spy([]), _Spy([]), _Spy(_priced(5))
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=_DictPrefs())
    asyncio.run(tool("buy laptop deal"))
    assert fc.calls == ["buy laptop deal"]               # no URL anywhere → raw query


def test_all_thin_returns_thin_status():
    shopping, serp, fc = _Spy([]), _Spy([]), _Spy([])
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=_DictPrefs())
    out = asyncio.run(tool("buy laptop deal"))
    assert out["status"] == "thin"


def test_learned_serp_winner_is_tried_first():
    # prefs already say SERP won for this class → serp must be called before shopping
    prefs = _DictPrefs(seed={"product_research:shopping": TOOL_SERP})
    shopping, serp, fc = _Spy(_priced(5)), _Spy(_priced(5)), _Spy(_priced(5))
    tool = build_deal_search_tool(domain="product_research", shopping_leg=shopping,
                                  serp_leg=serp, firecrawl_leg=fc, prefs=prefs)
    out = asyncio.run(tool("buy cheap laptop price"))
    assert out["tool"] == TOOL_SERP
    assert len(serp.calls) == 1 and shopping.calls == []  # shopping skipped


def test_empty_query_is_error():
    tool = build_deal_search_tool(domain="product_research", shopping_leg=_Spy(_priced(5)),
                                  serp_leg=_Spy([]), firecrawl_leg=_Spy([]), prefs=_DictPrefs())
    out = asyncio.run(tool("   "))
    assert out["status"] == "error"


def test_works_without_prefs_store():
    # prefs=None must not break the cascade (degradation-safe)
    tool = build_deal_search_tool(domain="product_research", shopping_leg=_Spy(_priced(5)),
                                  serp_leg=_Spy([]), firecrawl_leg=_Spy([]), prefs=None)
    out = asyncio.run(tool("buy laptop"))
    assert out["tool"] == TOOL_SHOPPING
