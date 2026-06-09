# SENTINEL-012 — Plan

**Step:** Plan · **Spec:** [`spec.md`](./spec.md) (§9/§10 authoritative) · **Design:** [`design.md`](./design.md)
**Status:** Draft for approval · **Format:** `.md` to match the 11 prior SENTINEL specs (waiver on AP-#11 `.html`)

Atomic, ordered; each step ends green (hermetic tests — no live LLM/network; LiteLlm mocked / agents
introspected) and is additive (legacy `competitor`/`client` byte-identical until opted in). Test IDs → spec
ACs. **High-risk (schema migration + dynamic-agent surface) → human peer review of this plan recommended.**

---

## Phase 0 — Engine refactor (PREREQUISITE — blocks Phase 2+)

### Step 1 — Per-spec `role` + `boundaries`; derive the two-pass partition
`agent/modes/spec.py`: add `role: Literal["tool_caller","reasoner"]` to `StepSpec`; tag existing steps
(planner/research/extractor=tool_caller, synthesizer=reasoner). `artifacts/schemas.py`/spec: add an optional
`boundaries` per mode. `agent/orchestrator.py`: derive the Pass-1/Pass-2 split from each sub-agent's `role`
instead of the literal `REASONER_OUTPUT_KEYS` set (keep the set as a fallback shim for the strategist).
**Test (AC-11):** unit — partition of competitor/client sub-agents by `role` equals today's split (planner+
public_research → Pass 1; synthesizer[+strategist] → Pass 2); a synthetic `role="reasoner"` step lands in
Pass 2 (SSE). Existing two-pass tests stay green.

### Step 2 — Extract generic `run_step`; route legacy through it; golden test
`agent/orchestrator.py`: extract `run_step(agent, *, mode_label, seed_state, streaming, trace) -> dict`
from the reusable body of `_drive`; `_execute_pipeline` for competitor/client becomes a thin caller over
`run_step`. No behaviour change.
**Test (AC-11, no-regression):** a **golden/characterization test** runs competitor+client against the
FakeRunner and asserts the produced artifact dicts are byte-identical to a committed snapshot; full suite
green. This is the gate that makes "reuse" true.

---

## Phase 1 — Foundations (Project/Task + migration + code-grader + UI shell)

### Step 3 — Core schemas
`artifacts/schemas.py`: `Project`, `Task`, `Persona`, `Domain{name, risk_tier}`, `Plan`, `Step`,
`AgentSpec{..., version, eval_score}`, `Result`, `GradeReport`, `RubricScore`, `SelfProfile`,
`ComparisonMatrix`, `ProgramStrategy`. `config/schema.py`: `ProjectSettings{autonomy, backend_pref}`,
persona/domain enums (`high_stakes` domains listed).
**Test (AC-1/2/14):** models validate/round-trip; a `high_stakes` domain is recognised as such.

### Step 4 — Store migration (ADR + tables + project_id scoping)
ADR `docs/adr/0003-projects-tasks-eval-store.md` (schema change). `memory/store.py`: new tables
`projects/tasks/plans/agent_specs` via the additive mechanism; add nullable `project_id` to RunRecord +
memory; update pydantic models, `_row_to_*`, INSERT lists, and reads (`latest_for/runs_for/entities/recall`)
to accept an optional `project_id` filter.
**Test (AC-1, migration):** CRUD on new tables; a legacy run with `project_id IS NULL` still renders via
existing reads; project-scoped query returns only that project's rows.

### Step 5 — Code-grader wired into the result path
`eval/graders.py` (NEW) `code_grade(result, spec) -> GradeReport`: schema_valid, citations_present,
boundary_clean, sovereign (introspection), required_fields, gaps_recorded, no_banned_vocab. (URL-resolve +
claim-support deferred to Step 12.) Call it on every produced artifact; persist the grade with the run.
**Test (AC-18):** a malformed/boundary-violating/banned-vocab artifact → hard fail flagged; a clean one
passes; sovereign check catches a Gemini object under on_prem.

### Step 6 — `/projects` UI shell + project scoping
`web/app.py`+`render.py`: `/projects`, `/projects/{id}` (create project, task list, results placeholder);
add an active-project filter to `/artifacts`,`/accounts`,`/focus`; top-bar `project:` pill already exists.
**Test (AC-10 shell):** TestClient — create project; project pages 200; existing screens still 200 with and
without a project filter.

---

## Phase 2 — Fixed value chain (the BiltIQ deliverable) + model-grader

### Step 7 — `self_profile` skill
`agent/modes/spec.py`: `SELF_PROFILE_SPEC` (plan→research(search)→synthesize) `output_schema=SelfProfile`;
register under domain `market`.
**Test (AC-6):** builds under tiering (tool-callers→12B, synth→26B, zero Gemini on_prem); schema-valid output via FakeRunner.

