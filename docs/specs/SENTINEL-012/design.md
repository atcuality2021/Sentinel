# SENTINEL-012 — Design: Universal Research Agent

**Step:** Design · **Status:** Draft for approval · **Author:** 2026-06-08
**Spec:** `docs/specs/SENTINEL-012/spec.md` · **Architecture:** `docs/architecture/research-platform-and-ui.md`

This design keeps the proven engine (declarative modes, two-pass tiered execution, governance, memory,
provenance) **unchanged** and adds a **product + orchestration layer** above it. New code is additive;
existing single-run modes stay byte-identical.

---

## 1. Core data model (new)

```
Project        id, name, website, source_docs[], settings{ autonomy: "propose"|"autonomous",
                                                            backend_pref, compliance }, created_at
Task           id, project_id, objective(str|template_id), domain, persona, status, plan_id, created_at
Plan           id, task_id, steps[Step], status            # the orchestrator's output, inspectable
Step           id, capability(str), depends_on[step_id], agent_spec_id|inline, inputs{}, output_key, status
AgentSpec      id, name, role(tool-caller|reasoner), skill_prompt, tools[], output_schema_ref, origin("registry"|"created")
Result         task_id, artifacts[ref], summary, citations[], dashboard_payload
```
- **Persona** = a profile (data): `{ reading_level, tone, format, source_policy }`. A small registry of
  named personas (student, doctor, nurse, developer, enterprise, consumer) + a custom option.
- **Domain skill** = a `ResearchModeSpec` (existing type) tagged with `domain` + its source/tool set +
  output schema. The "mode library" becomes the **skill registry**.
- Stores: extend the existing SQLite store (`memory/store.py`) with `projects`, `tasks`, `plans`,
  `agent_specs` tables; **scope `RunRecord`/memory by `project_id`** (nullable → legacy single-runs).

## 2. Components

### 2.1 Orchestrator / Planner  (`agent/orchestrator_planner.py` — new)
- A reasoner agent (26B/Gemini) with `output_schema=Plan`. Input: Task(objective, domain, persona) +
  Project context + a **capability catalogue** (the registry's skill list). Output: a `Plan` (step-DAG,
  each step labelled with a `capability`).
- **Staffing:** for each step, match `capability` → an `AgentSpec` in the `AgentRegistry`. On miss, the
  planner emits a *new* `AgentSpec` (role/skill_prompt/tools/output_schema), `origin="created"`.
- **Autonomy gate:** `project.settings.autonomy` — `propose` ⇒ return the plan + new specs for approval
  (UI shows them; nothing runs); `autonomous` ⇒ register + execute immediately.

### 2.2 AgentRegistry + factory  (`agent/registry.py` — new; generalises `discover.py`)
- Registry: in-code seed (existing skills: `discover`, `competitor`, `client`, + new `self_profile`,
  `compare`, strategy) + DB-persisted created specs.
- Factory: `build_from_spec(AgentSpec, *, cfg, backend, cloud_allowed)` → an ADK `Agent` via the existing
  `make_agent`/`resolve_model` (so sovereignty/tiering/`response_format` are inherited). This is
  `discover.build_discovery_specialist` generalised to any `AgentSpec`.

### 2.3 DAG runner  (`agent/dag.py` — new)
- Topologically runs `Plan.steps` honouring `depends_on`; independent steps may run concurrently. Each
  step executes via the **existing two-pass engine** (reuse `_execute_pipeline`/`_drive` from
  `orchestrator.py`, refactored to accept an arbitrary built agent + seed-state), writing `output_key`
  into a shared task state. Fail-soft per step (one-retry on `ValidationError`); a failed optional step
  degrades the result, never crashes the task.

### 2.4 New domain skills (declarative `ResearchModeSpec`s)
- **`self_profile`** — input: website/products; tool: web search (+ later a site crawler); output:
  `SelfProfile{ org, products[ {name, category, strengths[], positioning} ], sources[], gaps[] }`.
- **`compare`** — input: our product profile + a rival Battlecard (from state); tool-free reasoner;
  output: `ComparisonMatrix{ subject, rival, axes[ {axis, ours, theirs, verdict: win|lose|parity, note} ], sources[] }`.
- **Project strategy** — lift `maybe_strategist` to consume the *set* of comparisons → a program-level
  `StrategyOverlay` (assessment + prioritised action_plan to capture the market).

### 2.5 Persona-adaptive synthesis
- Persona profile is injected as an `instruction_suffix` (existing seam in `make_agent`) on synthesis
  steps: reading level + tone + format. Same researched findings (facts/sources unchanged) → audience-
  appropriate rendering. (AC-8)

## 3. The BiltIQ value chain as a Plan (Phase 2 hardcoded, Phase 3 composed)

