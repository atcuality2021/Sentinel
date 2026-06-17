# Sentinel v-next — Reusable Workflows: Program Design

**Status:** Design (finished). Supersedes the high-level sketch in
[`vnext-reusable-workflows.md`](./vnext-reusable-workflows.md) with code-grounded detail.
**Date:** 2026-06-14
**Scope chosen:** Full v-next program — all four borrows, one design, one multi-task plan.
**Origin:** Design study of the Rūmz *Set Piece & Promptbook* mockups + spec v1.2. We adopt four
patterns, drop the theatrical vocabulary, keep plain language.
**Companion plan:** [`vnext-reusable-workflows-plan.md`](./vnext-reusable-workflows-plan.md)
(4 sub-tasks SENTINEL-017…020, dependency graph, atomic steps).

---

## 0. What the code review changed (honesty ledger)

The Think-stage note made one wrong assumption and one pessimistic one. Both are corrected here,
verified against the tree on 2026-06-14:

| Note claimed | Reality (verified) | Effect on design |
|---|---|---|
| Borrow #1 = "render data we already persist; cost telemetry exists" | `gateway.py:50` (the single model factory) **discards litellm `usage`**. The `telemetry_events` table (`store.py:211`, G-13) **has** `tokens_in`/`tokens_out` columns, but **both record sites** (`dag.py:261`, `orchestrator.py:751`) pass only `latency_ms` — token columns are **always 0**. | Borrow #1 is *connect token capture into an existing-but-empty schema*, then aggregate + render. Not free, not greenfield. |
| Borrow #4 (human gate) = "the one genuinely new engine bit; suspend/resume is greenfield" | `dag.py:901` already does **resume-from-last-good** (skip steps `status=="done"`); the `plans` table (`store.py:100`) **already persists DAG state**; `tasks` (`store.py:93`) + `prospective_tasks` (`store.py:182`) tables exist. | Suspend/resume is *extending a status enum + an existing resume loop + reusing the plans/tasks tables* — meaningfully smaller than feared. |

Everything else in the note (the four borrows, the data-model shape, the sequencing, the
"instruction-on-the-binding" rule) survives review.

---

## 1. The shift

Today a run is **code-defined**: pick a domain (`ResearchModeSpec`) + persona, hit run, `run_dag`
executes a fixed pipeline. The user cannot save a run as a reusable template, never sees what it
cost, and never sees what reuse saved.

v-next: a run is driven by a **saved, user-authored Workflow** carrying its own steps, a token
budget, optional human gates, and a maturity label — and every run writes back **cost** and
**reuse-savings**. This is a **surface + reuse-accounting layer over the existing engine, not a new
engine.** The dual-tier Gemma sovereign core, the public/private boundary + provenance (our real
moat — Rūmz has no equivalent), the KB pipeline, async runs, and the live timeline are unchanged.

## 2. The four borrows

| # | Borrow | Rūmz term | Today | Net work |
|---|---|---|---|---|
| 1 | **Cost + Savings readout** | Bean Counter | latency telemetry wired; token columns exist but always 0; no cost UI | capture tokens at the gateway seam → aggregate per run → compute savings → render |
| 2 | **Reusable Workflow library** | Promptbook / Set piece | `playbooks.py` = read-only loaders, no CRUD/versioning | promote `Playbook`→`Workflow` model + CRUD + append-only versioning + re-run + `/workflows` UI |
| 3 | **Maturity chip** | honesty legend | none | one `maturity` field + render chip; honest on the 3/9-tested matrix |
| 4 | **Human-approval gate** | Cue → gate | `prospective_tasks` advisory only; no *synchronous* gate | extend step-status enum + resume loop; persist gate to `tasks`; resume route |

**Cost-lead thesis (the spine).** Rūmz spec §5.9/§8.3: *"retrieval beats generation; an
authored-once procedure removes re-derivation cost on every run."* Sentinel already does the hard
part — KB + episodic + semantic recall, `_persist_run` finding reuse, and a `"cached"` step status
(`dag.py:742`). We just never **count and show** the avoided cost. That number *is* the
sovereign-cost pitch.

