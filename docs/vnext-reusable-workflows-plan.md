# Sentinel v-next — Reusable Workflows: Program Plan

**Status:** Plan. Implements [`vnext-reusable-workflows-design.md`](./vnext-reusable-workflows-design.md).
**Date:** 2026-06-14
**Shape:** one program, four tasks (SENTINEL-017…020). Each task is independently shippable and
demo-able. No code starts until its task has a `spec.html` + `design.html` + `plan.html` scaffold
(per CLAUDE.md no-vibe-coding rule) — this program plan seeds those scaffolds.

---

## Dependency graph

```
        SENTINEL-017  Cost/Savings readout ─────────────┐ (soft: budget-cap-as-gate)
        (metering + RunRecord cols + render)            │
                                                        ▼
  SENTINEL-018  Workflow library ──────►  SENTINEL-020  Human-approval gate
  (Workflow/WorkflowInput, CRUD,          (suspend/resume, approval task, route)
   versioning, /workflows UI)
        │
        ▼
  SENTINEL-019  Maturity chips
  (Workflow.maturity + render)
```

- **017 ∥ 018** — independent; can run in parallel (different files: 017 = telemetry/schema/render
  region; 018 = new models/tables/routes). **Recommended build order: 017 first** (lowest risk,
  highest pitch value, no new tables).
- **019 depends on 018** — the chip is a field on `Workflow`.
- **020 depends on 018** (a gate is a property of a Workflow step) and **soft-depends on 017** (budget
  metering enables "budget-cap-as-gate"). Build 020 last — it's the only real engine change.

Critical path: **018 → 020**. 017 and 019 are off-path and can ship anytime after their dep.

---

## SENTINEL-017 — Cost/Savings readout  *(no new tables; ~6 steps)*

**Goal:** every run records and the result page shows tokens spent + tokens saved by reuse.

1. **Spike (OQ-1):** confirm whether ADK `LiteLlm` responses surface `usage`
   (`prompt_tokens`/`completion_tokens`) in `orch.run_step`. Decide: real usage vs. tokenizer
   estimate. Output: a one-paragraph note + the chosen capture call. *(timeboxed; no prod code)*
2. **Capture:** thread `tokens_in`/`tokens_out` from the run-step boundary into `_StepOutcome`
   (`dag.py:87`, beside `reasoner_delta`); fold a token sum in the scheduler (`dag.py:991`).
3. **Record:** pass the captured counts into the two `TelemetryEvent(...)` calls (`dag.py:268`,
   `orchestrator.py:755`) so `telemetry_events.tokens_in/out` stop being 0.
4. **Schema:** add `cost_tokens`/`saved_tokens`/`gate_state` to `RunRecord` (`schema.py:124`);
   append three tuples to `_RUN_MIGRATIONS` (`store.py:288`); extend the `INSERT` (`store.py:910`)
   and `_row_to_run` (`store.py:~369`, defensive `_col`). `gate_state` defaults `""` (used by 020).
5. **Savings calc:** in the scheduler, on `"cached"` (`dag.py:742`)/KB-recall hits, accumulate the
   avoided-regeneration estimate → `RunRecord.saved_tokens`. Persist via **both** `_persist_run`
   sites through one shared field-builder helper (mitigates the lockstep risk).
6. **Render:** extend the "Backend usage" card (`render.py:649`) with "this run: N tokens · saved ~M
   by reusing K findings."

**Tests:** unit — migration idempotency (run twice, one column set); capture fold sums correctly;
savings accumulates only on reuse; pre-migration row loads with defaults. Render — readout present +
formats zero/large values. **Acceptance:** a fresh run shows a non-zero cost; a re-run that hits
cache shows non-zero savings; old rows render "—" not a crash.

## SENTINEL-018 — Reusable Workflow library  *(2 new tables; ~9 steps)*

**Goal:** users save, version, list, and re-run workflows; instructions ride KB bindings.

1. **Model:** `Workflow` + `WorkflowInput` (design §3.3). Keep `Playbook` as a thin alias/adapter
   during migration so existing playbook callers don't break.
2. **Store:** `workflows` + `workflow_inputs` tables on the `agent_specs` pattern (`store.py:112`):
   scalar lookup columns + JSON `data`; `(id, version)` composite; "current" = max version.
3. **CRUD:** `create_workflow`, `get_workflow(id, version=None)`, `list_workflows(project_id)`,
   `new_version(id, …)` (append-only — never UPDATE in place). Replaces `playbooks.py` loaders.
4. **Binding:** `WorkflowInput{kb_entry_id, instruction}` resolution — fetch the canonical KB entry,
   attach the edge instruction at run assembly (NOT concatenated into KB text). The
   instruction-on-the-binding refactor.
