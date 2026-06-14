"""SENTINEL-022 Step 6 — product_research public-research prompt names the priced tools first (AC2).

The prompt must direct the agent to the structured shopping tools (find_deals →
google_shopping_search → google_product) BEFORE any generic ``site:`` web search, and must keep its
render placeholders intact.
"""

from sentinel.config.schema import SentinelConfig


def _public_prompt() -> str:
    cfg = SentinelConfig.default()
    return cfg.prompts["product_research.public_research"].template


def test_prompt_names_shopping_tools():
    p = _public_prompt()
    assert "google_shopping_search" in p
    assert "google_product" in p
    assert "find_deals" in p


def test_shopping_tools_come_before_generic_site_search():
    p = _public_prompt()
    first_shopping = p.index("google_shopping_search")
    first_site = p.index("site:flipkart.com")
    assert first_shopping < first_site, "priced tools must be directed before generic site: search"


def test_site_search_is_demoted_to_fallback():
    p = _public_prompt()
    # the generic site: searches must read as a fallback, not the lead step
    assert "FALLBACK" in p
    assert p.index("PRICES FIRST") < p.index("FALLBACK")


def test_render_placeholders_preserved():
    p = _public_prompt()
    assert "{target}" in p and "{research_plan}" in p


def test_searchapi_description_mentions_shopping():
    cfg = SentinelConfig.default()
    server = cfg.mcp_servers["searchapi"]   # cfg.mcp_servers is a {name: MCPServerConfig} dict
    assert "google_shopping_search" in server.description
