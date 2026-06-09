# SENTINEL-012 — Reflect

**Task:** Universal research agent — Project → Task → Orchestrator → typed/cited/persona-adapted Result.
**Closed:** 2026-06-08
**Outcome:** All 4 phases (0–3, 17 steps) built and green. Final suite: **400 passed, 0 regressions** (281 at Phase-0 start → 400 at close, +119 net).
**Transport note:** rendered inline (Claude) — the vLLM Socratic driver path was not used this run; artifact kept as `.md` to match the repo's existing `spec.md`/`design.md`/`plan.md` convention.

---

## 0. Phase & AC status matrix (umbrella close-or-descope — PC-M17-01 / PC-M21M27-01)

SENTINEL-012 is a **single multi-phase milestone**, not an umbrella of sub-task IDs. The prior
Intelligence-to-Action tasks (SENTINEL-008/009/010/011) shipped independently and *fed* this task; they
are not sub-tasks of it. Phase status:

| Phase | Scope | Status |
|---|---|---|
| 0 | Engine refactor (role-partition, `run_step`, declarative `ResearchModeSpec`) | **SHIPPED** |
| 1 | Foundations (Project/Task/Plan schemas, store ADR-0003, `/projects` UI shell) | **SHIPPED** |
| 2 | Fixed value chain (self_profile, compare, program-strategy, persona, DAG budget/cache, model-grader) | **SHIPPED** |
| 3 | Dynamic orchestrator (planner, registry+persist ADR-0004, autonomy gate, injection stance) | **SHIPPED** |

AC ledger (21 ACs). **Honest split: "SHIPPED" = built end-to-end + tested; "DEFERRED-integration" = the
unit is built and unit-tested but not yet wired into the orchestrated Task execution path.**

| AC | Summary | Status |
|---|---|---|
| AC-1 | Project create/persist incl. autonomy setting | SHIPPED |
| AC-2 | Task carries objective/domain/persona; template | SHIPPED |
| AC-3 | Orchestrator: Task → Plan (DAG w/ capability annotations) | SHIPPED (Step 15) |
| AC-4 | Bind existing AgentSpec or emit created spec; gate by mode | SHIPPED (Steps 14–16) |
| AC-5 | Staffed DAG executes on two-pass engine; schema-valid artifacts | SHIPPED (Step 13) |
| AC-6 | `self_profile` + `compare` domain skills | SHIPPED (Steps 7–9) |
| AC-7 | BiltIQ map→compare→strategy end-to-end | SHIPPED (coordinator + value chain) |
| AC-8 | Persona changes output, not facts | **DEFERRED-integration** (persona.py + tests built Step 11; not yet wired into `run_plan`) |
| AC-9 | Existing modes + baseline stay green; additive | SHIPPED (400 green) |
| AC-10 | UX Project→Task→Orchestrate→Execute→Results | SHIPPED (plan-review screen Step 16) |
| AC-11 | Refactor byte-identical golden | SHIPPED (Phase 0/2) |
| AC-12 | Created-agent safety (reject tool-bearing reasoner / off-allowlist tool) | SHIPPED (Step 14) |
| AC-13 | Autonomy defaults to propose-then-approve | SHIPPED (Step 16) |
| AC-14 | High-stakes domain task creation rejected | SHIPPED (`is_high_stakes` gate + test) |
| AC-15 | Budgets/cache (max-steps, max-26B, wall-clock) | SHIPPED (Step 10) |
| AC-16 | Step status+timing persisted; resume-from-last-good | SHIPPED (`Step.started_at/finished_at`; dag resume) |
| AC-17 | Persona invariance (sources/finding_texts identical across personas) | **DEFERRED-integration** (proven at unit level; see AC-8) |
| AC-18 | Code-grade gate on every result | SHIPPED (Steps 12–13) |
| AC-19 | Model-grade rubric over eval set | **DEFERRED-integration** (`model_grade` + `eval/runner.py` built Steps 12–13; not on sampled-production path §10.4) |
| AC-20 | Versioned golden eval set + regression | **DEFERRED-integration** (runner built; per-domain versioned sets not yet seeded) |
| AC-21 | Reuse-on-similarity for known capability | SHIPPED (Step 14 `registry.resolve`) |

**No silent abandonment:** the three DEFERRED-integration ACs are tracked in §6 with explicit triggers.

**Per-phase reflects (PC-M29-01) — deviation, logged:** separate `phase{0..3}-reflect.md` files were
**not** produced. Each step instead closed with an inline BiltIQ-format completion report (what/files/tests/
anti-patterns/insights) delivered in-session and promoted to `MEMORY` (`sentinel-*` memory files). For a
solo, single-session-chain build this was the honest record; fabricating four backdated phase reflects would
be lower-integrity than this note. Flagged as a process item in §4.

