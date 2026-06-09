"""
NutriVault Benchmark — Realistic E2E test of all 9 Sentinel research modes.

Scenario
--------
NutriVault is an evidence-based nutrition supplement startup based in Bangalore, India.
Founded 2024, seed-funded ₹4 Cr. Focus: protein + adaptogens for fitness enthusiasts and
urban professionals aged 25-40. Direct-to-consumer (DTC) via own website + quick-commerce.
Website: https://nutrivault.in (hypothetical; we use https://biltiq.ai as a live test proxy
         to exercise the actual crawler/KB pipeline with real content)

Benchmark tasks
---------------
1. competitor    → Battlecard  vs  HK Vitals (HealthKart brand)
2. competitor    → Battlecard  vs  Oziva
3. competitor    → Battlecard  vs  Wellbeing Nutrition
4. self_profile  → SelfProfile  of NutriVault
5. compare       → ComparisonMatrix  NutriVault vs HK Vitals
6. software      → SoftwareBrief  on Shopify (DTC platform evaluation)
7. finance       → FinancialProfile  on HealthKart (parent company, competitor context)
8. academic      → AcademicBrief  on "protein supplementation efficacy RCT meta-analysis"
9. nutrition     → NutritionBrief  on "ashwagandha adaptogen"

Each task is created via the project → plan → run API flow and results are captured.
The script prints a structured benchmark report at the end.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import httpx  # type: ignore[import-untyped]

BASE = "http://localhost:8080"
PROJECT_NAME = "NutriVault"
PROJECT_WEBSITE = "https://nutrivault.in"

# All 9 benchmark tasks: (label, objective, mode/domain)
BENCHMARK_TASKS = [
    ("competitor_hkvitals",
     "HK Vitals by HealthKart — protein and sports nutrition competitor analysis for NutriVault",
     "competitor"),
    ("competitor_oziva",
     "Oziva plant-based nutrition — competitor analysis for NutriVault",
     "competitor"),
    ("competitor_wellbeing",
     "Wellbeing Nutrition India — competitor analysis for NutriVault",
     "competitor"),
    ("self_profile_nutrivault",
     "NutriVault — evidence-based nutrition supplements India DTC startup",
     "self_profile"),
    ("compare_vs_hkvitals",
     "NutriVault vs HK Vitals protein supplements — feature, pricing, and positioning comparison",
     "compare"),
    ("software_shopify",
     "Shopify — DTC e-commerce platform evaluation for supplement brand",
     "software"),
    ("finance_healthkart",
     "HealthKart India — financial profile and investor analysis",
     "finance"),
    ("academic_protein",
     "protein supplementation efficacy meta-analysis RCT systematic review",
     "academic"),
    ("nutrition_ashwagandha",
     "ashwagandha adaptogen stress reduction evidence dosage",
     "nutrition"),
]


async def create_project(client: httpx.AsyncClient) -> str:
    """Create NutriVault project, return project_id."""
    r = await client.post(
        f"{BASE}/projects",
        data={"name": PROJECT_NAME, "website": PROJECT_WEBSITE},
        follow_redirects=False,
    )
    # 303 redirect to /projects/{id}
    loc = r.headers.get("location", "")
    pid = loc.rstrip("/").split("/")[-1]
    assert pid and pid != "projects", f"Bad redirect: {loc!r}"
    print(f"  Project created: {pid}")
    return pid


async def plan_task(client: httpx.AsyncClient, pid: str, objective: str, domain: str) -> tuple[str, str]:
    """
    GET /projects/{pid}/plan?objective=...&domain=...
    Returns (task_id, backend).
    The plan page redirects to /projects/{pid}/tasks/{tid}.
    """
    r = await client.get(
        f"{BASE}/projects/{pid}/plan",
        params={"objective": objective, "domain": domain},
        follow_redirects=True,
    )
    # After redirect, we're at /projects/{pid}/tasks/{tid}
    url = str(r.url)
    parts = url.rstrip("/").split("/")
    # URL shape: /projects/{pid}/tasks/{tid}[?...]
    tid = parts[-1].split("?")[0]
    assert len(tid) >= 8, f"Bad task_id from URL {url!r}"
    return tid


async def run_task(client: httpx.AsyncClient, pid: str, tid: str, backend: str = "") -> str:
    """
    POST /projects/{pid}/tasks/{tid}/run
    Returns final URL (task result page).
    """
    r = await client.post(
        f"{BASE}/projects/{pid}/tasks/{tid}/run",
        data={"backend": backend},
        follow_redirects=True,
    )
    return str(r.url)


async def get_task_html(client: httpx.AsyncClient, pid: str, tid: str) -> str:
    """GET the task result page HTML."""
    r = await client.get(f"{BASE}/projects/{pid}/tasks/{tid}", follow_redirects=True)
    return r.text


def extract_result_summary(html: str, label: str) -> dict:
    """Pull key signals from the result HTML without a DOM parser."""
    import re

    summary: dict = {"label": label, "ok": False, "has_result": False, "has_action_plan": False,
                     "has_grade": False, "public_findings": 0, "private_findings": 0,
                     "artifact_type": "", "error": ""}

    if "result-section" in html or "artifact-card" in html or "finding-card" in html:
        summary["has_result"] = True
        summary["ok"] = True

    if "action_plan" in html.lower() or "next step" in html.lower() or "recommended" in html.lower():
        summary["has_action_plan"] = True

    if "grade" in html.lower() or "eval_score" in html.lower():
        summary["has_grade"] = True

    # Count PUBLIC / PRIVATE boundary chips
    pub = len(re.findall(r'PUBLIC|public-chip|tag-public', html))
    prv = len(re.findall(r'PRIVATE|private-chip|tag-private', html))
    summary["public_findings"] = pub
    summary["private_findings"] = prv

    # Detect artifact type from page content
    for art in ("Battlecard", "AccountBrief", "SelfProfile", "ComparisonMatrix",
                "SoftwareBrief", "FinancialProfile", "AcademicBrief",
                "NutritionBrief", "TravelBrief"):
        if art.lower() in html.lower():
            summary["artifact_type"] = art
            break

    if "error" in html.lower() and not summary["has_result"]:
        m = re.search(r'<p[^>]*class=["\']error["\'][^>]*>([^<]{10,200})<', html)
        if m:
            summary["error"] = m.group(1).strip()

    # Check if it's still in "planned" state (run not triggered)
    if "approve" in html.lower() and not summary["has_result"]:
        summary["error"] = "Task still awaiting approval (run did not start)"

    return summary


def print_report(results: list[dict], elapsed: float) -> None:
    """Print a structured benchmark report."""
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    print("\n" + "=" * 70)
    print("  NUTRIVAULT BENCHMARK REPORT — Sentinel System Test")
    print("=" * 70)
    print(f"  Total tasks:     {len(results)}")
    print(f"  Passed:          {len(ok)}")
    print(f"  Failed:          {len(failed)}")
    print(f"  Wall clock:      {elapsed:.1f}s")
    print("-" * 70)

    for r in results:
        icon = "✓" if r["ok"] else "✗"
        artifact = r["artifact_type"] or "—"
        plan_str = "action_plan=✓" if r["has_action_plan"] else "action_plan=—"
        print(f"  {icon}  {r['label']:<30}  {artifact:<20}  {plan_str}")
        if r["error"]:
            print(f"       ERROR: {r['error'][:80]}")

    print("=" * 70)

    if len(ok) >= 7:
        print("  RESULT: PASS — ≥7/9 use cases produced structured artifacts")
    elif len(ok) >= 5:
        print("  RESULT: PARTIAL — 5-6/9 use cases passed (model errors tolerable)")
    else:
        print("  RESULT: FAIL — fewer than 5 use cases produced results")
    print("=" * 70 + "\n")


async def main() -> None:
    t0 = time.time()
    print("\n" + "=" * 70)
    print("  NutriVault × Sentinel — Full System Benchmark")
    print("  Startup: evidence-based nutrition DTC, India")
    print("  Testing all 9 research modes against real competitors")
    print("=" * 70)

    timeout = httpx.Timeout(300.0, connect=10.0)
    limits = httpx.Limits(max_connections=3)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        # 1. Create the project
        print("\n[1/3] Creating NutriVault project …")
        pid = await create_project(client)

        # 2. Plan all tasks (can run concurrently — planner is fast)
        print("\n[2/3] Planning all 9 research tasks …")
        task_ids: list[tuple[str, str, str]] = []  # (label, objective, tid)
        for label, objective, domain in BENCHMARK_TASKS:
            print(f"  → planning: {label}")
            try:
                tid = await plan_task(client, pid, objective, domain)
                task_ids.append((label, objective, tid))
                print(f"    task_id={tid}")
            except Exception as exc:
                print(f"    PLAN FAILED: {exc}")
                task_ids.append((label, objective, f"FAILED:{exc}"))

        # 3. Run tasks — sequential to avoid overloading the LLM backend
        print("\n[3/3] Running all research tasks (this may take several minutes) …")
        results: list[dict] = []
        for label, objective, tid in task_ids:
            if tid.startswith("FAILED:"):
                results.append({"label": label, "ok": False, "has_result": False,
                                 "has_action_plan": False, "has_grade": False,
                                 "public_findings": 0, "private_findings": 0,
                                 "artifact_type": "", "error": tid})
                continue

            print(f"\n  Running: {label}")
            print(f"    objective: {objective[:65]}…")
            t_step = time.time()
            try:
                await run_task(client, pid, tid)
                elapsed_step = time.time() - t_step
                html = await get_task_html(client, pid, tid)
                summary = extract_result_summary(html, label)
                summary["elapsed_s"] = round(elapsed_step, 1)
                results.append(summary)
                icon = "✓" if summary["ok"] else "✗"
                print(f"    {icon} {elapsed_step:.1f}s  artifact={summary['artifact_type'] or 'none'}  action_plan={summary['has_action_plan']}")
            except Exception as exc:
                elapsed_step = time.time() - t_step
                results.append({"label": label, "ok": False, "has_result": False,
                                 "has_action_plan": False, "has_grade": False,
                                 "public_findings": 0, "private_findings": 0,
                                 "artifact_type": "", "error": str(exc),
                                 "elapsed_s": round(elapsed_step, 1)})
                print(f"    ✗ FAILED after {elapsed_step:.1f}s: {exc}")

    elapsed = time.time() - t0
    print_report(results, elapsed)

    # Write JSON artefact
    out = Path(__file__).parent / "benchmark_nutrivault_results.json"
    out.write_text(json.dumps({
        "project": PROJECT_NAME,
        "project_id": pid,
        "total_elapsed_s": round(elapsed, 1),
        "results": results,
    }, indent=2))
    print(f"  JSON report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