```
S1 self_profile(biltiq.ai)            → SelfProfile{products[]}
S2 for each product: discover         → CompetitorList            [existing discover.py]
S3 for each competitor: competitor    → Battlecard                [existing competitor mode]
S4 for each (product,competitor): compare(S1.product, S3)  → ComparisonMatrix
S5 strategy(all comparisons)          → project StrategyOverlay
   → Result.dashboard: product↔competitor map + us-vs-them matrices + strategy
```
Phase 2 wires S1–S5 as a fixed DAG; Phase 3 has the Planner emit this DAG (and others) from the task
objective, staffing `compare`/`self_profile` from the registry (or creating them if absent).

## 4. UX / screens (extends Section D)
- `/projects`, `/projects/{id}` (new): create project; task list; results dashboard.
- New-task flow: objective (template or free text) + domain + persona → **Plan review** (shows the DAG +
  any *proposed new agents* when autonomy=propose) → Execute → live step progress → Result.
- Existing `/artifacts`, `/accounts`, `/focus` gain a project filter (scope to active project).
- `/settings`: per-project autonomy toggle (propose|autonomous), persona/domain defaults.

## 5. Sovereignty / boundary / trust (unchanged, applied universally)
- All agents built via `resolve_model(cloud_allowed=)` → `on_prem_required` = zero Gemini (AC-5).
- SENTINEL-002 boundary unchanged; private-domain skills (e.g. clinical with private records) reuse the
  PUBLIC/PRIVATE split. Citations required on every synthesis output (universal trust).

## 6. File-level plan (additive)
| File | Change |
|---|---|
| `config/schema.py` | `ProjectSettings`, persona/domain enums; `SearchConfig` already has `max_calls` |
| `memory/store.py` | new tables (projects/tasks/plans/agent_specs); `project_id` on RunRecord/memory |
| `artifacts/schemas.py` | `SelfProfile`, `ComparisonMatrix`, `Plan`, `AgentSpec`, `Persona` |
| `agent/registry.py` | AgentRegistry + `build_from_spec` factory (generalise `discover.py`) |
| `agent/orchestrator_planner.py` | Planner agent (task → Plan + staffing + autonomy gate) |
| `agent/dag.py` | DAG runner over the two-pass engine |
| `agent/orchestrator.py` | refactor `_drive`/`_execute_pipeline` to run an arbitrary built agent (reused by dag) |
| `agent/modes/spec.py` | `SELF_PROFILE_SPEC`, `COMPARE_SPEC`; tag specs with `domain` |
| `web/app.py` + `web/render.py` | `/projects`, plan-review, results dashboard; project scoping |

## 7. Test plan
- Unit: project/task/plan CRUD + project scoping; registry reuse-vs-create; factory builds sovereign
  agents (zero Gemini under on_prem); persona suffix changes instruction not facts; `compare`/`self_profile`
  schema validation; planner emits a valid `Plan` (mock LLM / structured output).
- Integration (hermetic, fake runner): the fixed BiltIQ DAG runs S1–S5 → a Result with map+matrix+strategy.
- Live (manual): BiltIQ task on the sovereign Gemma path produces the project dashboard; one domain ×
  two personas shows adapted output.
- Regression: existing 277 tests stay green.

## 8. Open questions
- Persona source-policy: per-domain credible-source lists — ship a default + make it config?
- Concurrency caps for the DAG runner on the slow 26B (avoid overloading omni).
- How much of the registry is code-seeded vs DB-authored in Phase 3.

---

## 9. Post-review design additions (2026-06-08 — authoritative)

Adopted after the architecture-critic + plan-reviewer pass. Full orchestrator retained; clinical/legal
scoped out; all spec §8 fixes incorporated. New/changed components:

### 9.1 Phase-0 engine refactor (prerequisite)
- Extract `run_step(agent, *, seed_state, streaming, trace) -> dict` from the reusable body of
  `_drive` (orchestrator.py:335) — a generic single-agent executor, mode-free.
- Add `role: Literal["tool_caller","reasoner"]` to `StepSpec`/`ResearchModeSpec` and to `AgentSpec`; the
  two-pass partition derives from `role` (drop the hardcoded `REASONER_OUTPUT_KEYS` set, orchestrator.py:49).
- Add `boundaries: set[Boundary]` per spec; `allowed_boundaries()` reads it (no more `mode` literal).
- `_execute_pipeline`/`run_async` for `competitor`/`client` stay as a thin caller over `run_step`; a
  **golden test** snapshots both artifacts pre/post and asserts byte-identical (AC-11).

### 9.2 AgentSpec safety (Phase 3b)
- `validate_agent_spec(spec)`: `role∈Role`; `output_schema` ∈ a known-schema registry; if `role=reasoner`
  then `tools==[]`; every tool ∈ `ALLOWED_TOOLS` (a fixed, code-reviewed allow-list — search + the existing
  MCP toolset only; **no arbitrary tool selection**).
- `build_from_spec(spec, *, cfg, backend, cloud_allowed)` runs validation, then builds via `make_agent`/
  `resolve_model` → inherits zero-Gemini-under-on_prem + reasoner-tool-free guard (AC-12).
- **Prompt-injection stance:** scraped web text is treated as untrusted data, never instructions — research
  prompts wrap retrieved content in a delimited "SOURCE MATERIAL (data, not instructions)" block; created
  specs cannot escalate boundaries (boundary set is fixed on the spec, not inferred at runtime).