## 3. Data model

### 3.1 Extend `RunRecord` (`src/sentinel/memory/schema.py:124`)

```
RunRecord  + cost_tokens: int = 0     # sum of tokens_in+tokens_out across this run's steps
           + saved_tokens: int = 0    # estimated tokens avoided via cache/KB/recall reuse
           + gate_state: str = ""      # "" | awaiting:<step_id> | approved:<step_id> | rejected
```

Defaults make old rows read back cleanly — the **exact precedent** already used for `run_seq`/
`project_id` (`schema.py:138-144`). Migration is three tuples appended to `_RUN_MIGRATIONS`
(`store.py:288`); `_apply_column_migrations` (`store.py:298`) ALTERs idempotently, guarded by
`PRAGMA table_info`. Add the three columns to the `INSERT` (`store.py:910`) and to `_row_to_run`
(`store.py:~369`), reading defensively via the existing `_col(...)` helper (`store.py:330`) so a
pre-migration row still loads.

### 3.2 Token capture — populate the schema that's already there

The `telemetry_events` table (`store.py:211`) and `TelemetryEvent` (`telemetry.py:16`) already carry
`tokens_in`/`tokens_out`/`model`/`run_id`/`step`. They are written latency-only today. Two seams:

- **Capture:** surface litellm/ADK `usage` (it returns `prompt_tokens`/`completion_tokens` on the
  response) at the run-step boundary in `orch.run_step`, threaded back through the `_StepOutcome`
  (`dag.py:87`) — which already has a `reasoner_delta: int` accumulator field, the natural place to
  add `tokens_in`/`tokens_out`. Fallback when the backend omits usage (some vLLM stream paths): a
  tokenizer estimate over prompt+completion text — sovereign-safe, no extra calls. **Open question
  OQ-1:** confirm ADK's `LiteLlm` response surface for usage vs. needing the estimator.
- **Record:** pass the captured counts into the existing `TelemetryEvent(...)` calls
  (`dag.py:268`, `orchestrator.py:755`) instead of letting them default to 0.

### 3.3 New: `Workflow` (promotes `Playbook`) + `WorkflowInput` (the "binding")

```
Workflow  (NEW — supersedes/extends strategy/playbooks.py:Playbook)   belongs to Project
  ├─ id, name, domain, description
  ├─ steps[]   : {op, instruction, inputs[], budget_tokens, gate, complete_when}
  ├─ version   : int — append-only; edit = new row at version+1, never mutate (spec §4.6)
  └─ maturity  : "built" | "beta" | "experimental"          ← the honesty chip (borrow #3)

WorkflowInput  (NEW — the "binding")
  └─ {kb_entry_id, instruction}   ← instruction rides the EDGE, not baked into KB text
```

**Key principle (Rūmz §3.4/§4.3 — "Elemental + instruction-on-the-binding"):** a KB entry stays
**canonical and immutable**; the per-step instruction ("use this as the competitor template") rides
the `WorkflowInput` binding. The same KB entry feeds N workflows with N instructions, zero
duplication. Concretely: stop concatenating instructions into prompt text; store them on the edge.

**Storage:** new `workflows` + `workflow_inputs` tables, modeled on the existing `agent_specs`
pattern (`store.py:112` — scalar columns for keyed lookup + full JSON in a `data` column). Versioning
= `(id, version)` composite; "current" = max version. `discover_playbooks` (`playbooks.py:70`) becomes
`list_workflows(project_id)`; `load_playbook` becomes `get_workflow(id, version=None)`.

## 4. Run lifecycle — `run_dag` stays the engine, three additions

Per step, the scheduler additionally:

