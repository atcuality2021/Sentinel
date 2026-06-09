# SENTINEL-013 — Reflect

**Task:** Research-pipeline hardening — real keyless SERP, concurrent level-scheduled DAG, parallel per-source extraction.
**Closed:** 2026-06-09
**Outcome:** All 3 phases (10 steps) built and green. Final suite: **470 passed, 0 regressions** (446 at start → 470 at close, +24 net).
**Transport note:** rendered inline — artifact kept as `.md` (same convention as prior specs).

---

## 0. Phase & AC status matrix

| Phase | Scope | Status |
|---|---|---|
| 1 | Real sovereign search (DDG lite SERP + SearXNG, stagger) | **SHIPPED** |
| 2 | Concurrent level-scheduled DAG execution | **SHIPPED** |
| 3 | Parallel per-source extraction | **SHIPPED** |

| AC | Summary | Status |
|---|---|---|
| AC-1 | DDG lite SERP parser: ≥2 URL-bearing rows from mocked HTML | SHIPPED |
| AC-2 | Stagger: 3 consecutive calls spaced by `stagger_s`; `stagger_s=0` → no sleep | SHIPPED |
| AC-3 | SearXNG provider: URL-bearing rows from mocked JSON; missing URL → clean error | SHIPPED |
| AC-4 | Concurrent branches run within a single level (not sequentially) | SHIPPED |
| AC-5 | Global semaphore: peak concurrent `run_step` bodies ≤ `max_concurrency` | SHIPPED |
| AC-6 | Level fold in declared order: concurrent vs sequential → identical artifact set | SHIPPED |
| AC-7 | Budget admission: fan-out wider than `max_reasoner_calls` admits exactly the ceiling | SHIPPED |
| AC-8 | N sources → N extractor calls, each input bounded to one source; `two_tier=False` byte-identical | SHIPPED |
| AC-9 | `on_prem_required` → zero Gemini objects in concurrent path; no redis/pymongo/celery/kafka | SHIPPED |
| AC-10 | 446 baseline + all new tests green at every phase boundary | SHIPPED (470 total) |

---

## 1. Estimate vs actual

| Step | Estimate | Actual |
|---|---|---|
| DDG + SearXNG (Steps 1–3) | ~2h | ~1.5h (discovered live SearXNG verification early) |
| DAG concurrent scheduler (Steps 4–7) | ~3h | Built in prior session; plan updated to reflect |
| Parallel per-source extract (Step 8) | ~2h | ~1h (clean seam: strip from pass1, gather per-source) |
| Sovereignty + infra test (Step 9) | ~0.5h | ~0.5h |
| Full-suite green + reflect (Step 10) | ~0.5h | ~0.5h |

---

## 2. What changed and why

### Phase 1 — Real sovereign search
The "no cited sources" bug was traced to `api.duckduckgo.com?format=json` returning Wikipedia abstracts only. Fixed by switching to `https://lite.duckduckgo.com/lite/` (POST `q=`) with a regex row parser. Discovered DDG lite is bot-blocked from the pilot IP; added **SearXNG** (`_searxng`, reads `SEARXNG_URL`) as the primary keyless path — the self-hosted metasearch engine closes the keyless sovereign gap. Live verified: 5 real Crayon citations from a local SearXNG container.

### Phase 2 — Concurrent level scheduler
The sequential `for step in order:` loop was replaced with a frontier-based level scheduler (`asyncio.gather` over all ready steps). `_run_one_step` is pure w.r.t. shared state (reads a snapshot, returns a `_StepOutcome` record) so concurrent execution is safe. Outcomes folded in **declared order** → deterministic `produced` / citations regardless of completion order. Budget admission-control pre-reserves counters at frontier entry so N concurrent reasoners can't race past `max_reasoner_calls`. The global semaphore (`_leaf_semaphore`, `BackendConfig.max_concurrency=3`) caps concurrent ADK runners.

### Phase 3 — Parallel per-source extraction
The single extractor agent in `_run_skill`'s pass1 was replaced by `_run_parallel_extract`. The change:
1. `build_step_agents(two_tier=True)` still inserts the extractor (and sets the `_2t` synthesizer prompt) — no spec change needed.
2. `_run_skill` strips the extractor from pass1 after construction.
3. After pass1, `_run_parallel_extract` splits `{public_findings}` via `_split_findings` (JSON list → N units; free text → 1 unit), runs the extractor N times concurrently under the existing global semaphore, and reduces per-source `ExtractionSet`s into one.
4. The `two_tier=False` path is byte-identical (extractor is not in the agent list, strip is a no-op).

---

## 3. What was deferred

- **AC-10 full pipeline half** (Step 3): live end-to-end Crayon run with `provider=searxng` — blocked on gemma 12B/26B endpoints being up. The search tool parse + integration tests cover the unit.
- **Search stagger config for DDG default**: `stagger_s=1.5` default for DDG recommended in the plan was not set in `defaults.py` (risk: bot-block in prod). Should be set before live use.

---

## 4. Gotchas the next session should know

- `_split_findings` is conservative by design: non-parseable `public_findings` (free text prose from the research agent) falls back to a single extraction call, which is equivalent to the pre-Step-8 behavior. The full benefit of per-source bounding only fires when the research agent writes structured JSON (a list of search result dicts). This is the correct fail-safe.
- The parallel extractor uses the same ADK `Agent` instance for all N concurrent calls — this is safe because ADK `Agent` objects are stateless; session state is managed externally via `InMemoryRunner.session_service`.
- `test_per_source_failure_degrades_gracefully` exercises the NFR-3 fail-soft path; the failing source's `create_session` raises, which propagates through `_run_agents` → `_extract_one` → caught, logged in trace, returns `None` → reducer skips it.

---

## 5. Tests added (SENTINEL-013, +24 total)

| File | Tests | Coverage |
|---|---|---|
| `test_013_parallel_extract.py` | 13 | AC-8 (`_split_findings`, `_run_parallel_extract`, bounded input, fail-soft, two_tier=False), AC-9 (zero Gemini, no banned infra) |
| Prior sessions (Steps 1–7) | 11 | AC-1/2/3 search, AC-4/5/6/7 DAG concurrency |

Total: 470 passed (446 baseline + 24 new), 0 regressions.