**Promotion amendment (PC-M17-02):** none — no sub-task was promoted to a standalone milestone during this
task. **Closed-PR audit (PC-M21M27-02):** N/A — repo is not under git (`git_repo=false`); work landed as
direct working-tree edits, no PRs opened or closed.

---

## 1. What went well (repeat these)

- **`design.md` §9.2 "no runtime escalation" envelope paid off three steps later.** Because the design fixed
  that created specs are PUBLIC-only + tool-free *before* any code, Step 15's `_mint_created_spec` and Step 17's
  injection stance were near-trivial: the safety property was already a build-time invariant, so Step 17 mostly
  *proved* a guarantee that already existed rather than adding new enforcement. The control-plane defence was
  free because the design front-loaded it.
- **Deterministic spec IDs (`seed-{cap}-{domain}` / `created-{domain}-{cap}`) chosen in Step 14 became free
  signals downstream.** Step 16's plan-review UI labels every step reuse-vs-new with a pure `startswith("seed-")`
  string check — no extra lookup. An ID scheme picked for idempotency doubled as a reviewer affordance.
- **Hermetic FakeRunner pattern held across the whole of Phase 3.** The same `InMemoryRunner` monkeypatch +
  state-injection shape unit-tested the planner, the autonomy gate, and the seeded-plan execution without a
  single network call. Reusable test infrastructure meant every step's test cost dropped over time.
- **"Each step ends with the full suite green" was the right hard rule.** Catching the Step-15 `streaming=True`
  ValidationError immediately (not three steps later) was only possible because the suite ran every step. Zero
  regressions across 5 steps (369→400).
- **Additive-by-construction (dark/opt-in) honored AC-9 the whole way.** New fields, new tables (ADR-0004 needed
  no `ALTER`), new prompt suffixes — never a mutation of the shipped competitor/client path. The byte-identical
  golden (AC-11) never broke.

## 2. What went wrong (anti-patterns I caught in Review/Test)

- **Anti-pattern #9 (Deprecated API) — `streaming=True` passed to `run_step`.** In Step 15 `plan_task` first
  passed a bare `True` where ADK's `RunConfig` requires a `StreamingMode` enum → ValidationError at
  orchestrator.py:393. Caught by the step's own test on first run; fixed by lazy-importing `StreamingMode.SSE`,
  mirroring `eval/graders.py`. Root cause: I reached for the obvious literal instead of reading how the existing
  caller (the model-grader) already did it — a near-miss of **Anti-pattern #1 (Reinvention)**.
- **Anti-pattern #1 (Reinvention) avoided, but only by an explicit check.** Before writing Step 16's gate I
  confirmed `run_dag` (Step 13) already existed and composed it (~15 lines) rather than writing a second
  execution path. Likewise Step 17 built on `tests/test_boundary.py`'s structural-introspection pattern instead
  of inventing a new one. The discipline worked, but it was manual each time.
- **Scope over-framing on Step 14 (caught before building).** I initially framed Step 14 as "needs a persisted
  schema change" when ADR-0003 had *deferred* exactly that table and none of the step's tests required
  persistence. Surfaced the fork via `AskUserQuestion`; dev chose persist-now → ADR-0004 first. The right outcome,
  but the over-scoping would have been silent if not flagged.

## 3. What we missed (slipped past Review/Test)

- **The created-capability *execution* gap (`dag.py:315`) is the one real miss.** Steps 14–16 all pass while the
  DAG runner still staffs purely by `SKILL_SPECS.get(step.capability)` — so an `autonomous` run of a plan
  containing a *created* capability degrades that step fail-soft instead of building the minted specialist via
  `build_from_spec`. Every test stayed green because the tests exercise *seeded* plans (which run fully) and the
  *persistence/validation* of created specs (which works) — but never an autonomous run *through* a created step.
  **The green suite gave false confidence about an integration that doesn't exist yet.** This is the most
  important lesson: a passing unit suite proved each half (mint, persist, validate, gate) without proving the
  seam between them.
- **Persona and model-grade built but never integrated.** `persona.py` (Step 11) and `model_grade` (Step 12)
  have green unit tests, so AC-8/AC-17/AC-19/AC-20 *looked* addressed — but neither is wired into the orchestrated
  `run_plan` path. A unit-test-only AC reads as "done" in a step report when it is really "done in isolation."

## 4. Process changes proposed

- **Add an "integration AC" convention to `spec.md`.** When an AC is satisfiable by either a unit *or* an
  end-to-end path, the spec should tag which one the AC demands. Three ACs here (8/17/19) were marked progressing
  on unit evidence alone. Proposed: ACs that describe *observable product behaviour* require an end-to-end test,
  not a unit test, to flip to DONE.
- **`AGENT_RULES.md`: add a "seam test" expectation for multi-step features.** Anti-pattern #1 defends against
  *reinventing* a component; we have no rule that defends against *building two components that are never wired
  together*. Propose a gate: a feature spanning N steps needs at least one test that exercises the **seam**
  (here: an autonomous run through a created-spec step) before the umbrella reflect.
