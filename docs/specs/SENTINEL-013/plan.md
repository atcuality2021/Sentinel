# SENTINEL-013 — Plan

**Step:** Plan · **Spec:** [`spec.md`](./spec.md) · **Design:** [`design.md`](./design.md)
**Status:** Draft for approval · **Format:** `.md` to match the prior SENTINEL specs (waiver on AP-#11 `.html`)
**Baseline:** 446 tests green (pinned 2026-06-08). Each step ends with the full suite green; tests are
hermetic (SERP + LLM mocked, injected clock/sleep — no network, no real sleeping). Test IDs → spec ACs.

---

## Phase 1 — Real sovereign search (fixes the "no cited sources" bug)

### Step 1 — Real keyless SERP (DDG lite + SearXNG) ✅ BUILT 2026-06-08
`tools/public/web_search.py`: rewrite `_duckduckgo` to POST the DDG lite SERP
(`https://lite.duckduckgo.com/lite/`, `q=`) and parse rows → `_row(title, url, snippet)`. Preserve the
explicit timeout, fail-soft `_err(...)`, `wrap_source_material`, and the typed return shape. Parse
defensively with `re` (no new dependency); empty parse → `_ok([], "duckduckgo")`.
**Discovered during build:** keyless DDG is bot-blocked (HTTP 202) from the pilot IP and Brave dropped
its free tier. Added a new **sovereign `searxng` provider** (`_searxng`, reads `SEARXNG_URL`, JSON API)
as the primary keyless path; registered in the provider enum across 6 sites (web_search `_FETCHERS`,
schema Literals, defaults `_SEARCH_PROVIDERS`, settings `_VALID_PROVIDERS`/`_FALLBACKS`, render UI).
**Test (AC-1, AC-3):** a mocked lite-SERP HTML payload yields ≥2 URL-bearing rows; a mocked SearXNG JSON
payload yields URL-bearing rows; a raised `httpx`/parse error returns `{"status":"error","results":[]}`
and never raises; missing `SEARXNG_URL` returns a clean typed error.

### Step 2 — Search stagger ✅ BUILT 2026-06-09
`config/schema.py`: add `SearchConfig.stagger_s: float = 0.0`; set the keyless DDG default > 0 in
`defaults.py` (e.g. `1.5`). `web_search.py`: thread `stagger_s` + injectable `now`/`sleep` through
`_make_function_tool` and `get_search_tool`; sleep `max(0, stagger_s - (now-last))` before each fetch.
`modes/spec.py:206`: pass `cfg.search.stagger_s`.
**Test (AC-2):** with a fake clock + recording `sleep`, three consecutive `search()` calls are spaced by
`stagger_s`; **zero real sleeping**; `stagger_s=0` ⇒ no sleep call.

### Step 3 — Live verify + report ✅ SEARCH HALF VERIFIED 2026-06-08
Run the Crayon task live on the e2e DB; confirm a **non-degraded** Result with **≥1 cited source**.
**Verified (search half of AC-10):** local SearXNG container (`docker run -d --name sentinel-searxng -p
8888:8080 -v /tmp/searxng/settings.yml:/etc/searxng/settings.yml searxng/searxng:latest`) → Sentinel
`get_search_tool('searxng')` returned 5 real cited Crayon results (crayon.co, vendr.com, g2.com), each
snippet fenced as source material. **Remaining (full-pipeline half):** point the e2e config at
`provider=searxng` + `SEARXNG_URL` and run the end-to-end Crayon task for the non-degraded Result —
needs the gemma 12B/26B endpoints up.
**Test (AC-10 partial):** the live check is manual; committed regression tests assert the search tool
parses real SERP/JSON rows into URL-bearing fenced source material (governance + phase3-injection suites).

---

## Phase 2 — Concurrent level-scheduled execution (latency win)

### Step 4 — Extract `_run_one_step` ✅ BUILT 2026-06-09
`agent/dag.py`: lift the per-step body (seed assembly → cache check → run skill/created/aggregator →
build outcome) out of the loop into `async def _run_one_step(step, *, by_id, results_snapshot, …)
-> _StepOutcome` (new frozen dataclass: status, output_key, artifact|None, reasoner_delta, trace[],
missing[]). **Pure** w.r.t. shared state — reads a snapshot, returns a record. No behaviour change yet
(still called sequentially).
**Test (AC-6 setup):** existing DAG tests stay green (the refactor is behaviour-preserving).

### Step 5 — Level scheduler + deterministic fold ✅ BUILT 2026-06-09
`agent/dag.py`: replace `for step in order:` with the frontier loop — select ready steps, run via
`asyncio.gather(*[_run_one_step(...)], return_exceptions=True)`, fold outcomes **in declared plan order**
into `results`/`satisfied`/`produced`/`missing_inputs`/`degraded`. `produced` order = (level, declared).
**Test (AC-4, AC-6):** a 2-branch plan runs both branches' steps in one level (an injected per-step
barrier proves overlap, not sequence); concurrent vs sequential produce identical artifact set, `degraded`/
`missing_inputs`, and citation union; a single mid-branch failure degrades only its dependents.

