"""SENTINEL-022 — find_deals cascade tests.

Step 2 covers the pure policy (shopping_results_thin, classify_query_class). Step 4 appends the
orchestrator tests (the shopping → SERP → Firecrawl branch logic with injected fake legs).
"""

from sentinel.tools.shopping import (
    DEFAULT_MIN_PRICED,
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
