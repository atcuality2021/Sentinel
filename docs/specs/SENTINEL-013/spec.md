# SENTINEL-013 — Research-Pipeline Hardening: Real Search, Concurrent Map-Reduce, Parallel Extract

**Step:** Spec · **Status:** Draft for approval (2026-06-08) · **Author:** 2026-06-08
**Depends on:** SENTINEL-005 (`get_search_tool` provider layer), SENTINEL-008 (declarative
`ResearchModeSpec` + two-tier extract→synthesize), SENTINEL-011 (Gemma-4 tiering, two-pass execution),
SENTINEL-012 (Project/Task, `_execute_plan` DAG engine, `StepCache`, `TaskBudget`)
**Blocks:** the live pilot demo (real cited output + acceptable latency at project scale)
**Source:** the LeadFlow CRM `research_pipeline.py` flow (3-stage map-reduce: parallel GATHER →
parallel EXTRACT → SYNTHESIZE) — ported as an **improved, sovereign** version onto Sentinel's existing
engine, wired to our gemma-4-12B (tools/extract) + gemma-4-26B (reason/synthesize).
**Test baseline (pinned `pytest --collect-only`, 2026-06-08):** **446 tests** green.

---

## 1. Context / problem

A live run of the BiltIQ "profile us → competitor → compare" task (the Crayon task, 2026-06-08)
produced a **PARTIAL** result with **no cited sources**. Root-causing against the code, not the symptom,
surfaced three structural gaps between Sentinel's engine and the proven LeadFlow research-pipeline flow.
Sentinel already has the *shape* of the map-reduce (declarative `plan→research→extract→synthesize`
steps, a two-tier 12B→26B split, per-entity `StepCache`, `TaskBudget`, typed cited artifacts). What it
lacks is the parts of the LeadFlow flow that make the output *real* and the latency *acceptable*:

**(a) The DuckDuckGo provider hits the wrong endpoint — this is the "no cited sources" bug.**
`tools/public/web_search.py:30` queries `https://api.duckduckgo.com/` with `format=json` — the
**Instant Answer API**, which returns only Wikipedia-style abstracts + disambiguation topics. For a
real research query (*"Crayon competitive intelligence pricing"*) it returns essentially nothing →
empty `public_findings` → the synthesizer has nothing to cite → the artifact is honestly flagged
PARTIAL with zero sources. The sovereign no-cloud path therefore has **no real eyes on the web**.
LeadFlow deliberately uses a real DDG SERP with a request stagger.

**(b) The DAG executor runs fully sequentially — even where the plan is parallel.**
`agent/dag.py:368` is a flat `for step in order:` walk. Independent branches the plan *encodes* as
parallel (`self_profile`, `competitor_0`, `competitor_1` — all zero-in-degree or sibling) run strictly
one-after-another. The "map" in Sentinel's map-reduce is **latent in the DAG data but serialized by the
executor**. LeadFlow's entire speed story is `asyncio` fan-out under an `asyncio.Semaphore(3)`.

**(c) The extractor is a single call, not a per-source parallel map.**
`agent/modes/spec.py:226` inserts **one** `extractor` agent over all `{public_findings}`. LeadFlow runs
its cheap extractor **once per source, in parallel**, which (i) bounds each small-model call's input
(the F1/F2 token-overflow class of bug) and (ii) parallelizes the map. Sentinel collapses the map to a
single 12B call whose input grows unbounded with source count.

There is **no global concurrency cap**: `TaskBudget` ceilings a single task (steps / 26B-calls /
wall-clock), but nothing bounds concurrent GPU load once (b) introduces parallelism — a research burst
could starve the interactive chat path on the shared endpoint.

> **Not a solution restatement:** the ask is not "re-port LeadFlow." Sentinel already has the better
> decomposition (composable skills + sovereign SQLite/`StepCache`, not monolithic configs + Redis/Mongo).
> The ask is to **close the three execution gaps** — real search, concurrent level-scheduling, parallel
> per-source extract — so the existing pipeline produces real cited output at acceptable latency,
> *without* regressing the sovereignty moat (zero external services, zero Gemini under `on_prem_required`).

## 2. Goal / non-goals

