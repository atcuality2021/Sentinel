# Business Analysis — Sentinel "Intelligence-to-Action" Program

**Prepared:** 2026-06-07 · **Author:** BiltIQ AI · **Method:** `business-analysis` skill
**Context:** Extends the shipped Sentinel agent (SENTINEL-001..005) with the research → action →
prioritization loop borrowed (patterns, not code) from BiltIQ **LeadFlow / CommandCenter**
(`gitlab.com/leadflow2/leadflow`, branch `harish`).
**Maps to challenge judging:** Business Case (30%) + Innovation (20%) + Technical (30%).
**Status:** Draft for stakeholder confirmation → then per-increment spec→design→plan.

---

## PROBLEM

Sentinel today **produces an artifact and stops.** A run yields a Battlecard or AccountBrief —
cited, boundary-separated, accurate — but it answers *"what did we find?"* not *"so what do I do,
and which account do I do it to first?"* The pilot user (a sales/BD lead at a regulated SMB) still
has to read the brief, decide the next move, and manually choose where to spend the day. That is the
exact gap LeadFlow already closed inside its CRM: research feeds a **structured action plan**, a
**strategy playbook** turns judgment into a repeatable framework, and a **deterministic priority
score** tells the user *who to focus on now*. Sentinel has the research half and none of the action
half. Worst case observed in LeadFlow's absence: a rep with 40 accounts opens each brief cold every
morning, re-derives priority by gut, and lets stalled deals and at-risk accounts go silently past
their kill date.

Borrowing LeadFlow's *patterns* (it runs on the same on-prem vLLM stack, so they are proven in our
environment) closes that gap **without inheriting its CRM weight** — and it does so *sovereign*,
which the cloud incumbents (Klue, Clay, ZoomInfo) cannot.

> **Not a solution restatement:** the ask is not "add a recommendations field." It is "make the
> agent's output executable and ranked, so the user acts instead of re-analyzing."

---

## STAKEHOLDERS + GOALS

| Stakeholder | Goal | Priority |
|---|---|---|
| **P1 Analyst / BD lead** (pilot user) | Open one screen, see *which* accounts need action today and *what* the next move is, each with a cited reason | **High** |
| **P2 Admin** | Tune the strategy frameworks (playbooks) and priority weights without a redeploy | High |
| **P3 Compliance** | The whole action+priority layer obeys `on_prem_required` — no cloud egress, ever | **High (regulatory)** |
| **Owner (BiltIQ)** | Differentiate vs incumbents for the challenge: "sovereign intelligence *to action*", defensible Business Case | High |
| **Engineering** | Reuse LeadFlow patterns without importing its tech debt (free-text-JSON repair, triple scorers) | Medium |
| **Challenge judges** | See innovation (boundary + sovereign action loop) + a credible business case | Medium (scoring) |

---

## SCOPE — three capability themes (→ three increments)

The user asked to improve **(a) research, (b) action plan, (c) client search + suggested strategy.**
Each becomes one spec'd increment:

| Theme | Increment | One line |
|---|---|---|
| **(a) Research depth** | **SENTINEL-008** | Config-driven pipeline + two-tier extract→synthesize + run versioning/provenance |
| **(b) Action plan & strategy** | **SENTINEL-009** | Structured `recommended_actions` + `assessment` + `objection_handling` + **strategy playbooks** (Markdown overlay) |
| **(c) Prioritization / "who to focus on"** | **SENTINEL-010** | Deterministic **weighted-signal registry** over entity memory + reason-ranked **focus list** on the dashboard |

> **Numbering note (open question OQ-1):** SENTINEL-009's playbook-overlay mechanism realizes what
> the backlog previously called **007 "Automatic Skills."** Proposal: fold 007 into 009 and retire
> the 007 placeholder. **006 "Connectors"** (private MCP OAuth) stays separate and is a *soft*
> dependency of richer client research.

---

## USER STORIES + ACCEPTANCE CRITERIA

### Theme A — Research depth (SENTINEL-008)

**US-A1** — *As an analyst, I want each source extracted into clean structured notes before
synthesis, so the final brief is grounded in facts not raw HTML.*
- [ ] AC-A1.1 Given N public sources, when a run executes, then each source is parsed by a small/cheap
  (on-prem-eligible) model into typed notes **before** the synthesis call.
- [ ] AC-A1.2 The synthesis prompt receives only the structured extractions (bounded size), never raw page text.
- [ ] AC-A1.3 If one source fails extraction, the run continues and records that source as a gap (fail-soft).