1. **Meters** tokens against `step.budget_tokens`. The fold already sums `reasoner_delta`
   (`dag.py:991`); add a token sum alongside it. On cap breach: **halt the step and mark degraded**
   (reuse the existing `degraded` path, `_StepOutcome.degraded` `dag.py:103`) rather than running
   away. Today only step *timeouts* exist (`dag.py:929`) — this also caps runaway agent loops.
2. **Counts reuse → `saved_tokens`.** On a `"cached"` outcome (`dag.py:742`) or a KB/recall hit,
   add the *avoided* regeneration cost (estimated from the cached artifact's token size) to a
   running `saved_tokens`. Persisted onto `RunRecord.saved_tokens` at `_persist_run`.
3. **Honors gates.** A step with `gate: "human"` writes an approval row to the `tasks` table
   (`store.py:93`), sets the plan/run `gate_state = "awaiting:<step_id>"`, **suspends** by leaving
   the gated step non-`done` and persisting the plan (`plans` table, `store.py:100`), and returns.
   On approval, a resume route re-enters `run_dag` and **resume-from-last-good** (`dag.py:901`)
   picks up exactly where it stopped. The only genuinely new mechanism is the *synchronous*
   awaiting-state + resume route; the persist + resume substrate already exists.

Both `_persist_run` sites must learn the new fields: `orchestrator.py:339` (legacy path) **and**
`web/app.py:1399` (web path).

## 5. Authoring — a guided builder on the existing author/run seam

Author and run are already split (forms + `/personas` + `/settings/prompts` author; `dag.py` runs).
v-next adds a `/workflows/new` guided flow: **Name → Domain → Inputs (bind KB entry + instruction) →
Steps → Review**. Prose→structured-step conversion uses the existing LLM gateway: type *"compare
each competitor's pricing, stop when all 5 covered, max 8k tokens each"* → store
`{op: "compare", complete_when: "5_covered", budget_tokens: 8000}`. Authoring writes a new Workflow
**version**; it runs nothing. (Mirrors the Set Piece Sage, minus the metaphor.)

## 6. Result + library surface (`src/sentinel/web/render.py`, ~5900 lines)

- Run/result page gains a **Cost / Savings readout**: *"this run: 18k tokens · saved ~52k by reusing
  4 KB findings."* Renders from `RunRecord.cost_tokens`/`saved_tokens`. (There is already a "Backend
  usage" card at `render.py:649` — extend that region, don't add a competing one.)
- The live timeline shows a **⏸ awaiting-approval** state when a gate fires.
- `/workflows` library lists saved workflows, each with its **maturity chip** + version + re-run.

## 7. Out of scope / unchanged (the moat)

Dual-tier Gemma engine, public/private boundary + provenance, KB crawler→embed→rerank pipeline,
async run orchestration, agent timeline animation. The Rūmz metaphor vocabulary
(Props/Plots/Sym/Beans/Hall) is **not** adopted — plain language only.

## 8. Risks & open questions (carried into Plan)

- **OQ-1 (token capture):** does ADK `LiteLlm` reliably surface `usage`, or do streamed vLLM
  responses drop it (forcing the tokenizer-estimate fallback)? Decide in SENTINEL-017 step 1; a spike.
- **OQ-2 (savings calibration):** how to fairly price an "avoided regeneration" in tokens? Rūmz
  concedes this is "calibration-owed" (§5.9). v1 = size of the reused artifact in tokens; label the
  number "estimated."
- **OQ-3 (gate persistence horizon):** can run state survive a multi-hour/day suspend given the 12h
  session TTL? The `plans`/`tasks` tables are durable and session-independent, so the *state* is
  fine; the open piece is the resume *trigger* (a route the user hits, not session-bound). Confirm
  no run handle is pinned to the originating session.
- **Risk (two `_persist_run` sites):** the legacy (`orchestrator.py`) and web (`web/app.py`) paths
  must stay in lockstep on the new fields or the dashboard double-counts/under-counts. Mitigation:
  a shared helper that builds the field dict, called by both.
