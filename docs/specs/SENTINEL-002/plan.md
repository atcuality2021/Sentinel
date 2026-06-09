# SENTINEL-002 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered steps; each ends green. Test IDs map to spec ACs. No live LLM in any step.

---

### Step 1 — `memory/schema.py`
`DataBoundary` (alias of `artifacts.schemas.Boundary`), `MemoryType`, `MemoryEntry`, `RunRecord`,
`MemoryDelta`. Add `content_hash` helper (normalized text → sha1).
**Test:** models instantiate; `content_hash` stable for normalized-equal text.

### Step 2 — `memory/strength.py`
Pure SM-2 kernel: `decayed_strength`, `reinforce` (POSITIVE diminishing→ceil, NEUTRAL no-op),
`STRENGTH_FLOOR/CEIL`.
**Test:** POSITIVE raises but never exceeds ceil; NEUTRAL is identity; decay decreases over time.

### Step 3 — `memory/store.py` schema + `RunStore`
SQLite init (WAL, create tables), `RunStore.save/list/latest_for/all`, `data_dir()`.
**Test (AC-1):** save 3 runs; reopen new store on same path; `list()` returns them newest-first.

### Step 4 — `MemoryStore.write` (fail-closed + dedup)
Insert with boundary validation; bogus boundary → `quarantined=True`; dedup on
(entity, boundary, content_hash) → reinforce existing instead of duplicate.
**Test (AC-4, AC-7):** bogus-boundary write is quarantined; duplicate write doesn't add a row but
bumps strength/access_count.

### Step 5 — `MemoryStore.recall` (THE boundary choke point)
SQL `WHERE entity=? AND quarantined=0 AND boundary IN (...)` + Python re-assert; rank by
`decayed_strength`; drop < floor; top-k; token-budget truncate; `reinforce_on_read`.
**Test (AC-3 adversarial, AC-6):** seed PRIVATE "Acme" entry → `recall("acme", {PUBLIC})` excludes
it; `recall("acme", {PUBLIC,PRIVATE})` includes it; reading reinforces; below-floor dropped.

### Step 6 — `memory/extraction.py`
`extract_entries(entity, artifact)` → one boundary-stamped entry per Finding (Battlecard PUBLIC;
AccountBrief public_signal PUBLIC, private_signal PRIVATE). `MemoryStore.process_run` calls it.
**Test (AC-5):** AccountBrief fixture → public entries PUBLIC, private entries PRIVATE; counts match.

### Step 7 — `memory/delta.py`
`compute_delta(prior_run, current_texts)` → added/removed/summary; None prior ⇒ "first run".
**Test (AC-8):** prior vs current finding sets → correct added/removed; first-run path.

### Step 8 — Orchestrator memory loop
allowed-boundary by mode; gated recall→`memory_context` via 001 note-substitution slot (empty when
disabled/empty); post-run `RunStore.save` + `process_run` + `compute_delta`; `RunResult.delta`.
Add `memory_context` to `render.RESERVED_VARS`; add the empty-safe `{memory_context}` slot to the
two synthesizer default prompts.
**Test (AC-10):** with `entity_memory=False`, built synthesizer instruction == SENTINEL-001 golden
(no regression); competitor run calls recall with `{PUBLIC}` only (mode→allowed mapping unit test).

### Step 9 — Dashboard durable + delta
Back `web/app.py` STORE with `RunStore`; render `MemoryDelta` on artifact + dashboard.
**Test:** web smoke — `/` reads from RunStore; a seeded run shows; delta block renders when present.

### Step 10 — Purge + decay + housekeeping
`purge_entity`, scheduled `decay`; `.gitignore += data/`; docstrings; update `MEMORY.md`.
**Test (AC-9):** purge removes entity memory + runs → recall empty. Full `pytest -q` green (AC-11).

---

## Definition of done
- AC-1..AC-11 covered by passing tests, including the **adversarial boundary test (AC-3)**.
- PRIVATE memory provably cannot enter a public-only run.
- Runs + memory persist across restart; "since last run" delta shows on re-run.
- `entity_memory=False` ⇒ byte-identical synthesis to SENTINEL-001 (no regression).
- Fail-soft: a memory/db error degrades to "no memory", never breaks a run.

## Estimate
~10 atomic steps. Unlocks SENTINEL-004 (Accounts pages). The load-bearing step is 5 (recall choke
point) — the boundary invariant is Sentinel's differentiator, now enforced in storage too.