- **Per-phase reflect automation.** PC-M29-01 expects per-phase reflect files; this run produced inline step
  reports instead. Either (a) the harness should accept promoted in-session reports as the phase record, or (b)
  the step command should auto-emit a `phaseN-reflect.md` stub. Flag for Friday architecture review.

## 5. Cleanup confirmation (Anti-Pattern #7)

- [x] No `*_v2.*`, `*_new.*`, `*_old.*`, `*.bak`, `test_scratch_*`, or `*_tmp.*` files in `src/` or `tests/` (verified via `find`).
- [x] No experimental/throwaway scripts left behind — every new file is a shipped module or its test.
- [x] New files this task are all canonical: `src/sentinel/tools/sanitize.py`, `src/sentinel/agent/{autonomy,orchestrator_planner,registry}.py`, `docs/adr/0004-agent-specs-registry-table.md`, and `tests/test_phase3_*.py`.
- [x] No secrets in code/config/HTML — `ATCUALITY_API_KEY` stays in `.env`; web surfaces show a set/not-set pill only.
- [ ] Branch deletion after merge — **N/A**, repo is not under git this session.

## 6. Tech debt logged (explicit follow-ups with triggers)

| # | Item | Trigger to resolve | Status |
|---|---|---|---|
| TD-1 | **Created-capability execution** — wire `build_from_spec` into `_execute_plan`/`run_dag` (replace the pure `SKILL_SPECS.get` staffing at dag.py:315). | Before the first demo that lets the planner invent a capability in `autonomous` mode. | **CLOSED 2026-06-08** |
| TD-2 | **Persona render into `run_plan`** — apply the Step-11 persona pass to the orchestrated Result so AC-8/AC-17 hold end-to-end. | Before any pilot persona other than the default is offered. | **CLOSED 2026-06-08** |
| TD-3 | **`model_grade` on sampled-production path (§10.4)** + versioned per-domain golden eval sets (AC-19/AC-20). | Before claiming an eval/quality SLA to the pilot user. | **CODE CLOSED 2026-06-08**; residual: seed golden eval-set files per domain (AC-20 data, mechanism wired) |
| TD-4 | **Two new web routes call the live planner** and are only wired/guard-tested, not hermetically unit-tested end-to-end. | When the orchestrator UI moves from demo to pilot traffic. | **CLOSED 2026-06-08** |

### 6.1 Debt-closure addendum (2026-06-08, post-reflect)

Closed TD-1/2/3/4 in a follow-up pass; suite **400 → 410** (+10), zero regression. Also fixed the
memory-spine `task_state_change` schema (it rejected the `SENTINEL-` task-ID prefix) and emitted the
SENTINEL-012 closure event. Notes:

- **TD-1** — `_execute_plan` now staffs a created capability from its registry spec via a new
  `_run_created_step` (build_from_spec → single-pass SSE reasoner). Seam test
  `tests/test_phase3_created_exec.py` (3) runs an autonomous plan *through* a created step and asserts
  it executes (+ a fail-soft guard when the spec is absent). This is the seam the reflect said no test
  crossed.
- **TD-2/TD-3** — new `run_plan` finalize pass (`_finalize_result`) attaches `Result.persona_rendered`
  (render-only, AC-17 invariance) and a sampled `Result.grade` to the *typed* primary artifact; both
  opt-in/additive (default persona + `grade=False` → byte-identical). Wired into the web run routes
  (`persona=task.persona`, `grade=_grade_sample()` behind `SENTINEL_GRADE_SAMPLE`, dark by default).
  `tests/test_phase3_finalize.py` (3). **Residual:** AC-20 golden eval-set *files* per domain are not
  seeded — the `load_eval_set` mechanism is wired; this is data-entry, not code.
- **TD-4** — `tests/test_phase3_routes.py` (4) exercise the GET-plan and POST-run-plan bodies
  hermetically (mocking planner/gate). **This surfaced a real bug:** the GET plan route passed
  `created_at=utcnow()` (a `datetime`) where `Task.created_at` is a string — the route would have
  500'd on first real use. Fixed (`utcnow().isoformat()`). Exactly the class of defect the
  "test the route body, not just its wiring" lesson predicted.

---

## Estimate actuals (BILTIQ-022 AC6)

`spec.md` carries **no `**Estimate:**` line** (the task predates the estimate-capture convention), so there is
no baseline band to compute variance against. Recorded for calibration: actual delivery was a single
multi-session chain, 281→400 tests (+119), 4 phases / 17 steps, all green. **Recommendation:** seed a
retroactive estimate band (wall_clock ≈ L, complexity ≈ XL given the 21 ACs + 2 ADRs) into
`estimates-history.jsonl` so future orchestrator-class tasks have a reference point.