### Step 6 — Budget admission control under concurrency ✅ BUILT 2026-06-09
`agent/dag.py`: move the budget check to frontier **admission** — counters include steps admitted this
level; reasoner-calls reserved at admission so N concurrent reasoners can't exceed `max_reasoner_calls`;
`wall_clock_s` checked per level (in-flight level finishes). Over-budget steps → `skipped`/degraded.
**Test (AC-7):** a fan-out wider than `max_reasoner_calls` admits exactly the ceiling, returns a partial
Result, never over-spends.

### Step 7 — Global concurrency cap ✅ BUILT 2026-06-09
`config/schema.py`: `BackendConfig.max_concurrency: int = 3`. `agent/orchestrator.py`: wrap the leaf LLM
call in `run_step` with a module-level `asyncio.Semaphore` (lazily bound to the running loop), one
acquire per step. Guard the leaf only (no nested acquire) → no deadlock.
**Test (AC-5):** under a frontier wider than the cap, observed peak concurrent `run_step` bodies ≤
`max_concurrency` (instrumented counter); deepest linear plan does not deadlock.

---

## Phase 3 — Parallel per-source extract

### Step 8 — Per-source extract + reduce ✅ BUILT 2026-06-09
`agent/modes/spec.py` (or a new `agent/extract.py` helper invoked from `_run_skill`): when `two_tier`,
split `{public_findings}` rows into per-source units, run the 12B extractor once per source concurrently
(under the §2.3 semaphore), reduce per-source `Extraction`s → one `ExtractionSet` (code-level concat +
`extract_max_notes_per_source` cap). Synthesizer reads `{extractions}` unchanged.
**Test (AC-8):** N sources ⇒ N extractor calls, each input bounded to one source; reduced `ExtractionSet`
feeds synthesis; `two_tier=False` path byte-identical (no extractor calls).

---

## Cross-cutting gates (verified at every phase)

### Step 9 — Sovereignty + no-infra introspection ✅ BUILT 2026-06-09
**Test (AC-9):** build the full hardened plan under `on_prem_required`; assert zero Gemini objects in the
concurrent path; assert no `redis`/`pymongo` import is added (grep test). Run after each phase.

### Step 10 — Full-suite green + reflect ✅ BUILT 2026-06-09
**Test (AC-10):** 446 baseline + all new tests green at each phase boundary. After Phase 3, write
`reflect.md`, capture estimate actuals, emit the task-closure event, update `MEMORY.md`.

---

## Sequencing note (deadline 2026-06-11 17:00 PT)
Phase 1 (Steps 1–3) alone fixes the user-visible bug and is shippable standalone — **ship it first**.
Phase 2 (latency) and Phase 3 (extract quality) are additive and can land independently if time is tight.
No step depends on a later phase. No ADR required (code + in-memory Pydantic config only — spec §7).
