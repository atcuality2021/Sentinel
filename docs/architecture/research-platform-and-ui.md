# Sentinel — Research Platform & UI (architecture + scope)

> **Framing (read first, supersedes any narrower wording below):** Sentinel is a **universal research
> agent** — domain- and audience-agnostic. It can research *anything* for *anyone*. Competitor/market
> intelligence is merely the **first packaged domain**, not the product. See **Section G**.

**Status:** living doc. Captures (A) what Sentinel is today, (B) how the agent engine works, (C) the
general "research-anything" vision + extensibility model, (D) a screen-by-screen UI reference, and
(E) the scope/task backlog from specialised → general platform. Written 2026-06-08.

---

## A. What Sentinel is today (reality)

A **sovereign research agent** specialised for **competitive & account intelligence**. It is NOT yet a
general "research anything" platform — it does exactly two research types ("modes") plus one discovery
sub-agent:

| Mode (research type) | Input | Output artifact |
|---|---|---|
| `competitor` | a competitor name | **Battlecard** (positioning, strengths, weaknesses, pricing signals, recent developments, how-to-win, sources, gaps) |
| `client` | an account name | **Account Brief** (public signal, private signal, merged insights, recommended actions, sources, gaps) |
| `discover` (sub-agent, 2026-06-08) | one of OUR products + description | **CompetitorList** (≥3 named rivals) — breadth step that feeds `competitor` |

A unit of work today = **one target + one mode** (a "run"). There is no multi-target "Project" object yet.

---

## B. How the agent engine works

Every mode runs the same generic pipeline (the engine is mode-agnostic):

```
target ─▶ 1. PLAN        decompose the question into a research plan
         2. RESEARCH     agents call TOOLS: public web search and/or private MCP connectors
         3. [EXTRACT]    (two-tier, optional) distil raw sources into typed notes
         4. SYNTHESIZE   reason → a structured, every-fact-cited artifact (output_schema)
         └─▶ WRITE (markdown/gdoc/crm) + REMEMBER (entity memory) + SCORE (priority)
```

Key properties (all already built):
- **A research type is DATA, not code.** Each mode is a `ResearchModeSpec` = ordered steps + an
  `output_schema`. `COMPETITOR_SPEC` / `CLIENT_SPEC` live in `agent/modes/spec.py`. The design rule:
  *"adding a mode is a new ResearchModeSpec, not an edit to the engine."* → this is the extensibility seam.
- **Two-pass tiered execution (sovereign path):** Pass 1 = tool-callers on the fast gemma-4-12B
  (non-streamed); Pass 2 = the tool-free reasoner on gemma-4-26B (SSE-streamed, clears the Cloudflare
  524 wall). vLLM structured agents send `response_format: json_schema` so the 26B guided-decodes valid
  JSON. See `adr/0001-...` and memory `sentinel-streaming-524` / `sentinel-vllm-server-gaps`.
- **Governance / sovereignty:** every agent built via `resolve_model(cloud_allowed=)`; `on_prem_required`
  constructs **zero Gemini objects** (provable by introspection). Pluggable search (gemini/duckduckgo/brave/serpapi).
- **Boundary invariant (SENTINEL-002):** a `competitor` run can only ever read/write PUBLIC; private
  data structurally cannot leak into a public artifact.
- **Memory + priority:** each run accumulates boundary-tagged findings per entity; a deterministic
  PriorityScore ranks entities (tier hot/warm/cool).
- **On-demand sub-agent factory:** `agent/discover.py` builds a per-product specialist at runtime — the
  pattern for "create a sub-agent on the go".

---

## C. The general "research anything" vision + extensibility

