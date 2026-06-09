# SENTINEL-013 — Design: Research-Pipeline Hardening

**Step:** Design · **Status:** Draft for approval · **Author:** 2026-06-08
**Spec:** `docs/specs/SENTINEL-013/spec.md`

This design closes the three execution gaps in §1 of the spec with **surgical, localized** changes to
three existing modules — no new modules, no new tables, no new external dependency. Each phase is
independently shippable and ends with the full suite green. The sovereignty seam
(`resolve_model(cloud_allowed=)`) and the fail-soft contract are inherited unchanged.

---

## 1. Phase 1 — Real sovereign search (`tools/public/web_search.py`, `config/schema.py`)

### 1.1 The endpoint fix
`_duckduckgo` currently calls the Instant-Answer API (`https://api.duckduckgo.com/?format=json`), which
returns abstracts/disambiguation, not web results. Replace it with the DDG **HTML lite SERP**
(`https://lite.duckduckgo.com/lite/` or `https://html.duckduckgo.com/html/`, POST `q=`), parsing result
rows into the existing `_row(title, url, snippet)` shape. Keep:
- the existing `_TIMEOUT_S` explicit timeout,
- fail-soft (`_err(...)` on any network/parse error — AC-3),
- `wrap_source_material(snippet)` fencing (the Step-17 injection stance is unchanged),
- the typed `{"status","provider","results":[…],"notice"}` return.

Parsing is defensive: a missing/garbled row is skipped, not fatal; an empty parse returns `_ok([], …)`
(a clean gap), never raises. **No new dependency** — parse with `re` over the lite HTML (stable,
table-based) rather than adding a parser lib; if the regex finds nothing the result is an honest empty
list. (A heavier HTML parser is explicitly out of scope to keep the dependency surface flat.)

### 1.2 The stagger
Add `SearchConfig.stagger_s: float = 0.0` (keyed providers stay 0; the keyless DDG default is set > 0,
e.g. `1.5`). The per-run call counter already lives in `_make_function_tool`'s closure (`state["calls"]`);
extend that closure with the last-call timestamp and sleep `max(0, stagger_s - (now - last))` **before**
the fetch. The clock + sleep are **injected** (`now: Callable[[], float]`, `sleep: Callable[[float], None]`)
so a test asserts the spacing with a fake clock and **zero real sleeping** (AC-2). Default args bind to
`time.monotonic` / `time.sleep` so production is unchanged.

```python
def _make_function_tool(provider, results, max_calls=0, *, stagger_s=0.0,
                        now=time.monotonic, sleep=time.sleep):
    state = {"calls": 0, "last": None}
    def search(query: str) -> SearchResponse:
        ...                                     # empty/budget guards unchanged
        if stagger_s and state["last"] is not None:
            sleep(max(0.0, stagger_s - (now() - state["last"])))
        state["calls"] += 1
        state["last"] = now()
        return fetch(query.strip(), results)
```

`get_search_tool(provider, *, results, max_calls, stagger_s=0.0)` threads the new arg; `build_step_agents`
(spec.py:206) passes `cfg.search.stagger_s`.

## 2. Phase 2 — Concurrent level-scheduled execution (`agent/dag.py`, `config/schema.py`)

### 2.1 From sequential walk to level schedule
`_toposort` already yields a valid order. Replace the flat `for step in order:` loop with a **level
scheduler**: repeatedly select the frontier (every not-yet-run step whose `depends_on ⊆ satisfied`),
run that frontier **concurrently** via `asyncio.gather`, fold results, recompute the frontier. This is
the minimal change that exploits the parallelism the DAG already encodes; within a level there are no
inter-step data deps by construction, so dependency-state wiring (`_dependency_state`) is unchanged.

Each step's body (seed assembly → cache check → run → record) is extracted into an
`async def _run_one_step(step, ...) -> _StepOutcome` that returns a small record (status, artifact,
reasoner_call_delta, trace lines, missing markers) **instead of mutating shared state inline**. The
scheduler folds outcomes deterministically **in declared plan order** after each level's `gather`, so:
- `results`, `satisfied`, `produced`, `missing_inputs`, `degraded` are mutated on the single scheduler
  coroutine (no shared-state races),
- `produced` ordering = (level, then declared order) — stable and testable (AC-6),
- fail-soft is per-step: a raised exception inside `_run_one_step` is caught and returned as a
  `failed` outcome (we use `asyncio.gather(..., return_exceptions=True)` as a backstop, but the step
  body already guards), degrading only dependents (AC-6).

