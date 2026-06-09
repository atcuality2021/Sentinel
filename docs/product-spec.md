# Sentinel — Product Spec (BA + Requirements)

**Author:** BA pass, 2026-06-07 · **Status:** Draft for owner confirmation
**Inputs:** project brief, hackathon brief, current build (`src/sentinel/*`), `docs/business-analysis.md`, `docs/srs.md`

> Purpose: take the current basic demo and define the *real product* — personas, user
> stories, end-to-end flow, what the dashboard shows, where models/agents/prompts/tokens are
> configured, and the memory harness. Ends with a deadline-aware phasing plan (the demo is due
> 2026-06-11), because not all of this can or should ship before then.

---

## 1. Personas (who uses it, what they want)

| # | Persona | Role | Primary goal | Influence |
|---|---|---|---|---|
| P1 | **Analyst / Operator** | Sales or strategy at a regulated SMB | Get a trustworthy battlecard/brief in minutes, with sources | High |
| P2 | **Admin / Power user** | RevOps / sales-ops lead | Configure models, prompts, connectors; control cost & quality | High |
| P3 | **Compliance officer** | Risk / legal | Prove private data never left; audit every run; data residency | High (regulatory) |
| P4 | **Account owner (AE)** | Field sales | Memory of an account across runs; "what changed since last time" | Medium |
| P5 | **Evaluator / Judge** | Challenge judge | See the differentiator in 3 min; run it live | Demo-only |

---

## 2. Epics

- **E1 — Run intelligence** (core: target → battlecard/brief)
- **E2 — Dashboard & insights** (overview, activity, system status)
- **E3 — Model configuration** (per-agent model + backend selection)
- **E4 — Agent configuration** (the pipeline: planner / public / private / synthesizer)
- **E5 — Prompt management** (editable, versioned instruction templates)
- **E6 — Generation defaults** (temperature, max tokens, top_p/k, safety)
- **E7 — Memory harness** (run history, entity memory, org preferences)
- **E8 — Connectors / private boundary** (Workspace MCP, CRM, OAuth, scopes)
- **E9 — Governance & audit** (compliance mode, residency, audit log, provenance)

---

## 3. User stories (with acceptance criteria)

### E1 — Run intelligence
- **US-1.1** As an *Analyst*, I want to enter a competitor and get a battlecard so I can prep for a deal.
  - [ ] Given a target + competitor mode, when I run, then I get a Battlecard with ≥1 cited finding per populated section within ~60s.
  - [ ] Every finding shows a 🔵public/🟠private provenance tag and (for public) a clickable source.
- **US-1.2** As an *Analyst*, I want an account brief that merges public + private signal so I know how to re-engage.
  - [ ] Given client mode with a connector, then `merged_insights` references at least one public and one private fact.
  - [ ] If no connector, the brief still ships with `private_signal=[]` and a flagged Gap (graceful degradation).
- **US-1.3** As an *Analyst*, I want to watch progress (plan → research → synthesis) so I trust the result.
  - [ ] The run shows live step status; the final page exposes the run trace.

### E2 — Dashboard
- **US-2.1** As an *Operator*, I want an at-a-glance overview (recent reports, public/private split, backend in use, system health) so I know the system state.
  - [ ] KPIs, provenance chart, recent runs, and a "system status" panel (key set? connector up? backend healthy?) all render.
- **US-2.2** As an *Account owner*, I want to jump from the dashboard to a specific account's history.

### E3 — Model configuration
- **US-3.1** As an *Admin*, I want to pick which model each agent uses (e.g., planner=flash, synthesizer=pro) so I balance cost vs quality.
  - [ ] Per-agent model dropdown; saved; applied on next run; shown in the run trace.
- **US-3.2** As an *Admin*, I want to choose the backend (Gemini cloud / Gemma on-prem) globally and per-run.
  - [ ] Default from config; per-run toggle overrides; resolved backend recorded on the artifact.

### E4 — Agent configuration
- **US-4.1** As an *Admin*, I want to see the agent pipeline and toggle/configure each step.
  - [ ] List of agents (planner, public_research, private_research, synthesizer) with model, prompt, tools, enabled-state.
- **US-4.2** As an *Admin*, I want to enable/disable the private research agent without code changes.

### E5 — Prompt management
- **US-5.1** As an *Admin*, I want to edit each agent's instruction prompt in the UI so I can tune output without redeploying.
  - [ ] Prompt editor per agent with visible variables (`{target}`, `{research_plan}`, …); validates required variables present.
  - [ ] "Reset to default" restores the shipped prompt.
- **US-5.2** As an *Admin*, I want prompt versions so I can roll back a bad edit.
  - [ ] Each save creates a version with timestamp; can view/restore previous.