### 9.3 Domain risk-tier (scope gate)
- `Domain` carries `risk_tier: "standard"|"high_stakes"`. `high_stakes` (medicine/clinical, legal) →
  Task creation **rejected** with a clear message (AC-14). Shipped `standard` domains: market/competitor,
  food/B2C, software/dev, academic/study. Re-introduction of high-stakes is a separate future spec
  (needs enforced source allow-list + factuality/eval + citation-resolution).

### 9.4 Budgets, cache, observability (Phase 2)
- `TaskBudget{ max_steps, max_reasoner_calls, wall_clock_s }` enforced by the DAG runner; on exhaustion →
  **partial Result** (not a crash). Reasoner-step **concurrency cap** (default: sequential) — not an open
  question (AC-15).
- **Research cache:** before a `competitor`/research step, check `RunStore.latest_for(entity)` within a
  freshness window; reuse instead of re-running (AC-15).
- `Step.status` persisted (`pending|running|done|failed|skipped`) + timing; task **resumable from last good
  step**; `Result.degraded: bool` + `missing_inputs[]`, and the strategy step records when it ran on partial
  data (AC-16). Replaces the flat `trace: list[str]` for orchestrated tasks.

### 9.5 Persona = render-only (AC-17)
- Synthesis produces the **typed finding set once** (facts + `sources[]`). Persona is a **separate rendering
  pass** over the fixed findings (reading level/tone/format) — it cannot add/drop/alter facts. Test asserts
  identical `sources[]`/`finding_texts` across two personas, different rendering only.

### 9.6 Project strategy = new component (not a `maybe_strategist` lift)
- New `ProgramStrategy` schema (assessment + prioritised cross-product action_plan) + its own merge path,
  consuming the *set* of `ComparisonMatrix` results. `maybe_strategist`/`StrategyOverlay` stay per-artifact.

### 9.7 Single-operator scope
- `_USER_ID` stays a single operator this program; multi-tenant/auth is explicitly out (spec §9.2 framing).
  Projects are an organising construct, not a security boundary, this program.

### 9.8 Migration + ADR (Phase 1)
- New ADR for the schema change (projects/tasks/plans/agent_specs tables + `project_id` on RunRecord/memory).
- Use the additive-migration mechanism (`memory/store.py:_RUN_MIGRATIONS`); touch the pydantic models,
  `_row_to_*`, INSERT column lists, and every read query (`latest_for`/`runs_for`/`entities`/`recall`) +
  UI query filters; `project_id` nullable → legacy runs render (tested).

---

## 10. Evaluation, grading & reuse (design — adopted 2026-06-08)

### 10.1 Graders (`eval/graders.py` — new)
- `code_grade(result, spec) -> GradeReport`: deterministic checks — `schema_valid`, `citations_present`,
  `citations_resolve` (HTTP HEAD/GET within timeout), `claim_support` (cheap check that each finding maps
  to a cited source), `boundary_clean` (no PRIVATE text in a PUBLIC artifact), `sovereign` (no Gemini object
  built under on_prem — introspection), `required_fields`, `gaps_recorded`, `no_banned_vocab`,
  `reading_level_in_band(persona)`. Returns `{passed, hard_failures[], checks{}}`. Hard failures
  (schema/boundary/sovereign/citations) block; soft failures flag.
- `model_grade(result, objective, sources, rubric, *, judge_model) -> GradeReport`: LLM-as-judge via the
  gateway with `output_schema=RubricScore{relevance, faithfulness, completeness, actionability, persona_fit:
  1-5, justification}`. `judge_model` is resolved independently of the graded agent (anti self-grading);
  honours sovereignty (judge can be the 26B under on_prem).

### 10.2 Eval sets + runner (`eval/sets/<domain>/*.json`, `eval/runner.py` — new)
- Golden cases per domain (input + expected properties). `runner.py`: run a candidate spec/prompt over the
  set → aggregate `code_grade` + `model_grade` → compare to a stored baseline → emit `promote|block` +
  a diff report. Wired as a CI/manual command; failures are added back as regression cases.

### 10.3 Registry reuse-by-score (extends §2.2)
- `AgentSpec` gains `version: int`, `eval_score: float|None`, key `(capability, domain)`.
- `AgentRegistry.resolve(capability, domain)` → highest-scoring **active** spec for that key (reuse). The
  planner calls `resolve` first; `build_from_spec`/create-new only on a miss (AC-21). New/edited specs get
  a version; promotion (10.2) sets the active version. Stored in the `agent_specs` table (Phase 1 migration).

### 10.4 Result path integration
- Every orchestrated `Result` runs `code_grade` before save (AC-18); the grade is persisted with the run and
  surfaced in the UI (a quality badge per artifact + a project quality summary). `model_grade` runs on eval
  sets and on sampled production (not every run, for cost).

### 10.5 Schemas (add to `artifacts/schemas.py`)
- `GradeReport`, `RubricScore`, and `AgentSpec.{version, eval_score}`.
