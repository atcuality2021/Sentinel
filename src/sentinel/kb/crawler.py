from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


@dataclass
class CrawledPage:
    url: str
    title: str
    text: str
    source_type: str = "web"


def _parse_page(html: str, url: str, source_type: str) -> CrawledPage | None:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
    if len(text) < 200:
        return None
    return CrawledPage(url=url, title=title, text=text, source_type=source_type)


def _same_domain_links(soup: BeautifulSoup, base_url: str, base_host: str) -> list[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].split("#")[0])
        parsed = urlparse(href)
        if parsed.netloc == base_host and parsed.scheme in ("http", "https"):
            links.append(href)
    return links


async def _crawl_httpx(
    start_url: str,
    max_pages: int,
    max_depth: int,
    source_type: str,
) -> list[CrawledPage]:
    """Lightweight fallback crawler using httpx (no JS rendering)."""
    import httpx
    from .url_guard import validate_crawl_url

    base_host = urlparse(start_url).netloc
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages: list[CrawledPage] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SentinelKB/1.0; +https://sentinel.ai)"}

    async with httpx.AsyncClient(follow_redirects=False, timeout=20, headers=headers) as client:
        while queue and len(pages) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                # Follow redirects manually — re-validate every hop to prevent SSRF
                hops = 0
                resp = await client.get(url)
                while resp.is_redirect and hops < 5:
                    location = resp.headers.get("location", "")
                    if not location:
                        break
                    next_url = urljoin(url, location)
                    validate_crawl_url(next_url)  # raises ValueError on RFC1918/loopback
                    url = next_url
                    resp = await client.get(url)
                    hops += 1
                if not resp.is_success:
                    continue
                if "text/html" not in resp.headers.get("content-type", ""):
                    continue
                html = resp.text
            except Exception:
                continue

            soup = BeautifulSoup(html, "html.parser")
            page = _parse_page(html, url, source_type)
            if page:
                pages.append(page)

            if depth < max_depth:
                for link in _same_domain_links(soup, url, base_host):
                    if link not in visited:
                        queue.append((link, depth + 1))

    return pages


async def _crawl_playwright(
    start_url: str,
    max_pages: int,
    max_depth: int,
    source_type: str,
) -> list[CrawledPage]:
    """Full crawler using Playwright for JS-rendered pages."""
    from playwright.async_api import async_playwright

    base_host = urlparse(start_url).netloc
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]
    pages: list[CrawledPage] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; SentinelKB/1.0; +https://sentinel.ai)"
        )

        while queue and len(pages) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                pw_page = await ctx.new_page()
                await pw_page.goto(url, wait_until="domcontentloaded", timeout=20000)
                html = await pw_page.content()
                await pw_page.close()
            except Exception:
                continue

            soup = BeautifulSoup(html, "html.parser")
            page = _parse_page(html, url, source_type)
            if page:
                pages.append(page)

            if depth < max_depth:
                for link in _same_domain_links(soup, url, base_host):
                    if link not in visited:
                        queue.append((link, depth + 1))

        await browser.close()

    return pages


async def _crawl_firecrawl(
    start_url: str,
    source_type: str,
) -> list[CrawledPage]:
    """Use Firecrawl API to extract content from JS-rendered pages."""
    import os

    import httpx

    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY not set")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": start_url, "formats": ["markdown"]},
        )
    if not resp.is_success:
        raise RuntimeError(f"Firecrawl HTTP {resp.status_code}: {resp.text[:200]}")

    payload = resp.json()
    data = payload.get("data") or {}
    markdown = (data.get("markdown") or "").strip()
    metadata = data.get("metadata") or {}
    title = (metadata.get("title") or metadata.get("ogTitle") or
             urlparse(start_url).path or start_url)

    if len(markdown) < 100:
        raise RuntimeError("Firecrawl returned insufficient content")

    return [CrawledPage(url=start_url, title=title, text=markdown, source_type=source_type)]


async def crawl_website(
    start_url: str,
    max_pages: int = 50,
    max_depth: int = 3,
    source_type: str = "web",
) -> list[CrawledPage]:
    """
    Crawl start_url and extract content.
    Priority: Firecrawl API (handles JS-rendered pages) → Playwright → httpx fallback.
    """
    try:
        return await _crawl_firecrawl(start_url, source_type)
    except Exception:
        pass
    try:
        return await _crawl_playwright(start_url, max_pages, max_depth, source_type)
    except Exception:
        return await _crawl_httpx(start_url, max_pages, max_depth, source_type)