### E6 — Generation defaults
- **US-6.1** As an *Admin*, I want to set temperature, max output tokens, top_p/top_k (global + per-agent) so I control determinism, length, and cost.
  - [ ] Settings persisted and passed to the model as `generate_content_config`; per-agent overrides win over global.
  - [ ] Sensible defaults shown (e.g., planner temp 0.2, synthesizer temp 0.4, max_output_tokens 2048).

### E7 — Memory harness
- **US-7.1** As an *Account owner*, I want Sentinel to remember prior runs on an entity so a new brief includes "what changed since last time."
  - [ ] Running the same account twice surfaces a "since last run" delta section.
- **US-7.2** As an *Admin*, I want org-level preferences (our positioning, tone, what matters) remembered and injected into every synthesis.
- **US-7.3** As a *Compliance officer*, I want memory retention controls and the ability to purge an entity's memory.

### E8 — Connectors
- **US-8.1** As an *Admin*, I want to connect Google Workspace / a CRM via OAuth with explicit read-only scopes.
  - [ ] Connection status visible; scopes listed; disconnect available.

### E9 — Governance & audit
- **US-9.1** As a *Compliance officer*, I want an audit log of every run (who, what, backend, sources, data touched) so I can demonstrate control.
- **US-9.2** As a *Compliance officer*, I want to enforce on-prem-only (no cloud calls on private data) per policy.

---

## 4. Complete user flow (end-to-end)

### 4.1 First-time setup (Admin)
1. Land on Dashboard → empty state + "Finish setup" checklist.
2. **Settings → Connectors:** add Gemini key (or on-prem endpoint); connect Workspace/CRM.
3. **Settings → Models/Generation:** accept defaults or tune.
4. **Settings → Governance:** pick compliance mode (cloud_ok / on_prem_required).
5. Status panel turns green → ready.

### 4.2 Core run (Analyst) — happy path
1. Click **New Report** → choose target, mode, vertical, backend.
2. Submit → progress view: *Planning → Public research → Private research → Synthesizing*.
3. Memory retrieval runs first: prior facts on this entity + org prefs are injected.
4. Result page: the battlecard/brief with provenance tags, "since last run" delta, provenance donut, run trace.
5. Actions: **Save/Export** (Markdown / Google Doc / CRM), **Re-run**, **Pin to account**.
6. Run is written to history + entity memory updated.

### 4.3 Config change (Admin)
Settings → edit model/prompt/tokens → save (versioned) → next run uses it → diff visible in trace.

### 4.4 Account review (Account owner)
Accounts → pick account → timeline of past briefs + accumulated entity profile → "Generate fresh brief."

```
Operator ─▶ New Report ─▶ [Memory retrieve] ─▶ Plan ─▶ Public research ─┐
                                                  └▶ Private research ───┤
                                                                         ▼
                          Export ◀─ Result (provenance + delta) ◀─ Synthesize
                                          │
                                          └▶ [Memory write-back] ─▶ Entity profile + History
```

---

## 5. Dashboard — what should be on it

**Home / Overview**
- **KPI row:** Reports (period), Accounts tracked, Public vs Private findings, Avg run time, Est. cost (period).
- **Charts:** Signal provenance donut (public/private — the signature), Runs by mode, Backend usage, Reports-over-time line.
- **System status panel:** backend health (Gemini key / vLLM reachable), connector status, compliance mode, last error.
- **Recent reports table:** target, mode, backend, provenance, when → click to open.
- **Quick actions:** New Report, Resume draft, Open last account.

**Other primary pages** (new information architecture):
- **Reports / History** — searchable list of every run + filters.
- **Accounts & Competitors** — entity pages with accumulated memory + run timeline (this is where memory becomes visible value).
- **Settings** — the config home (below).

Proposed nav: `Dashboard · New Report · Reports · Accounts · Settings`.

---

## 6. Where to configure models / agents / prompts / tokens

Single source of truth: a **`SentinelConfig`** object, persisted (JSON/YAML file now; DB later), editable in **Settings**, loaded by the agent builders instead of today's hardcoded values. Proposed shape:

```yaml
backend:
  default: gemini            # gemini | vllm
  gemini:  { model: gemini-2.5-flash, api_base: null }
  vllm:    { model: google/gemma-3-4b-it, api_base: http://localhost:8000/v1 }

generation:                  # global defaults → ADK generate_content_config
  temperature: 0.3
  max_output_tokens: 2048
  top_p: 0.95
  top_k: 40
  safety: default

agents:                      # the pipeline; per-agent overrides win
  planner:
    enabled: true
    model: gemini-2.5-flash
    generation: { temperature: 0.2, max_output_tokens: 1024 }
    prompt_ref: planner@v3
  public_research:
    enabled: true
    model: gemini-2.5-flash  # pinned to Gemini (grounding is native)
    prompt_ref: public_research@v2
  private_research:
    enabled: true            # auto-off if no connector
    model: <inherit backend>
    prompt_ref: private_research@v2
  synthesizer:
    enabled: true
    model: gemini-2.5-pro
    generation: { temperature: 0.4, max_output_tokens: 3072 }
    prompt_ref: synthesizer@v4

prompts:                     # editable, versioned templates with declared variables
  planner:
    version: 3
    variables: [target, vertical_context]
    template: "You are a competitive-intelligence planner..."
  # ...one per agent, each with version history

memory:
  entity_memory: true
  retention_days: 365
  inject_org_prefs: true

governance:
  compliance_mode: cloud_ok  # cloud_ok | on_prem_preferred | on_prem_required
  audit_log: true
  block_cloud_on_private: false
```

