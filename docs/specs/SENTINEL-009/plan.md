# SENTINEL-009 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered; each step ends green. No live LLM/network in any test (state seeded / models
introspected). Test IDs → spec ACs. Baseline: **145 tests green** (SENTINEL-005).

---

### Step 1 — Schemas: action plan, objection, overlay
Add `RecommendedAction`, `Objection`, `StrategyOverlay` to `artifacts/schemas.py`; extend
`Battlecard` (`assessment`, `action_plan`) and `AccountBrief` (`assessment`, `action_plan`,
`objection_handling`) with default-empty fields; docstring-flag legacy fields (OQ-1).
**Test (AC-1/2):** models construct; a default `Battlecard()`/`AccountBrief()` has empty/None new
fields; `SCHEMA_FOR_MODE` unchanged.

### Step 2 — Playbook loader + shipped playbooks
NEW `strategy/playbooks.py` (`Playbook`, `load_playbook`, `discover_playbooks`, fail-soft frontmatter
parse via `yaml.safe_load`). NEW `playbooks/account-strategy.md` + `playbooks/competitor-counterplay.md`
(each with the AC-12 house rule).
**Test (AC-6/9):** loads both shipped playbooks (`mode` correct, non-empty `body`); a tmp malformed
`.md` → `None` (no raise); `discover_playbooks` lists exactly the valid ones.

### Step 3 — Config: StrategyConfig + agent keys + prompts + reserved vars
`config/schema.py`: `StrategyConfig` (default off) + `strategy` on `SentinelConfig`. `defaults.py`:
seed from `SENTINEL_STRATEGY`; add `competitor.strategist`/`client.strategist` agents (no
`pin_gemini`) + prompts (read `{battlecard}`/`{account_brief}`). `config/render.py`: add
`battlecard`, `account_brief` to `RESERVED_VARS`.
**Test (AC-2):** default cfg `strategy.enabled is False`, round-trips through YAML; new prompts
validate via `render_prompt` (reserved vars accepted); new agent keys present.

### Step 4 — Builder: `maybe_strategist` + mode wiring
`agent/modes/_build.py`: `maybe_strategist(cfg, mode, *, backend, cloud_allowed)` (returns None when
disabled; loads playbook → `instruction_suffix`; tool-free; `output_schema=StrategyOverlay`).
`competitor.py`/`client.py`: append it when present.
**Test (AC-3/4/5/7/8):** `enabled=False` → pipeline has no strategist + synthesizer instruction
byte-identical to default; `enabled=True` → last sub-agent is `<mode>_strategist`, `output_schema is
StrategyOverlay`, no tools; playbook body appears in `.instruction`; editing the tmp playbook changes it.

### Step 5 — Sovereignty introspection (governance reuse)
Confirm `maybe_strategist` passes `cloud_allowed` through `make_agent`→`resolve_model` (no new code if
Step 4 wired it; this step is the **proving test**).
**Test (AC-11):** with `compliance_mode="on_prem_required"`, build each mode with `cloud_allowed=False`
→ strategist `.model` is a vLLM/LiteLlm object, not a str; no Gemini object anywhere in the pipeline.

### Step 6 — Orchestrator merge
`agent/orchestrator.py`: `_merge_strategy(artifact, state)`; call it (guarded by
`cfg.strategy.enabled`) between coerce and `writer.write`; append the trace note. Fail-soft on missing
/ malformed overlay.
**Test (AC-10):** `_merge_strategy(brief, {"strategy": overlay})` populates `assessment`/`action_plan`/
`objection_handling`; missing `strategy` key → artifact unchanged + `"strategy: none"` trace; bad
overlay → `"strategy: skipped (...)"`, run not broken (NFR-3).

### Step 7 — Render: markdown writer + dashboard
`artifacts/writer.py` + `web/render.py`: conditional Assessment / Action-plan table (sorted high→low)
/ Objection-handling sections; omit when empty.
**Test (AC-13):** writer output contains the action table + assessment when populated; contains
neither header when empty (no empty sections); dashboard render escapes text.

### Step 8 — Settings: Strategy section
`web/settings.py` `apply_strategy` (validate enabled bool, playbook stems exist in `playbook_dir` via
`discover_playbooks`); `web/render.py` Strategy section (toggle, dir, per-mode select); `app.py` route
`/settings/strategy`.
**Test (AC-14):** POST `/settings/strategy` persists `strategy.*` to YAML; no secret in YAML/HTML; bad
playbook stem → error banner; section renders current values.

### Step 9 — Housekeeping + no-regression
Docstrings; flip an end-to-end strategy run in a test (seeded overlay) to assert merged artifact is
written; update `MEMORY.md`, `specs/README.md` (009 → Built), `.remember`.
**Test (AC-14):** full `SENTINEL_DATA_DIR=$(mktemp -d) .venv/bin/python -m pytest -q` green;
SENTINEL-002 boundary + 003/004 tests untouched.

---

## Definition of done

AC-1..AC-14 green. With `strategy.enabled=False` the system is byte-identical to SENTINEL-004 (ships
dark). With it on, every brief gains a cited `assessment` + a prioritized `action_plan` (+ client
`objection_handling`) shaped by an **admin-editable Markdown playbook**, produced by a **tool-free
strategist** that in `on_prem_required` runs on **Gemma/vLLM with zero Gemini** — provable by
introspection. An admin changes house strategy by editing a `.md`, effective next run.

## Estimate

~9 steps. Heaviest: the playbook loader + builder wiring (Steps 2/4) and the render surfaces (Step 7).
Risk is low — additive, dark by default, and the sovereignty guarantee is inherited from the
already-built SENTINEL-005 seam rather than re-implemented.