**Goal:**
1. **Real sovereign search.** Replace the DDG Instant-Answer endpoint with a real DDG SERP (lite/HTML)
   that returns titled, URL'd, snippet'd results a synthesizer can cite; add a configurable inter-call
   **stagger** to dodge rate-limiting on the keyless provider. Brave/SerpAPI paths unchanged.
   **Built outcome (2026-06-08):** keyless DDG turned out to be bot-blocked (HTTP 202) from the pilot IP
   and Brave dropped its free tier, so the *primary sovereign* provider shipped is a new **self-hosted
   SearXNG** integration (`SEARXNG_URL` env, JSON API) — zero third-party egress, no key, not IP-blocked
   (it queries upstream engines server-side). The DDG lite-SERP parser still ships as a keyless fallback.
2. **Concurrent level-scheduled execution.** `_execute_plan` runs each topological *level* (steps whose
   deps are all satisfied) concurrently under a bounded `asyncio.Semaphore`, replacing the flat
   sequential loop — preserving fail-soft, budgets, cache, and deterministic results.
3. **Global concurrency cap.** A process-wide semaphore (configurable `max_concurrency`) bounds
   simultaneous in-flight LLM steps so a research fan-out can't starve interactive use.
4. **Parallel per-source extract.** When `two_tier` is on, run the cheap 12B extractor **per source in
   parallel** (bounded input per call), reducing into one `ExtractionSet` the synthesizer reads — the
   real map-reduce "map", on our 12B.
5. **No regression, no new infra.** The 446-test baseline stays green; no Redis, no MongoDB, no new
   tables (sovereign SQLite + `StepCache` retained); `on_prem_required` still constructs zero Gemini
   objects; default (untiered/single-tier) output stays byte-identical where the path is unchanged.

**Non-goals (this task):** porting Redis/Mongo (sovereign zero-egress moat — deliberately *not* ported);
a new LLM planner (SENTINEL-012 Phase 3d territory); new domain skills; multi-stage TTL cache tiers (the
freshness-gated `StepCache` is sufficient — listed as a deferred option, not built here); changing the
result/artifact schemas.

## 3. The flow (LeadFlow → Sentinel, improved)

```
LeadFlow                         Sentinel today                  SENTINEL-013 (this task)
────────────────────────────────────────────────────────────────────────────────────────
GATHER (parallel fetch +     →   search() function tool,     →   real DDG SERP + stagger;
  staggered 10s DDG)             single-shot, Instant-API        function-tool loop unchanged
                                 (returns ~nothing)              (G1)
EXTRACT (E4B, per-source,    →   ONE extractor (12B) over     →   per-source 12B extract, run
  parallel)                      all findings                    concurrently → ExtractionSet (G4)
SYNTHESIZE (35B)             →   synthesizer (26B, SSE)       →   unchanged (already correct)
PERSIST → MongoDB            →   RunStore (SQLite) +          →   unchanged (sovereign)
                                 StepCache + typed artifacts
Semaphore(3)                 →   TaskBudget (per-task only)   →   + global Semaphore cap (G3)
[sequential per task]            flat sequential DAG walk     →   level-scheduled asyncio.gather (G2)
```

`G1`/`G2`/`G3`/`G4` map to the goals above and to the phasing in §5.

## 4. Acceptance criteria (binary)

- **AC-1 (real search):** a sovereign keyless provider returns real web results (title + resolvable URL +
  snippet) for a normal research query — proven by tests asserting non-empty, URL-bearing rows from a
  mocked SERP HTML payload (DDG lite, not the Instant-Answer abstract shape) **and** from a mocked
  SearXNG JSON payload. Brave/SerpAPI rows unchanged. *Live-verified 2026-06-08* via a local SearXNG
  container: `get_search_tool('searxng')` returned 5 cited Crayon results, snippets fenced as source
  material.
- **AC-2 (search stagger):** consecutive function-tool `search()` calls within a run are spaced by a
  configurable `stagger_s` (default > 0 for the keyless DDG provider, 0 for keyed providers); proven by
  a test with an injected clock asserting the gap, with **zero real sleeping** in the suite.
- **AC-3 (fail-soft preserved):** a search HTTP/parse error still returns the typed `{"status":"error",
  …, "results":[]}` shape and never raises (NFR-3 unchanged).
- **AC-4 (concurrent levels):** `_execute_plan` runs independent same-level steps concurrently; a plan
  with two independent branches completes with all branches' artifacts present, and a test proves
  overlap (e.g. via an injected per-step barrier/counter), not sequential execution.
- **AC-5 (concurrency cap):** no more than `max_concurrency` LLM steps run simultaneously across the
  process; proven by a test observing peak concurrency ≤ cap under a fan-out wider than the cap.
- **AC-6 (determinism + fail-soft under concurrency):** with concurrency on, the produced artifact set,
  `degraded`/`missing_inputs` flags, and citation union are identical to the sequential executor for the
  same plan; a single step failure still degrades only its dependents (AC-15 of 012 preserved).