Target vision (user's words): *create a Project → give company / website / any task → the agent picks the
right research → produces results.* Research could be anything: product-launch, patent search, design
research, pricing research, medicine research, etc.

**The architecture is the skeleton of that platform; today only two "muscles" (modes) are attached.**
Each new research type = a new mode = (steps + output schema + prompts + optional domain tool). Examples:

| Research type | New mode = | Likely extra tool |
|---|---|---|
| Pricing research | `pricing` spec + `PricingReport` schema | web search (have it) |
| Patent search | `patent` spec + `PatentReport` schema | patent-DB tool |
| Product-launch research | `launch` spec + `LaunchReport` schema | web search |
| Medicine research | `medicine` spec + `MedicineReport` schema | drug/clinical-DB tool |

**Gap between vision and today:**

| Vision | Today | Work needed |
|---|---|---|
| A **Project** (company/website/brief) fanning out into many tasks | only single per-target "runs" | a Project object → tasks → runs (+ a Project UI) |
| **Research anything** | only `competitor` + `client` | a **library of modes** (one spec+schema per type) |
| Input = "a website or any task" | input = a target *name* + chosen mode | a **router/intake agent**: read brief → pick mode(s) |
| Domain sources (patent/drug DBs) | web search + private MCP | per-domain tools wired into modes |

---

## D. Screen-by-screen UI reference (`sentinel-web`, FastAPI)

The UI is the visibility layer over the same stores (RunStore / MemoryStore / PriorityStore in
`SENTINEL_DATA_DIR`) and config (`sentinel.config.yaml`). Canonical instance: `http://localhost:8080`.

**Left-nav information architecture** (mirrors the Attack-Loop lifecycle):
- **Build** → Dashboard, Agents, New Run
- **Scale** → Accounts, Artifacts
- **Govern** → Backends, Settings
- **Optimize** → Focus

Top bar carries the active `project: <name>` pill, the active `Backend: <vllm|gemini>` pill, and a
global **New Run** button.

| Route | Screen | What it shows / does | Data source |
|---|---|---|---|
| `/` | **Dashboard** | At-a-glance: *Signal provenance* (public vs private donut), *Runs by mode* (competitor vs client bar), *Backend usage* (Gemini vs Gemma donut), *Top to focus on* (top priority entities), *Recent runs* | RunStore + PriorityStore |
| `/focus` | **Focus** | Full ranked list of every entity by deterministic PriorityScore + tier (hot/warm/cool) — the "what to work on next" list | PriorityStore |
| `/new` | **New Run** | The "create a research" form: target name, mode (competitor/client), optional vertical/industry, backend. Submits → `/run` | — (writes a run) |
| `/agents` | **Agents** | The pipeline flow-graph per mode (Competitor Intelligence, Account Intelligence) — visualises the sub-agent topology (planner → research → synthesizer) | static topology |
| `/artifacts` | **Artifacts** | Every produced artifact: target, kind (Battlecard/Brief), public/private finding counts, backend, saved-to file path, timestamp | RunStore |
| `/accounts` | **Accounts** | Entity memory index — every researched target, with modes, run count, accumulated public/private findings, last-run time | RunStore.entities() |
| `/accounts/{entity}` | **Account detail** | One entity: run timeline (each run's backend/findings/gaps/artifact), public signal, private signal, cumulative provenance, purge ("danger zone") | RunStore + MemoryStore |
| `/backends` | **Backends** | Live status of Cloud·Gemini, On-prem·Gemma, and the Private boundary (Workspace MCP) connection | config + probes |
| `/settings` | **Settings** | Edit everything (persisted to `sentinel.config.yaml`): Backends, Models·Gemma-4 role tiering, Coordinator·A2A, Governance·sovereignty, Public search provider, Strategy, Generation defaults, Memory, per-agent (competitor/client), Prompts | config store |
| `/healthz` | health | `ok` | — |

---

## E. Scope & task backlog (specialised → general platform)

Legend: ✅ done · 🔶 partial · ⬜ not started.

**Engine / agents**
- ✅ Generic mode engine (declarative `ResearchModeSpec`), two modes (competitor, client)
- ✅ Two-pass tiered sovereign execution (12B tools → 26B reason) + `response_format` guided JSON
- ✅ Competitor-discovery sub-agent + on-demand factory
- ✅ Search call-budget (`search.max_calls`) to bound over-searching
- 🔶 Tiered 26B reliability — occasional `ValidationError`; add **one-retry on validation failure**
- ⬜ **Mode library**: add new research types (pricing, patent, product-launch, medicine, design…) — each = spec + schema + prompts (+ domain tool)
- ⬜ **Router/intake agent**: accept a website URL / free-text brief → choose mode(s) to run
- ⬜ **Per-domain tools**: patent-DB, clinical/drug-DB, pricing-page scraper, etc.

**Product / UX**
- ⬜ **Project abstraction**: a Project (company + website + brief) → fans out into many research tasks → combined results dashboard
- ⬜ `/new` upgrade: accept a website/brief, not just a target name; let user pick research type(s) from the mode library
- ⬜ Project results view (group runs by project, not just by entity)
- 🔶 Backend comparison surfacing — runs stack under an entity; add an explicit side-by-side compare view

**Ops / infra (mostly owner)**
- ✅ Sovereign Gemma 12B/26B tiering verified; web UI consolidated on :8080
- ⬜ Paid Gemini key (current `.env` key is free-tier, 20/day) to enable the Gemini comparison column
- ⬜ Cloud Run deploy + demo (pre-existing program step)

**Recommended build order:** (1) one new mode end-to-end (e.g. pricing) to prove "research anything";
(2) router/intake agent; (3) Project abstraction + UI. Each is an independent, shippable increment.

---

## F. The correct product: Project → Task → Orchestrated agent team

### F.1 The real job (worked example: BiltIQ market capture)
> Research our website + products → map each product/service to its competitors → extract strengths
> (theirs and ours) → compare us vs them → synthesize a market-capture strategy.

This is a **value chain**, not a single run:

```
1. PROFILE SELF      biltiq.ai → our products + each product's strengths        [NEW mode: self/company profile]
2. DISCOVER          per product → ≥3 competitors                                [HAVE: discover.py]
3. PROFILE RIVALS    per competitor → battlecard (strengths/weaknesses)          [HAVE: competitor mode]
4. COMPARE           us vs each rival → comparison matrix (where we win/lose)     [NEW mode: compare → ComparisonMatrix]
5. STRATEGISE        synthesize a market-capture strategy across all of it       [HAVE-ish: strategist, lift to program level]
```

So ~2 new modes (self-profile, compare) + a program-level strategy synthesizer, on top of what exists.

### F.2 The correct UX (today's is backwards — it starts at a single "run")
The right flow is **Project → Task → Orchestrate → Execute → Results**:

1. **Create Project** — name + website URL + (optional) our-product list / docs. This is the durable
   context every task inherits. (NEW object: `Project`.)
2. **Define a Task / Objective** — pick a template ("map products↔competitors + strategy") or describe
   it in free text. (NEW object: `Task`.)
3. **Orchestrate (plan & staff)** — a **Planner/Orchestrator agent** decomposes the task into a step DAG,
   and for each step **checks the agent registry**: *is an existing agent enough, or do we need a new
   one?* Gaps → it proposes a **new agent spec** (name, role, skill/prompt, tools, output schema) for
   approval; the **agent factory** builds + registers it at runtime (the "create a sub-agent on the go"
   pattern, generalised from `discover.py`). Output: an approved Plan + staffed team. (NEW: `Planner`,
   `AgentRegistry`, `AgentSpec`, generalised factory.)
4. **Execute** — run the DAG on the existing two-pass tiered engine (12B tools → 26B reason), governance
   + memory + provenance inherited. Live per-step progress. (HAVE: engine; NEW: DAG runner over steps.)
5. **Results** — a **Project dashboard**: product↔competitor map, an us-vs-them strengths matrix, and the
   strategy — all cited, all saved. (NEW: project-scoped results view; artifacts/accounts already exist.)

### F.3 What an "agent" is made of (so the orchestrator can reason about staffing)
An `AgentSpec` = **role** (tool-caller vs reasoner tier) + **skill/prompt** (instruction template) +
**tools** (search / MCP / domain) + **output_schema** (the typed result). This is exactly what
`make_agent` + `ResearchModeSpec` already encode — the orchestrator just needs to (a) read a registry of
these and (b) synthesise a new one when no existing spec covers a step. "Skills + prompts do the work" =
the AgentSpec's prompt/tools; reuse vs create-new is a registry lookup.

### F.4 New abstractions vs what exists
| New | Reuses |
|---|---|
| `Project` (company/website/brief) | RunStore/MemoryStore (scope by project_id) |
| `Task`/`Objective` + templates | — |
| `Planner`/Orchestrator agent (task → step DAG) | LLM + structured output (response_format) |
| `AgentRegistry` + `AgentSpec` + generalised agent factory | `make_agent`, `discover.py` factory pattern |
| DAG runner (dependencies between steps) | two-pass tiered engine, governance, memory |
| Modes: `self_profile`, `compare` | declarative `ResearchModeSpec` engine |
| Project results dashboard | `/artifacts`, `/accounts`, `/focus` |

### F.5 Scope/task backlog for the proper product (⬜ unless noted)
- ⬜ `Project` model + store (project_id scoping on runs/memory) + `/projects`, `/projects/{id}` UI
- ⬜ `Task`/objective model + task templates (incl. the "map+compare+strategy" template above)
- ⬜ `self_profile` mode (website/products → our profile + strengths) + schema
- ⬜ `compare` mode (`ComparisonMatrix`: feature/strength/pricing axes, us vs rival, win/lose/parity)
- ⬜ Program-level strategy synthesizer (lift `strategist` from per-artifact to whole-project)
- ⬜ `Planner`/Orchestrator agent: task → step DAG + capability annotations
- ⬜ `AgentRegistry` + `AgentSpec` + generalised runtime agent factory (reuse-or-create decision)
- ⬜ DAG runner with inter-step dependencies (over the existing two-pass engine)
- ⬜ Project results dashboard (product↔competitor map, us-vs-them matrix, strategy)
- 🔶 Reliability: one-retry on 26B `ValidationError`; paid Gemini key for the cloud comparison column

**Build order:** (1) `Project`+`Task` models + UI shell; (2) the "map+compare+strategy" task as a fixed
DAG (prove the value chain end-to-end with `self_profile`+`compare`+strategy modes, reusing discovery
+ competitor); (3) generalise to the `Planner`+`AgentRegistry` so the DAG is composed, not hardcoded —
this is where "orchestrator decides if existing agents suffice or creates new ones" becomes real.

---

## G. The real product: a Universal Research Agent (any research, any user)

Competitor/market intelligence is the **first domain**, not the product. Sentinel is a domain- and
audience-agnostic research agent: give it an objective and who it's for, and it researches, reasons,
and returns a **typed, cited** answer — sovereign and on-prem when required.

### G.1 Two dimensions every Task carries
- **Domain** (*what* to research) → selects sources/tools + output schema. e.g. food/nutrition,
  medicine/clinical, academic/study, software/dev, legal/patent, market/competitor, finance, travel…
- **Persona / audience** (*who* it's for) → selects reading level, depth, tone, format, and which
  sources count as credible. e.g. K12 student, college student, doctor, nurse, web developer,
  enterprise analyst, individual consumer. Serves enterprise **and** individuals.

### G.2 The universal core (domain-independent)
```
Project context ─▶ Task(objective + DOMAIN + PERSONA)
   ─▶ Planner/Orchestrator: plan a step-DAG
   ─▶ staff from AgentRegistry (reuse a skill, or CREATE a specialist for a new domain)
   ─▶ execute on the tiered sovereign engine (12B tools → 26B reason)
   ─▶ typed, CITED result adapted to the persona  ─▶ memory + provenance
```
Why it generalises cleanly:
- A **research skill** = objective template + tools + output schema + tone — identical *shape* in every
  domain (the `ResearchModeSpec` already proves this; competitor/client are just two instances).
- The orchestrator **never hardcodes a domain** — it reads the registry and **creates an agent on the
  fly** for an unseen domain (the `discover.py` factory, generalised).
- **Citations/provenance + sovereignty are universal trust requirements** — a nurse, a student, and an
  enterprise all need sourced answers; a hospital needs it on-prem. Already core to the engine.

### G.3 Examples (domain × persona → output)
| User / persona | Domain objective | Output (persona-adapted, cited) |
|---|---|---|
| K12 student | "explain photosynthesis" | study guide + quiz, simple reading level |
| College student | "literature review on X" | structured summary + sources |
| Doctor | "interaction of drug X + Y" | clinical brief, label/PubMed sources, precise |
| Nurse | "post-op care for procedure Z" | checklist/protocol, plain clinical language |
| Web developer | "best auth library for stack X" | comparison + code snippets, dev-doc sources |
| Food / B2C brand | "gluten-free snack market, India" | market + product landscape |
| Enterprise | "competitor battlecard" | today's `competitor` mode (the seed domain) |

### G.4 Scope additions for the universal framing (⬜ unless noted)
- ⬜ `Task` carries `domain` + `persona` (reading-level / tone / format) params
- ⬜ **Persona-adaptive synthesis** — same findings, audience-appropriate output (reading level, format)
- ⬜ **Domain source/tool registry** — PubMed/clinical, academic, dev-docs, nutrition, legal, finance… +
  per-domain output schemas
- ⬜ Orchestrator selects domain skill + persona profile per task; creates a new domain skill when missing
- ✅ Competitor/market = first packaged domain (competitor + discovery shipped)

The Project→Task→Orchestrator build (Section F) is unchanged in shape — **Task simply gains `domain` +
`persona`**, and the "mode library" becomes a **"research-skill library across domains × personas."**

---

## H. Finalized build plan + evaluation/reuse (SENTINEL-012)

The platform design is finalized and specced as **SENTINEL-012** (`docs/specs/SENTINEL-012/{spec,design,plan}.md`).
Reviewed by an adversarial architecture-critic + the BiltIQ plan-reviewer (both "needs-revision", converged);
all findings adopted. This section is the authoritative summary; the spec §9/§10 govern on conflict.

### H.1 Reality check that reshaped the plan
"Add a layer, reuse the engine" was **false**: `_execute_pipeline`/`_drive` are hardcoded to the two modes
(`Mode` literal, `_OUTPUT_KEY`, `REASONER_OUTPUT_KEYS`, `allowed_boundaries`, `maybe_strategist`). So the
real prerequisite is an **engine refactor** (extract a generic `run_step`; derive the 12B-tools/26B-reason
split from a per-spec `role`, not a hardcoded key set — else generic reasoner steps route to the 12B and
re-trigger the 524; freeze the legacy path behind a byte-identical golden test).

### H.2 Decisions
- **Full dynamic orchestrator retained** (Project→Task→Planner→staff→DAG→Result) — not the templates-only
  simplification — but with every safety/cost/observability fix mandatory.
- **High-stakes domains (medicine/clinical, legal) scoped OUT** via a `domain.risk_tier` gate (rejected at
  task creation). Shipped domains: market/competitor, food/B2C, software/dev, academic/study.
- **Single-operator** scope this program (projects organise, not a security boundary; no multi-tenancy yet).

### H.3 Agent reuse + evaluation (continuous improvement)
- **Reuse:** `AgentRegistry` keys `AgentSpec` by `(capability, domain)` with `version` + `eval_score`;
  `resolve()` returns the **highest-scoring active** spec → similar tasks reuse it; create-new only on a miss.
- **Two graders:** **code-based** (deterministic, every result + CI — schema, citations present+resolve+
  claim-support, boundary-clean, zero-Gemini sovereignty, reading-level band; hard failures block) and
  **model-based** (LLM-as-judge rubric: relevance/faithfulness/completeness/actionability/persona-fit, on an
  independent judge model, over golden eval sets + sampled prod).
- **Improvement loop:** versioned golden eval set per domain; a prompt/agent change is **promoted only if
  non-regressing + improved** (CI gate); the promoted version becomes what `resolve()` reuses. Eval score = reuse key.
- New: `eval/graders.py`, `eval/runner.py`, `eval/sets/<domain>/*.json`.

### H.4 Authoritative phasing (see `plan.md` for atomic steps + tests)
- **Phase 0 — Engine refactor (prereq):** per-spec `role` partition + generic `run_step` + golden no-regression test.
- **Phase 1 — Foundations:** Project/Task schemas; store migration (ADR-0003: projects/tasks/plans/agent_specs +
  `project_id`); code-grader wired into the result path; `/projects` UI shell + project scoping.
- **Phase 2 — Fixed value chain (BiltIQ deliverable):** `self_profile` + `compare` skills + `ProgramStrategy`;
  hand-built DAG (S1 self_profile→S2 discover→S3 competitor→S4 compare→S5 strategy) with budgets + per-entity
  cache + per-step status/resume/degraded; persona render-only; model-grader + eval sets + improvement runner.
- **Phase 3 — Dynamic orchestrator (decomposed):** 3a generic DAG runner → 3b AgentRegistry + safe
  `build_from_spec` (validate, tool allow-list, zero-Gemini, reuse-by-score) → 3c Planner emits validated Plan →
  3d autonomy gate (propose default / autonomous opt-in) + plan-review UI → 3e prompt-injection stance.

Status: architecture finalized; **nothing built for 012 yet** — Phase 0 is the entry point.
