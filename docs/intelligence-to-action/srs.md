# System Requirements — Sentinel "Intelligence-to-Action" Program

**Version:** 0.1 (draft) · **Last updated:** 2026-06-07 · **Method:** `system-requirements-analyst`
**Status:** Draft — for stakeholder review, then per-increment spec→design→plan→build
**Source BA:** [`business-analysis.md`](./business-analysis.md) · **Reference impl:** BiltIQ LeadFlow
(`/tmp/leadflow-src`, branch `harish`) — patterns only, not code.
**Builds on:** SENTINEL-001 (config), 002 (memory+boundary), 003 (settings), 004 (reports/accounts),
005 (governance + pluggable search).

---

## 1. Stakeholders

| # | Name/Role | Type | Influence | Primary concern |
|---|---|---|---|---|
| 1 | Analyst / BD lead (pilot user) | End user | H | Executable next move + who to focus on, with cited reasons |
| 2 | Admin | Operations | M | Edit playbooks + priority weights without redeploy |
| 3 | Compliance | Compliance | H | Action+priority layer never egresses to cloud in `on_prem_required` |
| 4 | Owner (BiltIQ) | Sponsor | H | Differentiated challenge story; defensible business case |
| 5 | Engineering | Operations | M | Reuse LeadFlow patterns without its tech debt |

---

## 2. Functional Requirements

IDs group by increment: **08x** = SENTINEL-008 (research), **09x** = 009 (action/strategy),
**10x** = 010 (prioritization).

### SENTINEL-008 — Research depth

| ID | Pri | Requirement | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-081 | Must | The research pipeline SHALL extract each source into typed structured notes via a small/cheap model **before** synthesis. | US-A1 | AC-A1.1/.2 |
| FR-082 | Must | Per-source extraction SHALL fail soft — a failed source becomes a recorded gap, the run continues. | US-A1 | AC-A1.3 |
| FR-083 | Must | A research mode SHALL be defined declaratively (sources, prompts, output schema, model roles); adding a mode SHALL require no pipeline-engine change. | US-A2 | AC-A2.1 |
| FR-084 | Must | Existing competitor & client modes SHALL be expressed as configs producing output byte-identical to SENTINEL-004. | US-A2 | AC-A2.2 |
| FR-085 | Should | Each run SHALL be versioned and persisted with its sources, enabling a "since last run" delta on the entity page. | US-A3 | AC-A3.1 |
| FR-086 | Must | Every finding SHALL retain its source citation + boundary (unchanged invariant). | US-A3 | AC-A3.2 |

### SENTINEL-009 — Strategy & action plan

| ID | Pri | Requirement | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-091 | Must | `recommended_actions[]` SHALL be objects `{action, priority∈{high,med,low}, timeline, rationale}`. | US-B1 | AC-B1.1 |
| FR-092 | Must | Each artifact SHALL carry an `assessment` (1–2 sentences: standing + best angle). | US-B1 | AC-B1.2 |
| FR-093 | Must | Strategy output SHALL use the agent's pydantic structured output — no free-text-JSON repair layer. | US-B1 | AC-B1.3 |
| FR-094 | Must | A **playbook** SHALL be a runtime-loaded Markdown file (frontmatter + framework + output template + house rules). | US-B2 | AC-B2.1 |
| FR-095 | Must | The strategy step SHALL inject the selected playbook as the agent instruction overlay for that turn. | US-B2 | AC-B2.2 |
| FR-096 | Must | Editing a playbook file SHALL change strategy output on the next run with no code change. | US-B2 | AC-B2.3 |
| FR-097 | Should | At least two playbooks SHALL ship (`account-strategy`, `competitor-counterplay`). | US-B2 | AC-B2.4 |
| FR-098 | Should | AccountBrief SHALL gain `objection_handling[]` (objection → evidence-based reframe). | US-B3 | AC-B3.1 |
| FR-099 | Must | In `on_prem_required`, strategy + playbook reasoning SHALL run on vLLM only (zero Gemini). | US-B4 | AC-B4.1 |

### SENTINEL-010 — Prioritization & suggested strategy

| ID | Pri | Requirement | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-101 | Must | `compute_account_priority(entity)` SHALL return `{score 0-100, tier, breakdown{signal→value}}`, computed deterministically (no LLM arithmetic). | US-C1 | AC-C1.1 |
| FR-102 | Must | The dashboard SHALL show a ranked **focus list**; each row SHALL carry `reasons[]` linked to cited findings/memory. | US-C1 | AC-C1.2 |
| FR-103 | Must | The score breakdown SHALL be explainable and persisted (auditable). | US-C1 | AC-C1.3 |
| FR-104 | Must | Priority signals SHALL register via `register_signal(name, weight, fn)`; the engine SHALL normalize weights to 1.0, isolate per-signal failures with a default, and clamp 0-100. | US-C2 | AC-C2.1 |
| FR-105 | Must | Exactly one signal registry SHALL be the source of truth (no parallel scorers). | US-C2 | AC-C2.2 |
| FR-106 | Should | A reusable `normalize(value, low, high, invert)` + time-decay (half-life) primitive SHALL be available to signals. | US-C3 | AC-C3.1 |
| FR-107 | Must | Priority reasons SHALL respect the boundary invariant (no private-sourced reason in a public-only context). | US-C4 | AC-C4.1 |

---

## 3. Non-Functional Requirements

