# Sentinel v-next — Reusable Workflows, Cost/Savings, Gates

**Status:** Think-stage design note (pre-spec) — SUPERSEDED for build by the finished
[design](./vnext-reusable-workflows-design.md) + [program plan](./vnext-reusable-workflows-plan.md)
(2026-06-14; full v-next, tasks SENTINEL-017…020). Kept for the original reasoning trail.
**Date:** 2026-06-14
**Origin:** Design study of the Rūmz *Set Piece & Promptbook* mockups + spec v1.2
(`~/Desktop/psyos-hcs/proptbook/files (9)/`). We borrow four patterns, drop the
theatrical metaphor, and keep plain language.

---

## 1. The shift

Today a research run is **code-defined**: pick a domain (`ResearchModeSpec`), a persona,
hit run, `run_dag` executes a fixed pipeline. The user cannot save a run as a reusable
template, never sees what it cost, and never sees what reuse saved.

v-next: a run is driven by a **saved, user-authored Workflow** that carries its own steps,
a cost budget, and optional human gates — and every run writes back **cost** and
**reuse-savings**. This is a *surface + reuse-accounting* layer over the existing engine,
**not a new engine**. The dual-tier Gemma sovereign core, the public/private boundary +
provenance (our real moat — Rūmz has no equivalent), KB pipeline, async runs, and the live
timeline are all unchanged.

## 2. The four borrows (and why)

| # | Borrow | Rūmz term | Sentinel status today | Net |
|---|---|---|---|---|
| 1 | **Cost + Savings readout** | Bean Counter | latency telemetry wired; token columns exist but **always 0**; **0 cost UI** | connect token capture into the existing (empty) schema → aggregate → savings calc → render |
| 2 | **Reusable Workflow library** | Promptbook / Set piece | workflows = code; `playbooks.py` is the seed (read-only) | promote to CRUD + versioning |
| 3 | **Maturity chip** | honesty legend (built/conceptual/owed) | none | trivial, high-trust (our 9-domain matrix is only 3/9 e2e-verified) |
| 4 | **Human-approval gate (suspend/resume)** | Cue → human gate | async prospective tasks only (`dag.py` G-09) | the one net-new engine bit — puts us *ahead* of the Rūmz spec (it lists suspend/resume as *owed*) |

**Cost-lead thesis (the spine).** Rūmz spec §5.9/§8.3: *"retrieval beats generation; an
authored-once procedure removes the re-derivation cost on every run."* Sentinel already does
the hard part — KB + episodic + semantic recall, `_persist_run` finding reuse. We just never
**count and show** the savings. That number *is* the sovereign-cost pitch.

## 3. Data model — mostly promotion of what exists

Real anchors:
- `RunRecord` — `src/sentinel/memory/schema.py:124` (no cost/savings fields today)
- `RunStore` / `_persist_run` — `src/sentinel/memory/store.py`, `orchestrator.py`, `web/app.py`
- Playbooks — `src/sentinel/strategy/playbooks.py` (`load_playbook`, `discover_playbooks`; **no CRUD, no versioning**)

```
Workflow  (NEW — promotes Playbook)        belongs to Project (RunRecord.project_id exists)
  ├─ steps[]   : {op, instruction, inputs[], budget_tokens, gate, complete_when}
  ├─ version   : append-only — edit = new version, never mutate in place (spec §4.6)
  └─ maturity  : built | beta | experimental     ← the honesty chip

WorkflowInput  (NEW — the "binding")
  └─ {kb_entry_id, instruction}    ← instruction lives on the EDGE, not baked into KB text

RunRecord  (EXTEND schema.py:124)
  └─ + cost_tokens: int, saved_tokens: int, gate_state: str   (default 0 / "")
```

**Key principle (spec §3.4/§4.3 — "Elemental + instruction-on-the-binding"):** a KB entry
stays **canonical and immutable**; the per-step instruction ("use this as the competitor
template") rides the `WorkflowInput` binding. The same KB entry feeds N workflows with N
instructions, zero duplication. This is a concrete refactor away from baking instructions
into prompt text.

## 4. Run lifecycle — `run_dag` stays the engine, three additions

Per step, `run_dag` additionally:
1. **Meters** token spend against `budget_tokens`; on cap, **halt or escalate** instead of
   running away (today we have step *timeouts* only — this also caps runaway agent loops).
2. **Checks reuse**: on a KB/recall hit, skip regeneration and add the avoided cost to
   `RunRecord.saved_tokens`. Savings = sum of avoided regeneration cost. Computed from data
   `_persist_run` already writes.
3. **Honors gates**: a step with `gate: human` issues an approval task (reuse the
   `tasks`-like prospective mechanism already in `dag.py` G-09 — `due_at` /
   `trigger_condition` / `action_hint`), **suspends** the run, persists DAG state, and
   **resumes** on approval. Suspend/resume of DAG state is the only genuinely new engine work.

## 5. Authoring — guided builder on the existing author/run seam

Author/run is already split (forms + `/personas` + `/settings/prompts` vs `dag.py`). v-next
adds a `/workflows/new` guided flow: **Name → Domain → Inputs (bind KB + instruction) →
Steps → Review**. The prose→structured-step conversion uses the existing LLM gateway: type
*"compare each competitor's pricing, stop when all 5 covered, max 8k tokens each"* → store
`{op: compare, complete_when: 5_covered, budget_tokens: 8000}`. Authoring writes a new
Workflow **version**; it runs nothing.

## 6. Result surface

- Run/result page gains a **Cost / Savings readout**: "this run: 18k tokens · saved ~52k by
  reusing 4 KB findings."
- Live timeline shows a **⏸ paused-for-approval** state when a gate fires.
- Each workflow in the library shows its **maturity chip**.

## 7. Sequencing (each independently shippable + demo-able)

1. **Cost/Savings readout** — pure read + render, no schema migration beyond two
   `RunRecord` columns. Highest ROI, lowest risk. Strengthens sovereign pitch immediately.
2. **Workflow library** — promote `playbooks.py` to CRUD + append-only versioning + re-run.
   This is the self-serve spine flagged P0 in the GTM doc.
3. **Maturity chips** — trivial; honest expectation-setting on the 3/9-tested matrix.
4. **Human-approval gate** — real engineering (suspend/resume DAG state); compliance unlock
   for regulated buyers; puts us ahead of the Rūmz spec.

## 8. Explicitly out of scope / unchanged

Dual-tier Gemma engine, public/private boundary + provenance, KB crawler→embed→rerank
pipeline, async run orchestration, agent timeline animation. The Rūmz metaphor vocabulary
(Props/Plots/Sym/Beans/Hall) is **not** adopted — plain language only.

## 9. Open questions for Plan stage

- Savings calibration: how do we price an "avoided regeneration" in tokens fairly?
  (Rūmz concedes this is "calibration-owed" — §5.9.)
- Workflow versioning store: extend the Playbook model in-place, or new table?
- Gate persistence: can current async run state survive a multi-hour/day suspend, given the
  12h session TTL? (May need a durable run-state store independent of session.)
