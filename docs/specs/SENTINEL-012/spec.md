# SENTINEL-012 — Universal Research Agent: Projects, Tasks & Orchestrated Agent Teams

**Step:** Spec · **Status:** Revised after review (2026-06-08) — full orchestrator retained; clinical/legal
scoped out; all §8 fixes adopted (see §9, which is authoritative where it differs from §2/§4/§5) · **Author:** 2026-06-08
**Depends on:** SENTINEL-001 (`make_agent`/config), 002 (boundary invariant), 005
(`resolve_model(cloud_allowed=)` sovereignty seam), 008 (declarative `ResearchModeSpec` engine),
009 (strategist), 011 (Gemma-4 tiering, two-pass execution), discovery sub-agent (`agent/discover.py`)
**Blocks:** the product pivot from "competitor-intel tool" → a universal research platform
**Source:** `docs/architecture/research-platform-and-ui.md` (Sections A–G — the canonical architecture)

---

## 1. Context / problem

Sentinel today is a **specialised** competitor/account-intelligence tool: a unit of work is *one
target + one of two hardcoded modes* (`competitor`→Battlecard, `client`→AccountBrief). Two structural
limits block the real product:

**(a) The UX starts at the wrong place.** The first action is "New Run = pick a target + a mode." But a
real research job is a *project with an objective that fans out into many steps* — e.g. *"research my
website + products → find competitors per product → compare us vs them → produce a market-capture
strategy."* There is no `Project`, no `Task`/objective, and no way to express a multi-step research goal.

