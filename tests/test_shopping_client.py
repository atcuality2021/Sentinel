"""SENTINEL-022 Step 3 — SearchAPI MCP shopping client.

Normalizers are tested against canned payloads whose field names were verified live against the
real engine (2026-06-14). The transport is exercised only for its fail-soft contract, driven from a
sync test via ``asyncio.run`` with a monkeypatched ``streamablehttp_client`` — no live network, no
``pytest-asyncio`` dependency.
"""

import asyncio

import sentinel.tools.shopping_client as sc
from sentinel.tools.shopping_client import (
    call_shopping_search,
    normalize_offers,
    normalize_shopping,
    _extract_json,
)

# --- canned payloads mirroring the verified live shapes -------------------- #

_SHOPPING_PAYLOAD = {
    "shopping_results": [
        {"position": 1, "title": "Lenovo LOQ i5", "price": "₹63,990",
         "extracted_price": 63990, "seller": "Flipkart",
         "product_link": "https://www.google.com/search?...catalogid:1079",
         "product_token": "eyJxIjoibGFwdG9w"},
        {"position": 2, "title": "Acer Nitro V", "price": "₹75,999",
         "seller": "Reliance Digital", "product_link": "https://x/2", "product_token": "tok2"},
        {"position": 3, "title": "", "price": "₹1", "product_link": "https://x/3"},  # dropped: no title
    ]
}

# NOTE: offers[].merchant is a {name, favicon} dict in the live engine (verified 2026-06-14),
# NOT a plain string — this payload pins that shape so the dict-repr-as-seller bug can't return.
_PRODUCT_PAYLOAD = {
    "offers": [
        {"position": 1, "title": "Lenovo LOQ", "link": "https://flipkart.com/loq",
         "price": "₹63,990", "total_price": "₹63,990",
         "merchant": {"name": "Flipkart", "favicon": "https://x/fav"}},
        {"position": 2, "title": "Lenovo LOQ", "link": "https://amazon.in/loq",
         "total_price": "₹64,500", "merchant": {"name": "Amazon", "favicon": "https://x/fav2"}},
    ]
}


# --- normalize_shopping ---------------------------------------------------- #

def test_normalize_shopping_maps_verified_fields():
    rows = normalize_shopping(_SHOPPING_PAYLOAD)
    assert len(rows) == 2  # the titleless row is dropped
    first = rows[0]
    assert first["title"] == "Lenovo LOQ i5"
    assert first["price"] == "₹63,990"
    assert first["seller"] == "Flipkart"
    assert first["product_token"] == "eyJxIjoibGFwdG9w"
    assert first["source_url"].startswith("https://")


def test_normalize_shopping_empty_and_garbage():
    assert normalize_shopping(None) == []
    assert normalize_shopping({}) == []
    assert normalize_shopping({"shopping_results": ["junk", 5]}) == []


# --- normalize_offers (best-deal-across-sellers) --------------------------- #

def test_normalize_offers_uses_direct_links_and_total_price():
    rows = normalize_offers(_PRODUCT_PAYLOAD)
    assert len(rows) == 2
    assert rows[0]["seller"] == "Flipkart"
    assert rows[0]["source_url"] == "https://flipkart.com/loq"
    # second offer has no `price`, only `total_price` — must still normalize
    assert rows[1]["price"] == "₹64,500"
    assert rows[1]["seller"] == "Amazon"


# --- _extract_json --------------------------------------------------------- #

class _Block:
    def __init__(self, text): self.text = text

class _Result:
    def __init__(self, content=None, structured=None, is_error=False):
        self.content = content or []
        self.structuredContent = structured
        self.isError = is_error

def test_extract_json_prefers_text_then_structured():
    assert _extract_json(_Result(content=[_Block('{"a": 1}')])) == {"a": 1}
    assert _extract_json(_Result(structured={"b": 2})) == {"b": 2}
    assert _extract_json(_Result(content=[_Block("not json")])) is None
    assert _extract_json(None) is None


# --- fail-soft transport (asyncio.run, no live network) -------------------- #

def test_call_returns_empty_when_url_missing(monkeypatch):
    monkeypatch.delenv("SEARCHAPI_MCP_URL", raising=False)
    assert asyncio.run(call_shopping_search("laptop", url=None)) == []


def test_call_returns_empty_when_transport_raises(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(
        "mcp.client.streamable_http.streamablehttp_client", _boom, raising=False)
    # url provided so we get past the missing-url guard into the transport
    assert asyncio.run(call_shopping_search("laptop", url="https://fake")) == []


def test_blank_query_and_token_short_circuit():
    assert asyncio.run(call_shopping_search("   ", url="https://fake")) == []
    assert asyncio.run(sc.call_google_product("", url="https://fake")) == []