**US-A2** — *As an admin, I want to add a new research mode by adding config, not editing the pipeline.*
- [ ] AC-A2.1 A research mode is defined by a declarative config (sources, prompts, output schema, models); adding one requires no change to the pipeline engine.
- [ ] AC-A2.2 The existing competitor & client modes are expressed as two such configs with **byte-identical** output to today (no regression).

**US-A3** — *As an analyst, I want to see what changed since the last brief for the same entity.*
- [ ] AC-A3.1 Every run is versioned and persisted with its sources; the entity page can show a "since last run" delta (extends SENTINEL-002/004).
- [ ] AC-A3.2 Each finding retains its source citation and boundary (unchanged invariant).

### Theme B — Action plan & strategy (SENTINEL-009)

**US-B1** — *As a BD lead, I want the brief's recommendations to be executable items I can sort and schedule, not a flat list of sentences.*
- [ ] AC-B1.1 `recommended_actions[]` items are objects `{action, priority(high|med|low), timeline, rationale}` — not strings.
- [ ] AC-B1.2 The brief carries a top-level `assessment` (1–2 sentences: where the entity stands + best angle).
- [ ] AC-B1.3 Actions are returned via the agent's **structured (pydantic) output** — no free-text JSON repair.

**US-B2** — *As an admin, I want to encode our sales/strategy judgment as editable frameworks the agent applies, without redeploying.*
- [ ] AC-B2.1 A **playbook** is a Markdown file (frontmatter + framework + output template + house rules) loaded at runtime.
- [ ] AC-B2.2 The strategy step injects the selected playbook as the agent instruction overlay for that turn.
- [ ] AC-B2.3 Editing a playbook file changes the agent's strategy output on the next run with no code change.
- [ ] AC-B2.4 At least 2 shipped playbooks (e.g. `account-strategy`, `competitor-counterplay`).

**US-B3** — *As an analyst (client mode), I want anticipated objections and how to reframe them.*
- [ ] AC-B3.1 AccountBrief gains `objection_handling[]` (likely objection → evidence-based reframe), populated from merged public+private signal.

**US-B4 (governance)** — *As compliance, I want the strategy layer to honor sovereignty.*
- [ ] AC-B4.1 In `on_prem_required`, strategy generation + playbook reasoning run on vLLM only — **zero Gemini** (reuses SENTINEL-005 `cloud_allowed`).

### Theme C — Prioritization / suggested strategy (SENTINEL-010)

**US-C1** — *As a BD lead, I want one screen that ranks my accounts by who needs attention now, each with a cited reason.*
- [ ] AC-C1.1 `compute_account_priority(entity)` returns `{score 0-100, tier, breakdown{signal→value}}`, computed **deterministically** (no LLM in the arithmetic).
- [ ] AC-C1.2 The dashboard shows a ranked **focus list**; each row carries human-readable `reasons[]`, each reason linked to a cited finding / memory entry.
- [ ] AC-C1.3 The score breakdown is explainable and persisted (auditable).

**US-C2** — *As an admin, I want to add/weight a priority signal without touching the scorer core.*
- [ ] AC-C2.1 Signals register via `register_signal(name, weight, fn)`; the engine normalizes weights to 1.0, isolates per-signal failures (default fallback), clamps 0-100.
- [ ] AC-C2.2 One signal registry is the single source of truth (no parallel competing scorers).

**US-C3** — *As an analyst, I want recency to matter — a finding from 18 months ago should weigh less than last week's.*
- [ ] AC-C3.1 A reusable time-decay (e.g. half-life) and `normalize(value, low, high, invert)` primitive is available to signals.

**US-C4 (governance)** — *As compliance, the focus list must not leak private data into a public view.*
- [ ] AC-C4.1 Priority reasons respect the boundary invariant; a public-only context never surfaces a private-sourced reason.

---

## NON-FUNCTIONAL REQUIREMENTS

- **Performance:** a strategy/action step adds ≤ 1 LLM call per brief; priority score for an entity computes in < 200 ms (deterministic, no network).
- **Sovereignty (hard):** every new capability obeys `governance.compliance_mode`; `on_prem_required` ⇒ no cloud egress in research extraction, synthesis, strategy, or scoring.
- **Security:** no secrets in config/code/HTML (continue the SENTINEL "one center" rule — keys env-only, shown as pills).
- **Reliability:** deterministic-first — scores and threshold flags are pure code; the LLM only narrates/prioritizes; an LLM failure degrades to the deterministic payload, never breaks a run.
- **Maintainability:** playbooks + signal weights are editable artifacts (Markdown / config), not redeploy-gated.
- **No regression:** SENTINEL-002 boundary invariant and 003/004 surfaces unchanged; default config reproduces current behaviour (ship dark).
- **Types:** pydantic structured output; no `Any`, no `# type: ignore` without justification.