**(b) It only does two kinds of research, and only for one kind of user.** The vision is a **universal
research agent** — *any research, for anyone*: a K12 student on photosynthesis, a doctor on a drug
interaction, a nurse on a care protocol, a web developer choosing a library, a food/B2C brand sizing a
market, an enterprise analyst. Competitor intelligence is just the **first packaged domain**. Two
dimensions are missing from a unit of work: a **domain** (what to research → sources/tools + output
shape) and a **persona** (who it's for → reading level/tone/format + credible-source selection).

The engine is already general (declarative modes, on-demand agent factory, sovereign tiered execution,
citations, memory) — what's missing is the **orchestration + product layer** on top.

> **Not a solution restatement:** the ask is not "add more modes." It is "introduce Project/Task as the
> unit of work, and an Orchestrator that plans a task into a step-DAG and *staffs it from a registry —
> reusing an agent or creating a new specialist when a domain/step is unseen* — so one system researches
> anything for anyone, sovereign and cited."

## 2. Goal / non-goals

**Goal:**
1. **Project / Task model.** `Project` (durable context: name, website, source docs, settings) and
   `Task` (`objective` free-text or template + `domain` + `persona`). Runs/memory scope by `project_id`.
2. **Orchestrator/Planner.** Given a Task + Project context, produce a **Plan** = a step-DAG, each step
   annotated with the capability it needs; then **staff** each step from the `AgentRegistry` — *reuse an
   existing AgentSpec, or synthesise a new one* (role + skill/prompt + tools + output schema).
3. **Per-project autonomy.** A project setting controls the staffing gate: **propose-then-approve**
   (orchestrator drafts new AgentSpecs for human approval) **or autonomous** (creates + runs them) —
   so governed enterprise and fast individual use both fit.
4. **Domain + persona dimensions.** `domain` selects a research-skill (sources/tools + output schema);
   `persona` selects a profile (reading level, tone, format, credible-source policy). Both are
   composable data, not code.
5. **DAG execution on the existing engine.** A runner executes the staffed step-DAG over the SENTINEL-011
   two-pass tiered path (12B tools → 26B reason), inheriting governance, memory, provenance.
6. **Universal trust layer.** Every result is **cited**; sovereignty (`on_prem_required` ⇒ zero Gemini)
   and the SENTINEL-002 boundary apply across all domains.
7. **First end-to-end value chain.** Ship the "map products↔competitors → compare → strategy" task for a
   Project (BiltIQ) as the proving deliverable, using two **new domain skills** (`self_profile`,
   `compare`) + the existing discovery + competitor skills + a project-level strategy synthesizer.
8. **Ship incrementally, no regression.** Existing single-run modes + the 277-test baseline stay green;
   the platform is additive.

**Non-goals (this program):** a marketplace of third-party agents; fully self-improving agents that
rewrite their own prompts; real-time collaborative multi-user editing; building every domain skill (we
ship the orchestration + 2–3 domains and the pattern to add more); replacing the existing single-run UX
(it remains as the "quick run" path).

## 3. The universal model (what a unit of work becomes)

```
Project(context) ─▶ Task(objective + DOMAIN + persona)
   ─▶ Orchestrator: PLAN (step-DAG) + STAFF (reuse|create AgentSpec, per-project autonomy gate)
   ─▶ DAG runner on the two-pass sovereign engine
   ─▶ typed, CITED, persona-adapted Result  ─▶ memory + provenance + project dashboard
```

- **Domain** examples: market/competitor (shipped), food/nutrition, medicine/clinical, academic/study,
  software/dev, legal/patent, finance, travel. Each = sources/tools + output schema.
- **Persona** examples: K12 student, college student, doctor, nurse, developer, enterprise analyst,
  individual consumer. Each = reading level + tone + format + credible-source policy.

## 4. Acceptance criteria

- **AC-1** A `Project` can be created (name + website + settings incl. autonomy mode) and persisted;
  runs/memory created under it carry its `project_id`.
- **AC-2** A `Task` carries `objective`, `domain`, `persona`; a task template ("map+compare+strategy")
  exists and is selectable.
- **AC-3** The Orchestrator turns a Task into a Plan (ordered/DAG steps with capability annotations),
  inspectable before execution.
- **AC-4** For each step the Orchestrator either binds an existing `AgentSpec` from the registry or emits
  a new `AgentSpec`; in **propose** mode the new specs are surfaced for approval before any run; in
  **autonomous** mode they run without a gate. Mode is read from the project setting (AC-1).
- **AC-5** The staffed DAG executes on the existing two-pass engine; every produced artifact is schema-
  valid and **cited** (sources present); `on_prem_required` builds **zero Gemini objects** (introspection).
- **AC-6** Two new domain skills exist: `self_profile` (website/products → our profile + strengths) and
  `compare` (us vs a rival → `ComparisonMatrix`); plus a project-level strategy synthesis step.
- **AC-7** The BiltIQ "map products↔competitors → compare → strategy" task runs end-to-end under a
  Project and produces a project Result (product↔competitor map + us-vs-them matrix + strategy), all saved.
- **AC-8** A `persona` changes the *output* (reading level/format) without changing the researched facts
  (same findings, audience-adapted synthesis) — demonstrable on one domain across two personas.
- **AC-9** Existing single-run modes + full test baseline remain green; the platform is additive (dark/opt-in).
- **AC-10** UX: Project → Task → Orchestrate(plan+staff, with the autonomy gate) → Execute → Results,
  reachable in the web UI; the existing screens (Artifacts/Accounts/Focus) scope to the active project.

## 5. Phasing (each independently shippable)

- **Phase 1 — Foundations:** `Project` + `Task` models + stores (project-scoped runs/memory) + `/projects`
  UI shell. Makes the UX correct. (AC-1, AC-2, AC-10 shell)
- **Phase 2 — Fixed value chain:** `self_profile` + `compare` domain skills + project-strategy step,
  wired as a *hardcoded* DAG for the "map+compare+strategy" task. Delivers the real BiltIQ output.
  (AC-6, AC-7, AC-8)
- **Phase 3 — Orchestrator:** `Planner` + `AgentRegistry` + `AgentSpec` + generalised runtime factory +
  DAG runner, with the per-project autonomy gate — the DAG becomes *composed*, not hardcoded.
  (AC-3, AC-4, AC-5)

## 6. Risks

- **Orchestrator reliability** — a bad plan/agent spec wastes a long run. Mitigation: propose-then-approve
  default, typed plan schema, dry-run/inspect before execute.
- **26B structured-output flakiness** — occasional `ValidationError` (seen 2026-06-08). Mitigation:
  one-retry on validation failure; 12B-only fallback config.
- **Domain breadth** — infinite domains. Mitigation: ship the *pattern* + 2–3 domains; new domains are
  data (skill spec), not engine changes.
- **Cost/latency at project scale** — many steps × slow 26B. Mitigation: tier (cheap 12B for breadth,
  26B only for final reasoning), search-call budget, optional Gemini for speed (needs paid key).

## 7. References
- Architecture: `docs/architecture/research-platform-and-ui.md` (Sections A–G)
- Engine: `agent/modes/spec.py` (`ResearchModeSpec`), `agent/orchestrator.py` (two-pass), `agent/discover.py`
- Sovereignty/tiering: ADR `docs/adr/0001-a2a-coordinator-and-gemma4-tiering.md`; memory
  `sentinel-streaming-524`, `sentinel-vllm-server-gaps`, `sentinel-competitor-discovery`

---

## 8. Pre-plan review findings & required revisions (2026-06-08)

Two independent reviews (adversarial architecture-critic + BiltIQ plan-reviewer). Verdict: **needs
revision before plan.md**. They converge on the same blockers. Must-fix, grouped:

### 8.1 BLOCKER — "additive / byte-identical" is false; the engine refactor is the real prerequisite
`_execute_pipeline`/`_drive` are hardcoded to two modes: `Mode = Literal["competitor","client"]`
(schemas.py:160), `_OUTPUT_KEY` + `REASONER_OUTPUT_KEYS` (orchestrator.py:41,49), `allowed_boundaries()`
(:63), `_artifact_from_state` (:374), `_build_subagents` branch (:322), mode-coupled `maybe_strategist`
(_build.py:155). The DAG runner "reusing" this is a **rewrite of the most-tested, 524-sensitive path**,
not reuse. Required:
- Extract a **generic step-executor** from the reusable part of `_drive`; **freeze** the legacy
  `_execute_pipeline` (competitor/client unchanged) and route it through the shared executor.
- Make the **reasoner/tool-caller partition a per-spec attribute** (`ResearchModeSpec`/`AgentSpec` declares
  `role`), replacing the hardcoded `REASONER_OUTPUT_KEYS` literal — else generic reasoner steps route to
  the 12B non-streamed and re-trigger the 524 wall.
- Carry the **boundary set explicitly per spec/AgentSpec** (not derived from the `mode` literal).
- Add a **characterization/golden test** proving the two legacy modes are byte-identical — not just "tests green".
- This refactor is its own reviewed+tested deliverable and is a **prerequisite for Phase 2** (which needs the
  runner) — so Phase 2 is NOT independent of it. Re-sequence accordingly.

### 8.2 BLOCKER — safety for high-stakes domains + dynamically-created agents
- **High-stakes domains:** clinical/legal are headline examples but there is no factuality/eval/citation-
  verification story (`Source` is an LLM-written label+optional URL; nothing resolves or claim-checks it).
  Add a **domain risk-tier**: clinical/legal explicitly **scoped out or hard-gated** (human-in-loop +
  "unverified, not professional advice" interstitial); an **enforced** per-domain credible-source allow-list;
  a per-shipped-domain **eval set with a pass bar**; a citation-resolution check (URL reachable + claim-support).
- **Created agents:** in `autonomous` mode an LLM-emitted `AgentSpec` (role/**tools**/prompt/schema) runs with
  no gate; scraped web content feeds the reasoner (**prompt-injection** vector, unaddressed). Required:
  created specs choose tools only from a **fixed code-reviewed allow-list** (no arbitrary tools);
  **propose-then-approve is the default/only mode** for now; every `AgentSpec` is **validated before build**
  (role∈Role, reasoners carry no tools, output_schema is a known type) and `build_from_spec` is proven to
  build **zero Gemini under on_prem_required**; define a prompt-injection stance for scraped content.

### 8.3 HIGH — scope/cost/observability gaps to add as ACs
- **Cost/latency budgets:** a project task fans out to 15+ slow 26B runs with no ceiling/cache. Add ACs:
  max steps/task, max 26B-calls/task, wall-clock ceiling with **partial-result return**, **reasoner-step
  concurrency cap** (not an "open question"), and a **per-entity research cache** (reuse `RunStore.latest_for`).
- **Partial-failure + observability:** make `Step.status` load-bearing — persisted per-step state,
  **resume-from-step**, and **degraded/missing-input flags** carried into downstream synthesis (so a strategy
  built on 80% of comparisons is marked, not silently confident).
- **Persona facts-invariance (AC-8):** an instruction-suffix cannot *guarantee* "facts unchanged". Either
  architect it as **synthesize-findings-once → persona controls a rendering pass only** (assert same
  `sources[]`/`finding_texts`, different format), or drop the guarantee.

### 8.4 MEDIUM/process
- **Decompose Phase 3** into atomic sub-slices: (3a) generic step-executor + golden legacy test; (3b) DAG
  runner over a **hand-built** Plan (no LLM); (3c) AgentRegistry + `build_from_spec` (deterministic
  reuse-or-create); (3d) Planner LLM emitting a Plan; (3e) autonomy gate.
- **Capability vocabulary:** define a **closed capability namespace** = `ResearchModeSpec.name`/`domain`;
  reuse-vs-create is a deterministic lookup, not fuzzy matching.
- **Migration + ADR:** new tables (projects/tasks/plans/agent_specs) + `project_id` on RunRecord/memory is a
  schema change → **requires an ADR + explicit column-by-column migration + backfill/rollback + legacy
  (project_id NULL) render test**. The store has an additive-migration mechanism (`_RUN_MIGRATIONS`) to use.
- **Multi-user/auth/retention:** `_USER_ID` is a hardcoded singleton. Either **scope to single-operator
  explicitly** (drop multi-tenant framing) or add an auth/tenancy section — don't imply enterprise tenancy
  while building single-operator.
- **`maybe_strategist` "lift" is understated:** project-level strategy is a **new schema + new merge path**,
  not a lift. Name it as a new component.
- **Artifact format (#11):** BiltIQ rule expects `docs/specs/**` as `.html`; these are `.md`. Resolve
  (convert or explicit waiver) before plan.md is born non-compliant.
- **Test-baseline number:** pin via `pytest --collect-only` before making it an AC (don't hardcode 277).
- **High-risk → human peer review** of plan.md is recommended (schema migration + dynamic-agent surface).

### 8.5 STRATEGIC RECOMMENDATION (both reviewers, given the 2026-06-11 deadline)
The Planner + AgentRegistry + dynamic-agent-creation is **speculative generality**: the only committed
value is a **fixed** DAG (the BiltIQ chain). Recommended path for the deadline: **build Phases 1–2 with a
"TaskTemplate" model — named, hand-written fixed DAGs of existing+new modes, run by a small topological
driver over the (8.1-refactored) two-pass engine.** "Add a domain" = a code-reviewed new template + mode
spec (the `ResearchModeSpec` seam already proves this). Defer the LLM-Planner + dynamic agent synthesis
(Phase 3d/3e) to post-deadline. Gives up: on-the-fly agents for *unseen* domains (unbuilt, unsafe, uncommitted).
Gains: no LLM-plans-a-DAG reliability risk, no dynamic-tool security surface, a hittable deadline.

---

## 9. Adopted revisions (post-review decisions — AUTHORITATIVE)

Decisions taken 2026-06-08 after the two reviews. Where this section differs from §2/§4/§5, **this wins**.

### 9.1 Direction: full dynamic orchestrator RETAINED, with all §8 fixes
We keep the Planner + AgentRegistry + on-the-fly agent creation as the target (not the templates-only
simplification) — **but every §8 blocker/fix is mandatory**, especially the engine refactor (8.1) and the
created-agent safety bounds (8.2). The "additive/byte-identical" framing is dropped; the engine refactor
is an explicit prerequisite, not reuse.

### 9.2 Scope: high-stakes domains scoped OUT (added to Non-goals)
Medicine/clinical and legal are **out of scope for this program** until there is an enforced per-domain
credible-source allow-list + a factuality/eval harness + citation-resolution. Shipped domains:
**market/competitor (seed), food/B2C, software/dev, academic/study.** A `domain.risk_tier`
(`standard` | `high_stakes`) field exists; `high_stakes` domains are **rejected at task creation** with a
clear message (not silently run). Re-introduced only via a future spec that adds the safety harness.

### 9.3 Revised phasing (authoritative — supersedes §5)
- **Phase 0 — Engine refactor (prerequisite, blocks Phase 2+).** Extract a generic step-executor from
  `_drive`; replace `REASONER_OUTPUT_KEYS` literal with a per-spec `role` (reasoner|tool_caller) so the
  two-pass partition is derived, not hardcoded; carry the boundary set per spec; **freeze** legacy
  `_execute_pipeline` and route it through the shared executor; **golden/characterization test** proving
  `competitor`/`client` output is byte-identical. (resolves 8.1)
- **Phase 1 — Foundations.** `Project` + `Task(objective, domain, persona)` models + stores; **ADR + explicit
  column-by-column migration** for `project_id` on RunRecord/memory + four new tables, with legacy
  (project_id NULL) render test; `/projects` UI shell; single-operator scoping made explicit (no multi-tenant
  framing this program). (resolves 8.4 migration + multi-user)
- **Phase 2 — Fixed value chain.** `self_profile` + `compare` skills + a **new project-strategy schema +
  merge path** (not a "lift" of `maybe_strategist`), wired as a hand-built DAG over the Phase-0 executor →
  the BiltIQ deliverable. Adds **cost budgets + per-entity research cache** and **per-step status +
  resume + degraded-input flags**. Persona = **render-only pass over a fixed finding set** (facts invariant).
  (resolves 8.3)
- **Phase 3 — Dynamic orchestrator (decomposed):** (3a) DAG runner over a hand-built `Plan` (no LLM);
  (3b) `AgentRegistry` + `build_from_spec` (deterministic reuse-or-create, validated, zero-Gemini-under-
  on_prem, reasoner-tool-free, **fixed tool allow-list**); (3c) Planner LLM emitting a validated `Plan`
  (structured output); (3d) autonomy gate (**propose-then-approve is default; autonomous is opt-in per
  project**); (3e) prompt-injection stance for scraped content fed to reasoners. (resolves 8.2 + 8.4 decomposition)

### 9.4 Added acceptance criteria (binary)
- **AC-11 (refactor no-regression):** a golden test asserts `competitor`+`client` artifacts are byte-identical
  pre/post Phase 0; reasoner steps (any spec with `role=reasoner`) run SSE on the 26B (no 524 regression).
- **AC-12 (created-agent safety):** `build_from_spec` rejects a tool-bearing reasoner and any tool not on the
  fixed allow-list; builds **zero Gemini objects** under `on_prem_required` (introspection); every `AgentSpec`
  validated (role∈Role, known output_schema) before build.
- **AC-13 (autonomy default):** new projects default to `propose-then-approve`; `autonomous` is explicit opt-in.
- **AC-14 (high-stakes gate):** creating a Task in a `high_stakes` domain is rejected with a clear message.
- **AC-15 (budgets/cache):** a task enforces max-steps, max-26B-calls, and a wall-clock ceiling with
  partial-result return; a per-entity cache (via `RunStore.latest_for`) skips re-research within a freshness window.
- **AC-16 (observability):** every `Step` persists status + timing; a task is resumable from the last good
  step; a Result flags any degraded/missing inputs and downstream synthesis records that it ran on partial data.
- **AC-17 (persona invariance):** across two personas on one domain, `sources[]`/`finding_texts` are identical;
  only rendering (reading level/format) differs.

### 9.5 Process
- Resolve `docs/specs/**` artifact format (#11): convert to `.html` or record an explicit waiver before plan.md.
- Pin the real green baseline via `pytest --collect-only` before it becomes an AC (don't hardcode 277).
- New tables + `project_id` ⇒ **ADR required**; high-risk (schema migration + dynamic-agent surface) ⇒
  **human peer review of plan.md** regardless of verdict.
- `design.md` to be updated with: the Phase-0 generic step-executor, AgentSpec validation + tool allow-list +
  injection stance, budgets/cache, observability/resume, persona render-only pass, project-strategy schema.

---

## 10. Evaluation, agent reuse & continuous improvement (adopted 2026-06-08)

User requirement: **reuse existing agents for similar tasks, and keep improving them via proper eval —
model-based grading + code-based grading + prompt engineering.** This makes quality measurable and
improvement gated by evidence, not vibes. Adopted into scope.

### 10.1 Two graders (every result is graded)
- **Code-based grading (deterministic, fast, runs on every result + in CI):** schema-valid; **citations
  present and resolvable** (URL reachable) + claim-support check; **boundary-clean** (no PRIVATE in a
  public artifact); **sovereignty** (zero Gemini under `on_prem_required`); required-field coverage; gaps
  recorded not dropped; banned-vocabulary absent; persona reading-level within target band. Produces a
  pass/fail + per-check report. A failing hard-check (schema/boundary/sovereignty) blocks the result.
- **Model-based grading (LLM-as-judge, on eval sets + sampled production):** a rubric scores 1–5 with
  justification on: relevance to objective, **faithfulness to cited sources** (no unsupported claims),
  completeness, actionability, persona-fit. Judge runs on a **separate/strong model** (guard against an
  agent grading itself); structured output. Aggregated to a domain score with a pass bar.

### 10.2 Eval sets
- A small, versioned **golden eval set per shipped domain** (`eval/sets/<domain>/*.json`): curated inputs
  + expected properties / reference points. Lives in-repo; grows as failures are found (failures become
  regression cases).

### 10.3 The improvement loop (prompt engineering, gated)
- Change a prompt/agent → run it over the domain eval set → compute **code-grade + model-grade** →
  **diff vs the current baseline** → promote the new version **only if it is non-regressing and improved**.
  Prompt iterations are evidence-gated; this is a CI step, not manual judgement.

### 10.4 Agent reuse (no duplicate spawning)
- The `AgentRegistry` keys an `AgentSpec` by **(capability, domain)**; a similar task **reuses the existing
  best-scoring spec** (and its tuned prompt) — create-new only on a genuine miss. Each `AgentSpec` carries a
  **version + latest eval score**; `registry.resolve(capability, domain)` returns the **highest-scoring
  active version**. Reuse is the default path; dynamic creation is the exception (ties to §9.1/§9.4 safety).

### 10.5 Added acceptance criteria
- **AC-18 (code-grade gate):** every produced result runs the code-grader; hard-check failures
  (schema/boundary/sovereignty/missing-citation) are blocked or flagged, never silently shipped.
- **AC-19 (model-grade rubric):** a model-grader scores outputs on the rubric over a domain eval set; a
  documented pass bar exists per shipped domain; the judge model is independent of the graded agent.
- **AC-20 (eval set + regression):** each shipped domain has a versioned golden eval set; a prompt/agent
  change is promoted only if eval is non-regressing + improved (CI-checkable).
- **AC-21 (reuse-on-similarity):** for a capability already in the registry, the orchestrator **reuses**
  the best-scoring existing `AgentSpec` rather than creating a duplicate; create-new fires only on a miss.

### 10.6 Phasing fit
- Phase 1: code-grader skeleton (schema/boundary/sovereignty/citation-present) wired into the result path.
- Phase 2: model-grader + first domain eval sets + the improvement-loop CI step; citation-resolution check.
- Phase 3b: registry stores version + eval score; `resolve()` reuse-by-score; create-new only on miss.
