"""
Sentinel Demo Recording Script — Complete Flow Capture
Records two research runs end-to-end with video:
  1. BiltIQ AI → Assam Government proposal (KB-enriched: biltiq.ai + assam.gov.in)
  2. India Laptop Market 2026 (product_research)

Usage:
  PYTHONPATH=src python3 record_demo.py

Outputs:
  /tmp/sentinel-demo-videos3/demo_01_assam_govt.webm
  /tmp/sentinel-demo-videos3/demo_02_laptop.webm
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

BASE = "http://localhost:8080"
OUT_DIR = Path("/tmp/sentinel-demo-videos3")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PLAN_TIMEOUT = 90_000       # ms — plan generation (vLLM 12B)
RUN_TIMEOUT_S = 420         # seconds — full research run
RUN_NAV_TIMEOUT = 450_000   # ms — Playwright navigation timeout for POST /run (sync, full duration)


def _delete_project_by_name(name: str) -> None:
    """Delete project from DB by name so fresh recording can create a clean one."""
    import urllib.request, urllib.parse
    try:
        # GET projects to find the ID
        resp = urllib.request.urlopen(f"{BASE}/projects", timeout=5)
        html = resp.read().decode()
        # The tasks page redirects to existing project — find it via API
        # Use the DB-level delete instead
        import sqlite3, os
        db = os.path.expanduser("~/Desktop/Sentinel/data/sentinel.db")
        if not os.path.exists(db):
            return
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT id FROM projects WHERE name=?", (name,)).fetchone()
        conn.close()
        if row:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{BASE}/projects/{row[0]}/delete",
                    data=b"",
                    method="POST",
                ),
                timeout=5,
            )
    except Exception:
        pass


# ── Helpers ──────────────────────────────────────────────────────────────────

async def slow_scroll(page, *, pause: float = 0.5, step: int = 250,
                       open_details: bool = False) -> None:
    """Scroll page from top to bottom at step increments, re-measuring height each step.

    open_details=True expands all <details> elements before scrolling so the
    agent timeline and KB context are visible in the recording.
    """
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(0.3)
    if open_details:
        await page.evaluate(
            "document.querySelectorAll('details').forEach(d => d.open = true)"
        )
        await asyncio.sleep(0.4)
    pos = 0
    while True:
        total = await page.evaluate("document.body.scrollHeight")
        if pos >= total:
            break
        pos = min(pos + step, total)
        await page.evaluate(f"window.scrollTo(0,{pos})")
        await asyncio.sleep(pause)
    await asyncio.sleep(0.8)
    await page.evaluate("window.scrollTo(0,0)")
    await asyncio.sleep(0.3)


async def wait_for_result(page, *, timeout_s: int = RUN_TIMEOUT_S) -> bool:
    """Poll page content until the result layout is visible."""
    print(f"    ⏳  Waiting for research to complete (up to {timeout_s}s)…")
    deadline = time.time() + timeout_s
    last_log = time.time()
    while time.time() < deadline:
        try:
            html = await page.content()
            if "View full plan" in html:
                print("    ✓  Result ready")
                return True
            if "Re-run" in html and "Approve" not in html:
                print("    ✓  Run complete (Re-run button visible)")
                return True
        except Exception:
            pass
        if time.time() - last_log > 20:
            elapsed = int(time.time() - (deadline - timeout_s))
            print(f"    ⏳  Still running ({elapsed}s)…")
            last_log = time.time()
        await asyncio.sleep(5)
    print("    ⚠  Timed out waiting for result")
    return False


def _extract_project_id(url: str) -> str:
    for part in url.split("/"):
        if len(part) == 32 and all(c in "0123456789abcdef" for c in part):
            return part
    return url.split("/projects/")[-1].split("/")[0].split("?")[0] if "/projects/" in url else ""


# ── Demo 1: BiltIQ AI → Assam Government Proposal ────────────────────────────

async def record_assam_govt(browser) -> Path:
    print(f"\n{'═'*62}")
    print("  Demo 1: BiltIQ AI → Assam Government Proposal")
    print(f"{'═'*62}")

    _delete_project_by_name("BiltIQ AI")

    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        record_video_dir=str(OUT_DIR),
        record_video_size={"width": 1280, "height": 900},
    )
    page = await ctx.new_page()

    # ── Step 1: Projects page (empty state) ────────────────────────────────
    print("  [1/9] Projects home — empty state")
    await page.goto(f"{BASE}/projects", wait_until="domcontentloaded")
    await asyncio.sleep(1.5)
    await slow_scroll(page, pause=0.5)

    # ── Step 2: Fill create project form ───────────────────────────────────
    print("  [2/9] Creating project: BiltIQ AI")
    await page.fill("input[name='name']", "BiltIQ AI")
    await asyncio.sleep(0.4)
    await page.fill("input[name='website']", "https://biltiq.ai")
    await asyncio.sleep(0.6)
    await slow_scroll(page, pause=0.4, step=250)
    await asyncio.sleep(0.4)

    # Submit — POST /projects → redirect to /projects/{id}/tasks
    async with page.expect_navigation(timeout=15000):
        await page.click("button:has-text('Create project')")

    project_id = _extract_project_id(page.url)
    print(f"  ✓  Project created: {project_id}")
    await asyncio.sleep(1.5)
    await slow_scroll(page)

    # ── Step 3: KB tab — biltiq.ai auto-crawl badge ────────────────────────
    print("  [3/9] KB tab — biltiq.ai auto-crawl in progress")
    await page.goto(f"{BASE}/projects/{project_id}/kb", wait_until="domcontentloaded")
    await asyncio.sleep(1.2)
    await slow_scroll(page, pause=0.5)
    await asyncio.sleep(1)

    # ── Step 4: Navigate to Research tab ──────────────────────────────────
    print("  [4/9] Research tab — filling task form")
    await page.goto(f"{BASE}/projects/{project_id}/tasks", wait_until="domcontentloaded")
    await asyncio.sleep(1)
    await slow_scroll(page, pause=0.5)
    await asyncio.sleep(0.4)

    # Fill objective
    await page.fill("input#t-obj",
                    "Propose BiltIQ AI sovereign intelligence platform to "
                    "Assam State Government for digital governance and citizen services")
    await asyncio.sleep(0.4)

    # Fill context
    await page.fill("textarea[name='context']",
                    "BiltIQ AI is a sovereign on-premise AI platform for regulated sectors. "
                    "Products: BiltIQ Sentinel (intelligence research), BiltIQ CommandCenter (CRM). "
                    "Assam Government has active digital transformation programs across "
                    "agriculture, healthcare, and citizen services.")
    await asyncio.sleep(0.4)

    # Fill client URL (KB enrichment — gets crawled before agents run)
    await page.fill("input#t-curl", "https://assam.gov.in")
    await asyncio.sleep(0.4)

    # Select domain
    await page.select_option("select#t-dom", "govt_proposal")
    await asyncio.sleep(0.6)

    await slow_scroll(page, pause=0.5, step=250)
    await asyncio.sleep(0.8)

    # ── Step 5: Plan task → plan generation ────────────────────────────────
    print("  [5/9] Clicking Plan task → plan generation starts")
    # GET form → /projects/{id}/plan?... → 303 → /projects/{id}/tasks/{tid}
    async with page.expect_navigation(timeout=PLAN_TIMEOUT):
        await page.click("button:has-text('Plan task')")

    print(f"    Landed at: {page.url}")
    await asyncio.sleep(2)

    # ── Step 6: Plan review page ────────────────────────────────────────────
    print("  [6/9] Plan review — KB context panel + agent DAG")
    await slow_scroll(page, pause=0.6, step=280)
    await asyncio.sleep(0.8)

    # If KB sources still indexing — wait and refresh up to 4 times
    for attempt in range(4):
        html = await page.content()
        if "indexing" in html.lower() or ("pending" in html.lower() and "KB" in html):
            print(f"    ⏳  KB still indexing (attempt {attempt+1})…")
            await asyncio.sleep(10)
            await page.reload(wait_until="domcontentloaded")
            await slow_scroll(page, pause=0.4, step=280)
        else:
            break

    # Approve & run if in propose mode
    html = await page.content()
    if "Approve" in html and "run" in html.lower():
        print("  → Clicking Approve & run (waiting up to 7min for sync run)…")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)
        # POST /run is fully synchronous — navigation won't complete until the
        # entire research pipeline finishes and the server returns the 303 redirect.
        async with page.expect_navigation(timeout=RUN_NAV_TIMEOUT):
            await page.click("button:has-text('Approve')", no_wait_after=True)
        print("    ✓  Run navigation complete")
        await asyncio.sleep(1.5)

    # ── Step 7: Result page — full scroll (expand all collapsibles) ────────
    print("  [7/9] Scrolling through Assam govt proposal result")
    await page.reload(wait_until="domcontentloaded")
    await asyncio.sleep(1.2)
    # open_details=True expands timeline + KB context so they're visible on camera
    await slow_scroll(page, pause=0.65, step=220, open_details=True)

    # ── Step 8: Memory tab ─────────────────────────────────────────────────
    print("  [8/9] Memory tab — semantic facts written")
    await page.goto(f"{BASE}/projects/{project_id}/memory", wait_until="domcontentloaded")
    await asyncio.sleep(1.2)
    await slow_scroll(page, pause=0.55, step=300)

    # ── Step 9: KB + Artifacts tabs ────────────────────────────────────────
    print("  [9/9] KB tab — biltiq.ai + assam.gov.in indexed")
    await page.goto(f"{BASE}/projects/{project_id}/kb", wait_until="domcontentloaded")
    await asyncio.sleep(1)
    await slow_scroll(page, pause=0.5, step=300)

    await page.goto(f"{BASE}/projects/{project_id}/artifacts", wait_until="domcontentloaded")
    await asyncio.sleep(1)
    await slow_scroll(page, pause=0.5, step=300)
    await asyncio.sleep(1.5)

    video_path = await page.video.path() if page.video else None
    await ctx.close()

    out = OUT_DIR / "demo_01_assam_govt.webm"
    if video_path and Path(video_path).exists():
        Path(video_path).rename(out)
    else:
        webms = sorted(OUT_DIR.glob("*.webm"), key=lambda f: f.stat().st_mtime)
        if webms:
            webms[-1].rename(out)
    size = out.stat().st_size // 1024 if out.exists() else 0
    print(f"  ✓  Saved: {out} ({size} KB)")
    return out


# ── Demo 2: India Laptop Market 2026 ─────────────────────────────────────────

async def record_laptop(browser) -> Path:
    print(f"\n{'═'*62}")
    print("  Demo 2: Best Laptop Under ₹80k — India Market 2026")
    print(f"{'═'*62}")

    _delete_project_by_name("India Laptop Market 2026")

    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        record_video_dir=str(OUT_DIR),
        record_video_size={"width": 1280, "height": 900},
    )
    page = await ctx.new_page()

    # ── Step 1: Projects page (BiltIQ project visible) ────────────────────
    print("  [1/8] Projects home — BiltIQ AI project visible")
    await page.goto(f"{BASE}/projects", wait_until="domcontentloaded")
    await asyncio.sleep(1.5)
    await slow_scroll(page, pause=0.5)

    # ── Step 2: Create project ─────────────────────────────────────────────
    print("  [2/8] Creating project: India Laptop Market 2026")
    await page.fill("input[name='name']", "India Laptop Market 2026")
    await asyncio.sleep(0.5)
    await slow_scroll(page, pause=0.4, step=250)
    await asyncio.sleep(0.4)

    async with page.expect_navigation(timeout=15000):
        await page.click("button:has-text('Create project')")

    project_id = _extract_project_id(page.url)
    print(f"  ✓  Project created: {project_id}")
    await asyncio.sleep(1.5)
    await slow_scroll(page)

    # ── Step 3: Research tab ───────────────────────────────────────────────
    print("  [3/8] Research tab — filling task form")
    await page.goto(f"{BASE}/projects/{project_id}/tasks", wait_until="domcontentloaded")
    await asyncio.sleep(1)

    await page.fill("input#t-obj",
                    "Find the best laptop under 80000 rupees in India 2026 "
                    "for software development and light gaming with best value for money")
    await asyncio.sleep(0.4)

    await page.fill("textarea[name='context']",
                    "Use case: full-stack software development + occasional gaming. "
                    "Must-haves: 16GB RAM, 512GB+ SSD, dedicated GPU, IPS display. "
                    "Budget: strict 80000 rupees cap. Compare Amazon.in and Flipkart.")
    await asyncio.sleep(0.4)

    await page.select_option("select#t-dom", "product_research")
    await asyncio.sleep(0.5)

    await slow_scroll(page, pause=0.5, step=250)
    await asyncio.sleep(0.8)

    # ── Step 4: Plan task ──────────────────────────────────────────────────
    print("  [4/8] Clicking Plan task → plan generation")
    async with page.expect_navigation(timeout=PLAN_TIMEOUT):
        await page.click("button:has-text('Plan task')")

    print(f"    Landed at: {page.url}")
    await asyncio.sleep(2)

    # ── Step 5: Plan review ────────────────────────────────────────────────
    print("  [5/8] Plan review page — agent DAG")
    await slow_scroll(page, pause=0.6, step=280)
    await asyncio.sleep(0.8)

    html = await page.content()
    if "Approve" in html and "run" in html.lower():
        print("  → Clicking Approve & run (waiting up to 7min for sync run)…")
        await asyncio.sleep(0.5)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.5)
        async with page.expect_navigation(timeout=RUN_NAV_TIMEOUT):
            await page.click("button:has-text('Approve')", no_wait_after=True)
        print("    ✓  Run navigation complete")
        await asyncio.sleep(1.5)

    # ── Step 6: Result — full scroll (expand all collapsibles) ──────────────
    print("  [6/8] Scrolling through laptop research result")
    await page.reload(wait_until="domcontentloaded")
    await asyncio.sleep(1.2)
    await slow_scroll(page, pause=0.65, step=220, open_details=True)

    # ── Step 7: Memory tab ─────────────────────────────────────────────────
    print("  [7/8] Memory tab — winner semantic fact")
    await page.goto(f"{BASE}/projects/{project_id}/memory", wait_until="domcontentloaded")
    await asyncio.sleep(1.2)
    await slow_scroll(page, pause=0.55, step=300)

    # ── Step 8: Artifacts ─────────────────────────────────────────────────
    print("  [8/8] Artifacts tab")
    await page.goto(f"{BASE}/projects/{project_id}/artifacts", wait_until="domcontentloaded")
    await asyncio.sleep(1)
    await slow_scroll(page, pause=0.5, step=300)
    await asyncio.sleep(1.5)

    video_path = await page.video.path() if page.video else None
    await ctx.close()

    out = OUT_DIR / "demo_02_laptop.webm"
    if video_path and Path(video_path).exists():
        Path(video_path).rename(out)
    else:
        webms = sorted(
            [f for f in OUT_DIR.glob("*.webm") if f.name != "demo_01_assam_govt.webm"],
            key=lambda f: f.stat().st_mtime,
        )
        if webms:
            webms[-1].rename(out)
    size = out.stat().st_size // 1024 if out.exists() else 0
    print(f"  ✓  Saved: {out} ({size} KB)")
    return out


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    from playwright.async_api import async_playwright
    import urllib.request

    print("\n🎬  Sentinel Demo Recording")
    print(f"    Output: {OUT_DIR}")
    print(f"    Server: {BASE}\n")

    for attempt in range(20):
        try:
            urllib.request.urlopen(f"{BASE}/projects", timeout=3)
            print("✓  Server is up\n")
            break
        except Exception:
            if attempt == 19:
                print("✗  Server not responding — aborting")
                sys.exit(1)
            if attempt % 4 == 0:
                print(f"  Waiting for server… ({attempt*2}s)")
            time.sleep(2)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/google-chrome",
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
            ],
        )

        await record_assam_govt(browser)
        print("\n  Pausing 3s…")
        await asyncio.sleep(3)
        await record_laptop(browser)

        await browser.close()

    print("\n" + "═"*62)
    print("🎬  Recording complete")
    print(f"    Files in {OUT_DIR}:")
    for f in sorted(OUT_DIR.glob("demo_*.webm")):
        mb = f.stat().st_size / 1024 / 1024
        print(f"      {f.name}  ({mb:.1f} MB)")
    print("═"*62 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
