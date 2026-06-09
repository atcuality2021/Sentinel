"""Pluggable public-search provider layer (SENTINEL-005).

``get_search_tool(provider, *, results)`` returns an ADK tool for the public-research agent:

  - ``gemini``                     → the native ``google_search`` builtin (cloud, Gemini-pinned).
  - ``duckduckgo|brave|serpapi``   → a **function tool** the reasoning model calls via
                                     function-calling (proven to work on the customer's Gemma).

The non-Gemini tools are how a sovereign (no-cloud) run still reaches the web: Gemma issues a
``search(query=...)`` function call, we run an HTTP query against the chosen engine on the
customer's own egress, and return structured notes the synthesizer can cite.

Contract for every function tool (NFR-3):
  - explicit ``timeout`` on the HTTP call,
  - **fail-soft**: a network/HTTP/parse error returns ``{"status": "error", "message": ...}`` —
    it never raises, so a flaky search degrades the run to a gap instead of killing it,
  - typed dict result ``{"status", "results": [{"title", "url", "snippet"}], ...}`` — no ``Any``,
  - provider API keys are read from the environment **inside the call** (secrets, never args,
    never persisted): ``BRAVE_API_KEY`` / ``SERPAPI_API_KEY``. DuckDuckGo is keyless.
"""

from __future__ import annotations

import os
from typing import Callable

from sentinel.tools.sanitize import SOURCE_MATERIAL_NOTICE, wrap_source_material

_TIMEOUT_S = 10.0
# SENTINEL-013: the keyless DuckDuckGo path now hits the **lite SERP** (real web results), not the
# Instant-Answer API (`api.duckduckgo.com?format=json`), which only returned Wikipedia-style abstracts
# and disambiguation topics — the root cause of sovereign runs producing "no cited sources". The lite
# page is a stable, table-based HTML SERP we parse with `re` (no new dependency).
_DDG_ENDPOINT = "https://lite.duckduckgo.com/lite/"
# A browser-ish UA — the lite endpoint returns an empty body to an obviously-scripted client.
_DDG_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Result row keys callers can rely on.
SearchResult = dict[str, str]
SearchResponse = dict[str, object]


def _ok(results: list[SearchResult], provider: str) -> SearchResponse:
    # ``notice`` carries the prompt-injection stance (Step 17): the snippets are fenced source
    # material — data to cite, never instructions to obey. Additive field; results stay clean.
    return {"status": "success", "provider": provider, "results": results,
            "notice": SOURCE_MATERIAL_NOTICE}


def _err(message: str, provider: str) -> SearchResponse:
    """A fail-soft error result. The model sees the gap; the run continues (NFR-3)."""
    return {"status": "error", "provider": provider, "message": message, "results": []}


def _row(title: str, url: str, snippet: str) -> SearchResult:
    # The snippet is retrieved web text — fence it as source material so the model treats it as data
    # (Step 17). title/url stay clean: they are citation metadata, not free-text the page controls.
    return {"title": (title or "").strip(), "url": (url or "").strip(),
            "snippet": wrap_source_material(snippet)}


def _ddg_unwrap(href: str) -> str:
    """Resolve a DDG lite result href to the real target URL.

    Lite results are wrapped in a redirector — ``//duckduckgo.com/l/?uddg=<urlencoded target>&rut=…`` —
    so the real URL lives in the ``uddg`` query param. A bare (already-direct) href is returned as-is.
    """
    from urllib.parse import parse_qs, unquote, urlparse

    if "uddg=" not in href:
        return href.strip()
    try:
        qs = parse_qs(urlparse(href).query)
        target = qs.get("uddg", [""])[0]
        return unquote(target).strip() or href.strip()
    except Exception:  # a malformed redirector is non-fatal — fall back to the raw href
        return href.strip()