**Settings UI sections (map 1:1 to the config):**
1. **Backends** (exists, expand) — default backend, model per backend, endpoint, health check.
2. **Models** — per-agent model picker.
3. **Agents** — pipeline list; enable/disable; model + generation + prompt link per agent.
4. **Prompts** — editor per agent with variable hints, validation, version history, reset-to-default, live preview.
5. **Generation** — global sliders (temperature/max tokens/top_p/top_k/safety) + per-agent overrides.
6. **Connectors** — Gemini key, Workspace/CRM OAuth + scopes, status.
7. **Memory** — toggles, retention, org-preferences editor, purge.
8. **Governance** — compliance mode, audit log, residency, on-prem-only enforcement.

This replaces scattered env vars + hardcoded instructions with one editable, versioned config the agent builders read at runtime.

---

## 7. Memory harness

Today: only **working memory** (per-run session state). Target: a 3-tier harness.

| Tier | What | Lifetime | Store |
|---|---|---|---|
| **Working** | within-run state (target, plan, findings) | one run | in-memory (exists) |
| **Episodic** | every run + its artifact + trace | persistent | history store |
| **Entity** | accumulating profile per competitor/account ("Stripe raised prices in Q1"; "Acme deal stalled at security review") | persistent, decaying | entity store |
| **Semantic / Org** | org positioning, tone, ICP, what matters | persistent | config/prefs |

**Loop:** on a run → **retrieve** relevant entity + org memory → inject into planner/synthesizer prompts → produce artifact → **write back** new facts to the entity profile + append to history. Result: each run on the same entity gets a **"What changed since last run"** delta — the visible payoff of memory.

**Storage:** start as JSON files under `data/` (entities/, history/, prefs.json); upgrade to SQLite (or pgvector for semantic recall) post-deadline. Keep memory **per-tenant** and respect compliance mode (on-prem memory stays on-prem).

---

## 8. Non-functional requirements (delta from current)

- **Persistence:** runs/memory survive restart (today they don't — in-memory only).
- **Config without redeploy:** model/prompt/token changes take effect on next run.
- **Auditability:** every run logged with backend, sources, data boundaries touched.
- **Cost control:** token caps + per-agent model selection; show estimated cost.
- **Security:** secrets in a secret store, not the config file; OAuth tokens encrypted at rest.
- **Residency:** on_prem_required ⇒ no private data leaves; enforced, not just labeled.

---

## 9. Phasing — what to build before 2026-06-11 vs after

**The deadline is 4 days out. Building all of Sections 5–7 now would sink the demo.** Recommended split:

### Phase 0 — ship for the submission (now → Jun 11)
Goal: make it look and feel like a real product, prove the differentiators, run live.
- [ ] **Persist runs to disk** (JSON history) so the dashboard survives restart and looks real.
- [ ] **Settings page (read + light edit):** backend default, per-agent model, generation defaults (temperature, max tokens). Persisted to a `sentinel.config.yaml`.
- [ ] **Prompts: view + edit (no versioning yet)** for the 4 agents, stored in config.
- [ ] **Entity memory (lite):** store per-target run history; show "since last run" delta on re-run.
- [ ] Wire config into the agent builders (replace hardcoded model/prompt/generation).
- [ ] Live run with a real Gemini key (still the one blocker).
- [ ] Demo video + Cloud Run deploy.

### Phase 1 — after the deadline
- Prompt versioning + rollback + live preview.
- Full agent enable/disable + tool config UI.
- Connectors OAuth UI (Workspace/CRM), scope management.
- Memory upgrade to SQLite/pgvector + org-prefs editor + purge.
- Governance: audit log UI, on-prem-only enforcement, cost dashboard.
- Multi-tenant + auth.

---

## 10. Open questions (need owner's call)

- **Q1 — Audience for the demo:** optimize Phase 0 for *judges* (wow + differentiator) or for a *real pilot user*? (changes how much config we expose vs polish the run flow.)
- **Q2 — Config depth for Phase 0:** is "model + generation + editable prompts, no versioning" the right cut, or do you want prompt versioning in the demo too?
- **Q3 — Memory scope for Phase 0:** is per-target "since last run" delta enough, or do you want full Accounts pages with timelines now?
- **Q4 — Auth:** any login/multi-user needed for the demo, or single-operator is fine?
- **Q5 — Persistence target:** JSON-on-disk for Phase 0 (fast) vs go straight to SQLite?
```