---

## SUCCESS METRICS

| Metric | Baseline (today) | Target |
|---|---|---|
| Brief → action without manual re-analysis | 0 (report only) | Every brief yields ≥ 3 structured, prioritized actions |
| "Who do I focus on?" answered | manual / gut | 1 ranked focus list, cited reasons, < 1 s to load |
| Strategy framework change cycle | code + redeploy | edit a Markdown playbook, effective next run |
| Sovereign action loop (no cloud) | research only | full research→action→priority runs in `on_prem_required` with zero Gemini (provable) |
| Challenge differentiation | "sovereign research" | "sovereign research **to action**" — a story no incumbent matches |

---

## OUT OF SCOPE (this program)

- Full CRM (pipeline kanban, invoicing, multi-channel messaging) — LeadFlow *is* that; Sentinel is not becoming a CRM.
- Auto-sending outreach / writing back to CRM (that's connector/SENTINEL-006 territory; here we *recommend*, a human acts).
- Learned/ML segmentation, vector client search — deterministic registry + filters only.
- LinkedIn browser scraping, the free-text-JSON repair stack, India/MEDDPICC-specific weights — explicitly *not* borrowed.
- Audit-log persistence — already a separate deferred SENTINEL-005 sub-increment.

---

## DEPENDENCIES

- **SENTINEL-005** (governance) — **ready**; 008/009/010 reuse `cloud_allowed` / `effective_*`.
- **SENTINEL-002/004** (memory + entity pages) — **ready**; 010 scores over accumulated memory, 008 versioning extends run history.
- **SENTINEL-006 Connectors (MCP OAuth)** — *soft* dependency: richer **private** signal makes client research + priority stronger, but 008/009/010 work on public + currently-configured MCP without it.
- LeadFlow source (read-only reference) cloned at `/tmp/leadflow-src` (branch `harish`).

---

## RISKS + MITIGATIONS

- **R-1 Scope vs 4-day deadline.** *Mitigation:* sequence by judging leverage — 009 (action plan, most visible) first, then 010 (focus list), 008 last (back-end depth). Each ships independently and dark.
- **R-2 Re-importing LeadFlow tech debt** (triple scorers, JSON repair). *Mitigation:* explicit "NOT borrowed" list above; use pydantic structured output + one signal registry.
- **R-3 Playbook overlay vs ADK tool loop** — overlay bypasses tools (cleaner reasoning, but staler context). *Mitigation:* design decision recorded per-increment; default tool-free strategy turn over the already-gathered findings.
- **R-4 Deterministic scoring feels arbitrary** if weights are opaque. *Mitigation:* always show the cited breakdown; weights are admin-editable.
- **R-5 Sovereignty regression** — a new LLM call sneaks a cloud model in. *Mitigation:* every new agent built through SENTINEL-005's `resolve_model(cloud_allowed=)`; introspection test per increment.

---

## RACI (program level)

| Deliverable | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| BA + SRS (this) | Claude (agent) | Owner (BiltIQ) | — | Engineering |
| Spec→design→plan per increment | Claude | Owner | LeadFlow patterns | — |
| Build 008/009/010 | Claude | Owner | — | Judges (via demo) |
| Compliance sign-off (sovereignty) | Claude | Compliance (P3) | Owner | — |

---

## OPEN QUESTIONS FOR STAKEHOLDER

- **OQ-1 (numbering):** fold the old "007 Automatic Skills" into **009** (playbooks = skills)? *Proposed: yes.*
- **OQ-2 (sequence):** build order **009 → 010 → 008** (visible-value-first) vs **008 → 009 → 010** (depth-first)? *Proposed: 009 → 010 → 008* given the deadline.
- **OQ-3 (scope of B):** ship 2 playbooks for the challenge, or a fuller library? *Proposed: 2 strong ones (account-strategy, competitor-counterplay).*
- **OQ-4 (priority signals):** which signals matter for the pilot's accounts? *Proposed seed set:* finding-recency, new-material-finding, competitor-move, stale-account (days since last run), private-engagement (if MCP connected). Needs pilot confirmation.
- **OQ-5 (small extraction model):** in cloud mode use `gemini-flash` for extraction + `gemini-pro`-class for synthesis; in on-prem use one Gemma for both? *Proposed: yes — two-tier only when it pays off.*