5. **Run integration:** `run_dag` can execute a `Workflow`'s `steps[]` (op/instruction/inputs/
   budget/complete_when) — map to the existing plan/step shape.
6–9. **UI:** `/workflows` list, `/workflows/new` guided builder (Name→Domain→Inputs→Steps→Review,
   design §5), prose→step conversion via the gateway, re-run from library, version history view.

**Tests:** versioning is append-only (edit → new row, old preserved); `get_workflow` returns current
by default + pinned version on request; binding resolves the canonical KB entry once across two
workflows; a saved workflow re-runs and produces a `RunRecord`. **Acceptance:** author → save →
appears in `/workflows` → re-run → second version preserves the first.

## SENTINEL-019 — Maturity chips  *(no new tables; ~3 steps)*

**Goal:** honest built/beta/experimental signaling on workflows + the domain matrix.

1. `Workflow.maturity` field (already in the 018 model; this task surfaces it end-to-end).
2. Render the chip on `/workflows` cards and the result header.
3. Seed maturity from the 9-domain × 6-persona matrix honesty (3/9 e2e-tested = "built", rest
   "beta"/"experimental"). Cross-ref `memory/sentinel-usecase-matrix.md`.

**Tests:** chip renders per value; default = "experimental" for un-labeled. **Acceptance:** the
matrix's tested/untested split is visible in the UI, not buried in a memory file.

## SENTINEL-020 — Human-approval gate  *(reuses tasks/plans tables; ~7 steps — the real engine work)*

**Goal:** a step can suspend the run for human approval and resume in place.

1. **Status enum:** extend step statuses (`done|cached|failed|skipped`) with `awaiting_gate`
   (`dag.py` `_SATISFIED`/status sites). `awaiting_gate` is NOT in `_SATISFIED` → scheduler stops.
2. **Gate fire:** a `gate:"human"` step writes an approval row to `tasks` (`store.py:93`), sets
   run/plan `gate_state="awaiting:<step_id>"`, persists the plan (`plans`, `store.py:100`), returns.
3. **Suspend semantics:** the run ends in a `suspended` state, not `failed`/`done`; dashboard +
   timeline show ⏸ awaiting-approval (design §6).
4. **Approve/reject route:** `/workflows/runs/<id>/gate` POST → on approve, set the gated step to a
   resumable state + `gate_state="approved:<step_id>"`; on reject, mark rejected + stop.
5. **Resume:** re-enter `run_dag`; **resume-from-last-good** (`dag.py:901`) continues from the gated
   step. Verify no run handle is pinned to the originating session (OQ-3).
6. **Budget-cap-as-gate (soft dep on 017):** optionally, a `budget_tokens` breach can *escalate to a
   human gate* instead of just degrading — reuses the same suspend path.
7. **Persistence horizon:** confirm a suspended run survives a process restart (state is in
   `plans`/`tasks`, both durable) — the test that proves OQ-3.

**Tests:** a gated run suspends (not fail); approve → resumes + completes; reject → stops clean;
suspended state survives a simulated restart (reload from `plans`); resume runs only post-gate steps
(resume-from-last-good honored). **Acceptance:** author a workflow with a human gate → run → it pauses
→ approve in the UI → it finishes; the timeline shows the pause.

---

## Cross-cutting

- **Anti-Pattern #1 defense (reuse before build):** 017 reuses `telemetry_events`/`TelemetryEvent`
  (don't add a parallel table); 018 reuses the `agent_specs` storage idiom; 020 reuses
  `plans`/`tasks` + resume-from-last-good (don't write a new state machine).
- **No `Any`, no banned vocab, compliance:** all metering is local/tokenizer-based — **zero new
  external calls**, so no ADR needed even under `on_prem_required`.
- **The lockstep invariant:** both `_persist_run` sites (`orchestrator.py:339`, `web/app.py:1399`)
  go through one shared field-builder for the new RunRecord fields. Asserted by a test that runs both
  paths and diffs the persisted record shape.
- **Sequencing recommendation:** ship **017 → 018 → 019 → 020**. 017 strengthens the sovereign-cost
  pitch immediately with the least risk; 020 (the only real engine change) lands last with the most
  test coverage.

## Ready-to-start gate

Each task needs its `/docs/specs/SENTINEL-0NN/{spec,design,plan}.html` scaffold before Build.
Next action when approved: `/biltiq-engineering:new-task SENTINEL-017` (then think→plan→build the
loop), or run the Attack Loop directly. **Recommended first:** SENTINEL-017.