| ID | Category | Requirement | Metric | Target | Source |
|---|---|---|---|---|---|
| NFR-1 | Performance | Strategy step overhead | extra LLM calls / brief | ≤ 1 | NFR(BA) |
| NFR-2 | Performance | Priority score compute | latency, no network | < 200 ms / entity | NFR(BA) |
| NFR-3 | Sovereignty | All new LLM calls honor `compliance_mode` | Gemini objects built in `on_prem_required` | **0** (introspection-proven) | P3 / SENTINEL-005 |
| NFR-4 | Security | No secret in config/code/HTML | secrets in YAML/HTML | 0 (env-only, pills) | "one center" |
| NFR-5 | Reliability | Deterministic-first | LLM failure breaks a run | never (degrades to deterministic payload) | login_briefing pattern |
| NFR-6 | Maintainability | Playbooks + weights editable | redeploy to change strategy | not required | P2 |
| NFR-7 | Compatibility | No regression | SENTINEL-002 boundary + 003/004 tests | all pass; default = byte-identical | NFR(BA) |
| NFR-8 | Quality | Typed contracts | `Any` / unjustified `# type: ignore` | 0 | AGENT_RULES |

---

## 4. Constraints

| # | Constraint | Source | Impact |
|---|---|---|---|
| C-1 | Must run on Google ADK programmatic Runner + pydantic output (existing stack) | repo | New agents use `make_agent`/`resolve_model` seams |
| C-2 | Must obey SENTINEL-005 governance for every model + tool | 005 | Strategy/extraction agents built via `cloud_allowed` |
| C-3 | Boundary invariant (002) is inviolable | 002 | Priority reasons + strategy never leak private→public |
| C-4 | No new external paid API as a hard dependency | sovereignty | Search via 005 pluggable providers; no Clearbit/Apollo |
| C-5 | 4-day challenge window | deadline | Increments must ship independently + dark |
| C-6 | LeadFlow code is reference only (different DB/stack: Mongo/Beanie) | legal/arch | Port patterns, re-implement against SQLite/config |

---

## 5. Assumptions

| # | Assumption | Risk if wrong | Validation |
|---|---|---|---|
| A-1 | Two-tier extract/synthesize improves quality enough to justify the extra call | wasted complexity | A/B a battlecard with vs without extraction on one target |
| A-2 | Playbook overlay (tool-free strategy turn) over already-gathered findings is sufficient | staler strategy | Allow a tool-enabled variant if the brief lacks fresh data |
| A-3 | A small deterministic signal set is enough to make the focus list useful to the pilot | low adoption | Confirm seed signals (OQ-4) with the pilot user |
| A-4 | Gemma (on-prem) handles structured strategy output acceptably | weak on-prem strategy | Tested via the same path as 005's confirmed function-calling |
| A-5 | Public + currently-configured MCP signal is enough without SENTINEL-006 | thin client priority | 006 connectors strengthen but don't block |

---

## 6. Traceability Matrix

| Req | Source (US) | Increment / Component | Test (planned) | Status |
|---|---|---|---|---|
| FR-081/082 | US-A1 | 008 · research_pipeline (extract stage) | test_research_pipeline | Spec'd-pending |
| FR-083/084 | US-A2 | 008 · ResearchConfig registry | test_research_config (no-regression) | Spec'd-pending |
| FR-085/086 | US-A3 | 008 · run versioning (extends 002/004) | test_run_versioning | Spec'd-pending |
| FR-091/092/093 | US-B1 | 009 · AccountBrief/Battlecard schema + strategy agent | test_strategy_schema | Spec'd-pending |
| FR-094..097 | US-B2 | 009 · playbook_library + overlay | test_playbook_overlay | Spec'd-pending |
| FR-098 | US-B3 | 009 · objection_handling | test_objection_handling | Spec'd-pending |
| FR-099 | US-B4 | 009 · resolve_model(cloud_allowed) reuse | test_strategy_sovereign | Spec'd-pending |
| FR-101/103 | US-C1 | 010 · priority engine + persistence | test_priority_engine | Spec'd-pending |
| FR-102 | US-C1 | 010 · focus-list dashboard card | test_focus_list_route | Spec'd-pending |
| FR-104/105 | US-C2 | 010 · signal registry (single source) | test_signal_registry | Spec'd-pending |
| FR-106 | US-C3 | 010 · normalize + decay primitives | test_normalize_decay | Spec'd-pending |
| FR-107 | US-C4 | 010 · boundary-respecting reasons | test_priority_boundary | Spec'd-pending |
| NFR-3 | P3 | all · governance introspection | test_*_sovereign (per increment) | Spec'd-pending |
| NFR-7 | NFR | all · regression guard | full suite (currently 145 green) | Baseline green |

---

## 7. Open Questions

| # | Question | Owner to resolve | Proposed default |
|---|---|---|---|
| OQ-1 | Fold legacy "007 Automatic Skills" into 009 (playbooks)? | Owner | Yes |
| OQ-2 | Build order? | Owner | 009 → 010 → 008 (value-first, deadline) |
| OQ-3 | Playbook count for challenge? | Owner | 2 (account-strategy, competitor-counterplay) |
| OQ-4 | Seed priority signals for the pilot's accounts? | Pilot user | recency, new-material-finding, competitor-move, stale-account, private-engagement(if MCP) |
| OQ-5 | Two-tier models in cloud vs single Gemma on-prem? | Eng | flash+pro (cloud) / one Gemma (on-prem) |
| OQ-6 | Does strategy turn get tools or run tool-free over gathered findings? | Eng | tool-free default (A-2) |

---

## 8. Definition of "documented & ready to build"

This SRS + the BA are approved by the Owner; OQ-1..OQ-3 (scope/sequence/count) are answered; then
each increment gets its own `docs/specs/SENTINEL-00x/{spec,design,plan}.md` triad and is built
test-first, ending green with the regression suite intact and a per-increment sovereignty
introspection test.