### 2.2 Budget under concurrency (AC-7)
The budget gate moves to **admission control**: before adding a step to the frontier batch, check
`budget.exhausted(steps_run, reasoner_calls, elapsed)` using counters that include the steps *already
admitted this level*. Reasoner-call accounting is reserved at admission (incremented when a reasoner
step is admitted), so N concurrent reasoner steps cannot collectively exceed `max_reasoner_calls`.
Steps that don't fit the remaining budget are marked `skipped`/degraded exactly as today. The
`wall_clock_s` ceiling is checked per level; an in-flight level is allowed to finish (no mid-step kill),
matching the existing "degrade, never crash" contract.

### 2.3 Global concurrency cap (AC-5)
Add a process-wide `asyncio.Semaphore` sized by a new config field
(`BackendConfig.max_concurrency: int = 3`, mirroring LeadFlow's Semaphore(3); a SENTINEL-013-only knob,
default chosen for the shared single-GPU endpoint). The semaphore wraps the **leaf LLM call** in
`orchestrator.run_step` (one acquire per step run), **not** the scheduler frontier — so the DAG may
*offer* a wide frontier but only `max_concurrency` LLM calls are ever in flight. Guarding the leaf (not
nesting acquires) is what prevents the deadlock risk in spec §6: a step never holds the semaphore while
waiting on another step. The semaphore is module-level + lazily created on the running loop so tests
and the web app share one cap.

### 2.4 What stays identical
`StepCache`, `_dependency_state`, `_assemble_result`/`assemble_generic`, `_finalize_result`, the
two-pass `_run_skill` split, and every public signature (`run_plan`/`run_dag`/`_execute_plan` kwargs).
A single-step or linear plan schedules one step per level → behaviourally identical to the old loop.

## 3. Phase 3 — Parallel per-source extract (`agent/modes/spec.py` or a small extract helper)

Today `build_step_agents` inserts one `extractor` agent reading all `{public_findings}`. The hardened
path, gated by `two_tier`:
- split `{public_findings}` into per-source units (the research step already returns a list of result
  rows; each row = one source),
- run the cheap **12B** extractor **once per source concurrently** (under the same global semaphore from
  §2.3), each call's input bounded to that single source (closes the unbounded-input F1/F2 class),
- **reduce** the per-source `Extraction`s into one `ExtractionSet` (plain code concatenation +
  `extract_max_notes_per_source` cap — already in `ResearchConfig`), which the synthesizer reads exactly
  as it does today.

Because the per-source extractor is a tool-free 12B reasoner-of-sorts (it distils, doesn't search), it
inherits sovereignty via `resolve_model(cloud_allowed=)`. With `two_tier=False` the whole branch is
skipped ⇒ byte-identical to today (AC-8 preserves AC-6 of SENTINEL-008). This phase is the most
invasive of the three and is **last** so Phases 1–2 ship value first; if the deadline bites, Phase 3 can
slip without blocking the bug fix or the latency win.

## 4. Sovereignty + regression (cross-cutting — AC-9, AC-10)

- An introspection test builds the full plan under `on_prem_required` and asserts no Gemini object is
  constructed anywhere in the concurrent path (the seam is unchanged, so this is a guard, not new work).
- No import of `redis`, `pymongo`, or any external-service client is added (grep-asserted in a test).
- The 446-test baseline is re-run at each phase; a live Crayon-task run after Phase 1 must show a
  non-degraded Result with ≥1 cited source.

## 5. Test plan (per phase)

| Phase | New tests |
|---|---|
| 1 | DDG SERP parse → URL-bearing rows (AC-1); stagger spacing with fake clock, no real sleep (AC-2); error → typed empty fail-soft (AC-3) |
| 2 | two independent branches overlap via injected barrier (AC-4); peak concurrency ≤ cap (AC-5); concurrent vs sequential produce identical set/flags/citations + single-failure degrades only dependents (AC-6); budget ceiling not exceeded under fan-out (AC-7) |
| 3 | per-source extractor call count = source count + bounded input (AC-8); `two_tier=False` byte-identical (AC-8) |
| X-cut | zero-Gemini introspection under on_prem (AC-9); no redis/pymongo import (AC-9); full suite green (AC-10) |

All tests hermetic: `SENTINEL_DATA_DIR=$(mktemp -d) .venv/bin/python -m pytest -q`; no network (SERP +
LLM mocked), no real sleeping (injected clock/sleep).
