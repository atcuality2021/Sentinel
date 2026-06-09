# SENTINEL-010 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered; each step ends green. Pure-code scoring — no LLM/network in any test (seeded tmp DB
+ injected `now`). Test IDs → spec ACs. Baseline assumes SENTINEL-009 green.

---

### Step 1 — Primitives + registry
NEW `priority/signals.py`: `normalize(value, low, high, invert)`, `half_life_decay(age_days,
half_life)`, the `_Signal` dataclass, `REGISTRY`, `register_signal(name, weight, fn, *, default)`.
**Test (AC-7):** `normalize` clamps + inverts; `half_life_decay` = 1 at age 0, 0.5 at one half-life,
→0 for large age; `register_signal` populates `REGISTRY`.

### Step 2 — Engine: context, score, normalization, isolation, clamp, tiering
NEW `priority/engine.py`: `PriorityContext`, `Reason`, `PriorityScore`,
`compute_account_priority(entity, *, allowed_boundaries, now, config)` — weight normalization,
per-signal try/except → default, clamp [0,100], tiering by thresholds. Reads via `RunStore` +
`MemoryStore.recall`.
**Test (AC-1/2/3/4/5):** returns a `PriorityScore` with no network; deterministic over repeats;
{2,2}≡{1,1} weights; a raising signal is isolated (score still returned, breakdown notes it); score
clamped to 100.

### Step 3 — Seed signals over existing data
In `signals.py`, register `recency`, `new_material`, `volume`, `private_engagement`,
`competitor_move`, each a small fn reading `ctx`. `private_engagement` counts only PRIVATE
`ctx.memory` (already boundary-filtered).
**Test (AC-8/10):** with a seeded entity, each signal returns [0,1]; scoring with
`allowed_boundaries={PUBLIC}` over seeded PRIVATE memory ⇒ `private_engagement==0` and no PRIVATE
reason; with `{PUBLIC,PRIVATE}` it contributes.

### Step 4 — Config: PriorityConfig
`config/schema.py`: `PriorityConfig{enabled, weights, hot_threshold, warm_threshold,
recency_half_life_days}`; add `priority` to `SentinelConfig`. Engine overlays `cfg.priority.weights`
on registry defaults.
**Test (AC-3/13):** default cfg has `priority` block, round-trips YAML; a `weights` override changes
the effective weighting; absent override uses registry defaults.

### Step 5 — Persistence
NEW `priority/store.py`: `PriorityStore` on the SENTINEL-002 SQLite file (`_ensure_schema` adds a
`priority` table); `save(PriorityScore)`, `latest_for(entity)`.
**Test (AC-11):** save then `latest_for` round-trips `score/tier/breakdown/reasons`; multiple saves
keep history (auditable); no collision with memory/run tables.

### Step 6 — Focus list route + dashboard card
`web/app.py` `/focus`: score every `RunStore().entities()` entity, sort desc, render rows (score,
tier, reasons with links) + a breakdown expander; dashboard "Top 5 to focus on" card. `render.py`
helpers; escape all text.
**Test (AC-9/12):** `/focus` returns 200 with seeded entities, highest score first, each row shows
reasons linked to a finding/run; single-entity compute timed < 200 ms.

### Step 7 — Housekeeping + no-regression
Docstrings (note: one registry, no parallel scorers — AC-6); update `MEMORY.md`,
`specs/README.md` (010 → Built), `.remember`.
**Test (AC-6/13):** a structural test asserts a single `register_signal`/`compute_account_priority`
public surface; full `SENTINEL_DATA_DIR=$(mktemp -d) .venv/bin/python -m pytest -q` green; SENTINEL-002
boundary + 004 index tests untouched.

---

## Definition of done

AC-1..AC-13 green. A BD lead opens `/focus` and sees their accounts ranked by who needs attention
now, each with a cited reason and an auditable per-signal breakdown — computed by **one deterministic
registry** (no LLM in the arithmetic), tunable by config, and **boundary-safe** (a public-only view
shows zero private-sourced reasons). The score is persisted for audit.

## Estimate

~7 steps. Heaviest: the engine + seed signals (Steps 2/3) and the focus-list render (Step 6).
Lower risk than 009 — no LLM, no new prompts, additive route; the boundary guarantee is inherited
from the SENTINEL-002 `recall` choke-point rather than re-implemented.
