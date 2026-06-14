"""SENTINEL-022 Step 7 — live e2e proof for product price discovery (AC5).

Skip-marked when the SearchAPI MCP is not configured, so CI stays green offline. When the engine is
reachable, this drives the real ``find_deals`` cascade (live ``google_shopping_search`` +
``google_product``) and asserts it surfaces real priced products with sources — the end-to-end proof
that product_research can reach e-commerce prices. The full-pipeline ``products_found ≥ 5`` synthesis
assertion is demonstrated by a live server run (recorded in the reflect note), not in CI, since it
needs a live LLM backend and would be flaky.
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("SEARCHAPI_MCP_URL"),
    reason="live SearchAPI MCP not configured (SEARCHAPI_MCP_URL unset)",
)


def test_find_deals_returns_at_least_5_priced_products_live(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))  # don't touch the real DB
    from sentinel.agent.modes.spec import _build_product_deal_tool
    from sentinel.config.schema import SentinelConfig

    tool = _build_product_deal_tool(SentinelConfig.default())
    out = asyncio.run(tool("best laptop under 80000 INR 16GB RAM RTX graphics for video editing"))

    assert out["status"] == "success"
    assert out["tool"] == "google_shopping_search"   # the priced path won, not a fallback
    results = out.get("results", [])
    priced = [r for r in results if r.get("price") and r.get("source_url")]
    assert len(priced) >= 5, f"expected >=5 priced products with sources, got {len(priced)}"
    # at least one offer carries a named seller (the best-deal-across-sellers signal)
    assert any(r.get("seller") for r in priced)


def test_find_deals_records_winning_tool_live(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    from sentinel.agent.modes.spec import _build_product_deal_tool
    from sentinel.config.schema import SentinelConfig
    from sentinel.memory.store import ToolPreferenceStore

    tool = _build_product_deal_tool(SentinelConfig.default())
    asyncio.run(tool("gaming laptop 16GB RAM RTX 4060 price India"))

    # the cascade recorded which leg won for this query-class (AC4 learning, end-to-end on real DB)
    prefs = ToolPreferenceStore()
    assert prefs.get("product_research:shopping") == "google_shopping_search"