- **AC-7 (budgets under concurrency):** `TaskBudget` (max steps / 26B-calls / wall-clock) is still
  enforced and still returns a partial Result — the cap is checked correctly when steps run concurrently
  (no over-spend race).
- **AC-8 (parallel per-source extract):** with `two_tier` on, the extractor runs once per source
  concurrently and reduces to one `ExtractionSet`; each call's input is bounded to a single source;
  proven by a test asserting per-source calls + a bounded input size. With `two_tier` off, the path is
  byte-identical to today (AC-6 of 008 preserved).
- **AC-9 (sovereignty unchanged):** under `on_prem_required`, the whole hardened pipeline constructs
  **zero Gemini objects** (introspection test) and makes no external-service (Redis/Mongo) call.
- **AC-10 (no regression):** the full suite — 446 baseline + new tests — is green; the live Crayon task
  produces a **non-degraded** Result with **≥1 cited source** (the bug in §1a is demonstrably fixed).

## 5. Phasing (each independently shippable, each ends green)

- **Phase 1 — Real search (G1).** Fix the DDG provider (real SERP) + add `stagger_s` to `SearchConfig`
  and the function-tool loop. Smallest change; directly fixes the observed bug; makes the *existing*
  pipeline produce citations. *Verify live on the Crayon task before proceeding.* (AC-1, AC-2, AC-3)
- **Phase 2 — Concurrent execution (G2 + G3).** Level-scheduled `asyncio.gather` in `_execute_plan` +
  process-wide `max_concurrency` semaphore + per-task budget re-checked correctly under concurrency.
  Biggest latency win. (AC-4, AC-5, AC-6, AC-7)
- **Phase 3 — Parallel per-source extract (G4).** Per-source 12B extraction, concurrent, reduced to one
  `ExtractionSet`, bounded input per call. (AC-8)
- **Sovereignty + regression (G5)** are cross-cutting gates verified at every phase. (AC-9, AC-10)

## 6. Risks

- **Concurrency introduces nondeterminism** in result *ordering* (not content). Mitigation: AC-6 pins
  the produced *set* + flags + citation union as order-independent; the `produced` completion-order list
  becomes a level-ordered, then declared-order, sort — tested.
- **DDG SERP scraping is brittle / may rate-limit.** Mitigation: the stagger (AC-2); fail-soft preserved
  (AC-3) so a blocked query degrades to a gap, never a crash; Brave/SerpAPI remain the keyed fallbacks.
- **Global semaphore could deadlock** if a step waits on a sub-step that also needs the semaphore.
  Mitigation: the cap guards *leaf LLM calls only* (one acquire per `run_step`), never nested; documented
  + tested for the deepest plan.
- **Budget race under concurrency** (N steps pass the gate, then all run, overspending). Mitigation:
  budget is checked + decremented atomically before each acquire; AC-7 tests peak spend ≤ ceiling.
- **Deadline (2026-06-11 17:00 PT).** Phase 1 alone fixes the user-visible bug and is shippable in
  isolation; Phases 2–3 are latency/quality and can land independently if time is tight.

## 7. Compliance / ADR note

All changes are **code + in-memory Pydantic config-field additions** (`SearchConfig.stagger_s`,
a concurrency setting). **No DDL, no new tables, no new external dependency** ⇒ **no ADR required**
(consistent with the SENTINEL-012 store-schema rule: TEXT/JSON-column-resident and in-memory model
changes are ADR-exempt; only columnar/table DDL needs an ADR). Repo compliance mode is `cloud_ok`; the
sovereign-deployment invariant (`on_prem_required` ⇒ zero Gemini, zero external services) is preserved
and asserted (AC-9). Secrets remain `.env`-only; no new keys are introduced (DDG is keyless).

## 8. References
- Engine: `agent/dag.py` (`_execute_plan` sequential loop, `StepCache`, `TaskBudget`),
  `agent/modes/spec.py` (`build_step_agents`, two-tier extractor insertion),
  `tools/public/web_search.py` (`_duckduckgo`, `_make_function_tool`)
- Config: `config/schema.py` (`SearchConfig`, `ResearchConfig`)
- Memory: `sentinel-per-task-route` (the Crayon bug context), `sentinel-streaming-524`
  (why reasoners SSE-stream on 26B), `sentinel-vllm-server-gaps`, `sentinel-008-research-depth`
- Source flow: LeadFlow `research_pipeline.py` (3-stage map-reduce; Semaphore(3); staggered DDG)