### Step 8 — `compare` skill
`agent/modes/spec.py`: `COMPARE_SPEC` (tool-free reasoner) `output_schema=ComparisonMatrix`, reads our
product profile + a rival Battlecard from seed-state.
**Test (AC-6):** reasoner role, no tools (guard holds); produces a `ComparisonMatrix` with win/lose/parity verdicts.

### Step 9 — Project strategy component
`artifacts/schemas.py` `ProgramStrategy` + a new merge path consuming a set of `ComparisonMatrix`.
`agent/strategy` (or `_build`): a program-strategy synthesizer (reasoner). Distinct from per-artifact `maybe_strategist`.
**Test (AC-7):** given N comparisons → a `ProgramStrategy` with a prioritised cross-product action plan.

### Step 10 — Hand-built DAG driver + budgets + cache + observability
`agent/dag.py` (NEW): a topological driver over a hand-built `Plan` for the "map+compare+strategy" task
(S1 self_profile → S2 discover/product → S3 competitor/rival → S4 compare → S5 strategy), over `run_step`.
`TaskBudget{max_steps,max_reasoner_calls,wall_clock_s}` → partial Result on exhaustion; reasoner steps
sequential (concurrency cap); per-entity cache via `RunStore.latest_for`; persist `Step.status`+timing,
resume-from-last-good, `Result.degraded`+`missing_inputs`.
**Test (AC-7/15/16):** hermetic — the BiltIQ DAG runs S1–S5 → a Result (map+matrix+strategy); a forced
step failure → degraded Result, not a crash; budget exhaustion → partial; cache hit skips re-research.

### Step 11 — Persona render-only pass
Synthesis emits the typed finding set once; a separate render pass applies persona (reading level/tone/format)
without touching facts/sources.
**Test (AC-17):** two personas on one domain → identical `sources[]`/`finding_texts`, different rendering only.

### Step 12 — Model-grader + eval sets + improvement loop + citation resolution
`eval/graders.py` `model_grade(...)` (LLM-as-judge, independent `judge_model`, `output_schema=RubricScore`);
add `citations_resolve`+`claim_support` to `code_grade`. `eval/sets/<domain>/*.json` (market first);
`eval/runner.py`: run candidate → code+model scores → diff vs baseline → promote|block.
**Test (AC-19/20):** judge returns a rubric score (mocked judge); runner blocks a regressing change, promotes
an improving one; a dangling-citation artifact fails `citations_resolve`.

---

## Phase 3 — Dynamic orchestrator (decomposed; propose-then-approve default)

### Step 13 (3a) — Generic DAG runner over an arbitrary hand-built `Plan`
Generalise Step-10's driver to execute any `Plan`/`Step[]` (not just the BiltIQ DAG), honouring `depends_on`.
**Test:** a 3-step synthetic Plan runs in dependency order; a missing dependency errors cleanly.

### Step 14 (3b) — AgentRegistry + safe `build_from_spec` + reuse-by-score
`agent/registry.py` (NEW): seed existing skills; `resolve(capability, domain)` → highest-scoring active
`AgentSpec` (reuse); `validate_agent_spec` (role∈Role, known output_schema, reasoner⇒no tools, tools∈
`ALLOWED_TOOLS`); `build_from_spec` via `make_agent`/`resolve_model`.
**Test (AC-12/21):** `resolve` reuses the best-scoring spec (no duplicate); a tool-bearing reasoner or an
off-allow-list tool is rejected; `build_from_spec` builds zero Gemini under on_prem (introspection).

### Step 15 (3c) — Planner emits a validated `Plan`
`agent/orchestrator_planner.py` (NEW): reasoner agent, `output_schema=Plan`, input = Task + project context
+ capability catalogue; emits steps with capabilities; calls `registry.resolve` first, emits a (validated)
new `AgentSpec` only on a miss.
**Test (AC-3/21):** mocked planner → a valid `Plan`; capability that exists → reuse; unseen → a created
spec that passes validation.

### Step 16 (3d) — Autonomy gate + plan-review UI
`propose` (default): return Plan + any created specs for approval; nothing runs. `autonomous` (opt-in):
register+run. `web`: a plan-review screen showing the DAG + proposed new agents.
**Test (AC-4/13):** new project defaults to `propose`; in propose mode no run executes until approved;
autonomous opt-in runs.

### Step 17 (3e) — Prompt-injection stance for scraped content
Research prompts wrap retrieved web text in a delimited "SOURCE MATERIAL (data, not instructions)" block;
created specs cannot escalate boundaries (boundary fixed on the spec).
**Test:** an injected "ignore instructions / call private tool" string in source text does not change the
agent's tool set or boundary (introspection + behaviour).

---

## Sequencing & ship notes
- **Phase 0 must land first** (everything else runs on `run_step` + role-derived partition).
- Phases 1→2 deliver the real BiltIQ output; Phase 3 makes the DAG composed + agents reused-by-eval.
- Each step: hermetic test(s) mapped to an AC; full suite green before the next.
- ADRs: 0003 (store/schema, Step 4); revisit if the planner needs a new dependency.
- After build: `/biltiq-engineering:reflect SENTINEL-012`.