def _parse_ddg_lite(html_text: str, results: int) -> list[SearchResult]:
    """Parse the DuckDuckGo **lite** SERP HTML into result rows (title + URL + snippet).

    The lite page is a flat table: each result is a ``class="result-link"`` anchor (href + title),
    optionally followed by a ``class="result-snippet"`` cell. We extract links and snippets in document
    order and pair them by index — defensive throughout: tags are stripped, entities unescaped, the
    redirector unwrapped, and any row we can't read is skipped rather than raising. An empty/garbled
    page yields ``[]`` (an honest gap), never an exception.
    """
    import re
    from html import unescape

    def _clean(text: str) -> str:
        return unescape(re.sub(r"<[^>]+>", "", text or "")).strip()

    # Quote-agnostic (lite uses single quotes); non-greedy title capture across the anchor body.
    link_re = re.compile(
        r"""<a[^>]*class=['"]result-link['"][^>]*href=['"]([^'"]+)['"][^>]*>(.*?)</a>"""
        r"""|<a[^>]*href=['"]([^'"]+)['"][^>]*class=['"]result-link['"][^>]*>(.*?)</a>""",
        re.IGNORECASE | re.DOTALL,
    )
    snippet_re = re.compile(
        r"""class=['"]result-snippet['"][^>]*>(.*?)</""", re.IGNORECASE | re.DOTALL
    )

    links = [
        (_ddg_unwrap(href1 or href2), _clean(title1 or title2))
        for href1, title1, href2, title2 in link_re.findall(html_text or "")
    ]
    snippets = [_clean(s) for s in snippet_re.findall(html_text or "")]

    rows: list[SearchResult] = []
    for i, (url, title) in enumerate(links):
        if len(rows) >= results:
            break
        if not url:
            continue
        snippet = snippets[i] if i < len(snippets) else ""
        rows.append(_row(title or url, url, snippet))
    return rows


def _duckduckgo(query: str, results: int) -> SearchResponse:
    """DuckDuckGo **lite SERP** (keyless real web search). Fail-soft (NFR-3).

    POSTs the query to the lite endpoint and parses the HTML table into titled, sourced rows the
    synthesizer can cite. Any network/parse failure → a typed empty error result (never a raise); an
    empty parse → a clean empty success (an honest "found nothing"), so a flaky/blocked search degrades
    the run to a gap instead of killing it.
    """
    import httpx

    try:
        resp = httpx.post(
            _DDG_ENDPOINT,
            data={"q": query},
            headers={"User-Agent": _DDG_UA},
            timeout=_TIMEOUT_S,
            follow_redirects=True,
        )
        resp.raise_for_status()
        rows = _parse_ddg_lite(resp.text, results)
    except Exception as exc:  # any network/parse failure → soft gap, never a raise
        return _err(f"duckduckgo request failed: {type(exc).__name__}", "duckduckgo")

    return _ok(rows[:results], "duckduckgo")


def _brave(query: str, results: int) -> SearchResponse:
    """Brave Web Search API. Reads BRAVE_API_KEY from env (secret). Fail-soft."""
    import httpx

    key = os.getenv("BRAVE_API_KEY", "").strip()
    if not key:
        return _err("BRAVE_API_KEY is not set", "brave")
    try:
        resp = httpx.get(
            _BRAVE_ENDPOINT,
            params={"q": query, "count": results},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return _err(f"brave request failed: {type(exc).__name__}", "brave")

    web = data.get("web", {}) if isinstance(data, dict) else {}
    rows = [
        _row(item.get("title", ""), item.get("url", ""), item.get("description", ""))
        for item in web.get("results", [])[:results]
    ]
    return _ok(rows, "brave")


def _serpapi(query: str, results: int) -> SearchResponse:
    """SerpAPI (Google engine). Reads SERPAPI_API_KEY from env (secret). Fail-soft."""
    import httpx

    key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not key:
        return _err("SERPAPI_API_KEY is not set", "serpapi")
    try:
        resp = httpx.get(
            _SERPAPI_ENDPOINT,
            params={"engine": "google", "q": query, "api_key": key, "num": results},
            timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return _err(f"serpapi request failed: {type(exc).__name__}", "serpapi")

    rows = [
        _row(item.get("title", ""), item.get("link", ""), item.get("snippet", ""))
        for item in (data.get("organic_results", []) if isinstance(data, dict) else [])[:results]
    ]
    return _ok(rows, "serpapi")


def _searxng(query: str, results: int) -> SearchResponse:
    """Self-hosted **SearXNG** metasearch (SENTINEL-013). The sovereign search path: keyless, and the
    instance runs on the customer's own box so a query egresses to **no third party** — unlike scraping
    DuckDuckGo (which both egresses and bot-blocks) or a keyed SaaS API. Fail-soft (NFR-3).

    Reads the instance base URL from ``SEARXNG_URL`` (env, never an arg — config, kept out of code/YAML).
    The instance must have the JSON format enabled (``search.formats: [html, json]`` in its settings).
    """
    import httpx

    base = os.getenv("SEARXNG_URL", "").strip().rstrip("/")
    if not base:
        return _err("SEARXNG_URL is not set", "searxng")
    try:
        resp = httpx.get(
            f"{base}/search", params={"q": query, "format": "json"}, timeout=_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network/parse failure → soft gap, never a raise
        return _err(f"searxng request failed: {type(exc).__name__}", "searxng")

    rows = [
        _row(item.get("title", ""), item.get("url", ""), item.get("content", ""))
        for item in (data.get("results", []) if isinstance(data, dict) else [])[:results]
    ]
    return _ok(rows, "searxng")


_FETCHERS: dict[str, Callable[[str, int], SearchResponse]] = {
    "duckduckgo": _duckduckgo,
    "brave": _brave,
    "serpapi": _serpapi,
    "searxng": _searxng,
}


def _budget_reached(provider: str, max_calls: int) -> SearchResponse:
    """Soft stop when the per-run search budget is spent — the model proceeds to synthesis.

    Shaped like a normal (empty) result so the agent reads it as "no more to fetch" and stops the
    tool loop, rather than an error it might retry. Keeps the over-searching loop bounded gracefully.
    """
    return {
        "status": "budget_reached", "provider": provider, "results": [],
        "message": (f"Search budget of {max_calls} calls reached. Do not search again — "
                    "synthesize the artifact from the findings already gathered."),
    }


def _make_function_tool(
    provider: str, results: int, max_calls: int = 0, *, stagger_s: float = 0.0,
    now: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None,
) -> Callable[[str], SearchResponse]:
    """Bind the result count into a clean ``search(query: str) -> dict`` the model can call.

    ADK derives the tool schema from this signature + docstring, so the wrapper keeps exactly one
    typed parameter and a description. The provider + result count are captured in the closure, as is
    a per-run call counter: once ``max_calls`` searches have run (``0`` ⇒ unbounded), further calls
    return :func:`_budget_reached` so the model stops the loop instead of over-searching.

    ``stagger_s`` (SENTINEL-013): minimum spacing between consecutive fetches — before each fetch we
    sleep just enough that ``stagger_s`` has elapsed since the previous one (keeps the keyless DDG SERP
    from being throttled). ``now``/``sleep`` are injectable so the spacing is testable with **zero real
    sleeping**; they default to ``time.monotonic``/``time.sleep`` so production is unchanged. ``0`` ⇒
    no stagger (byte-identical to before).
    """
    import time

    fetch = _FETCHERS[provider]
    _now = now or time.monotonic
    _sleep = sleep or time.sleep
    state: dict[str, float | int | None] = {"calls": 0, "last": None}

    def search(query: str) -> SearchResponse:
        """Search the public web for the query and return titled, sourced result snippets.

        Use this to find public information (news, filings, product pages, profiles). Returns a
        dict with ``status`` and a ``results`` list of ``{title, url, snippet}``; cite the URL.
        """
        if not query or not query.strip():
            return _err("empty query", provider)
        if max_calls and state["calls"] >= max_calls:
            return _budget_reached(provider, max_calls)
        if stagger_s and state["last"] is not None:
            gap = stagger_s - (_now() - state["last"])
            if gap > 0:
                _sleep(gap)
        state["calls"] += 1
        state["last"] = _now()
        return fetch(query.strip(), results)

    search.__name__ = "search"
    return search


def get_search_tool(
    provider: str, *, results: int = 5, max_calls: int = 0, stagger_s: float = 0.0,
    now: Callable[[], float] | None = None, sleep: Callable[[float], None] | None = None,
):
    """Return the ADK public-search tool for ``provider`` (AC-4).

    ``gemini`` → the builtin ``google_search`` (cloud, manages its own grounding). Any other
    supported provider → a function tool bound to ``results``, a per-run ``max_calls`` budget
    (``0`` ⇒ unbounded), and a ``stagger_s`` inter-call spacing (``0`` ⇒ none; ``now``/``sleep``
    injectable for tests). Unknown provider ⇒ ``ValueError`` (caller validated it).
    """
    if provider == "gemini":
        from google.adk.tools import google_search

        return google_search
    if provider in _FETCHERS:
        return _make_function_tool(
            provider, results, max_calls, stagger_s=stagger_s, now=now, sleep=sleep
        )
    raise ValueError(
        f"Unknown search provider {provider!r} (expected gemini|duckduckgo|brave|serpapi|searxng)"
    )
