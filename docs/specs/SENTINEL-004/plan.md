# SENTINEL-004 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered steps; each ends green. Test IDs map to spec ACs. No live LLM in any step.
SENTINEL-004 is a read/aggregate layer over SENTINEL-002's tables plus one reused destructive op —
no changes to `recall`, extraction, strength, orchestrator, or config.

---

### Step 1 — `EntitySummary` + store read methods
Add `EntitySummary` to `memory/schema.py` (entity, display_name, runs, last_run_at, public, private,
modes, kinds). Add `RunStore.entities()` (GROUP BY entity, newest-activity first) and
`RunStore.runs_for(entity)` (newest first). Add `MemoryStore.list_for_entity(entity, *, allowed=None,
include_quarantined=False)` — **SELECT-only**: no reinforcement, no budget, no mode gate; docstring
states it is the human-display path, never the agent path. Export `EntitySummary` from
`memory/__init__.py`.
**Test (AC-1/3/5):** seed 2 entities × N runs + memory; `entities()` collapses + counts + order;
`runs_for` order; `list_for_entity` returns both boundaries; **read-only** — strength/access_count
unchanged after the call (the AC-5 guard); `allowed=` narrows.

### Step 2 — `render.accounts_page` + nav + `users` icon
New `accounts_page(*, accounts, backend)` — card table (Account link · Modes · Runs · Public/Private ·
Last run) + empty state. Add a `users` icon and `("accounts","Accounts","users","/accounts")` to
`_NAV`. Escape all entity/target text.
**Test (AC-1/2/10):** renders a seeded entity row + link; empty state when no runs; a name with
spaces/case appears escaped and links to its normalized key.

### Step 3 — `GET /accounts`
Route → `RunStore().entities()` → `accounts_page`. Fail-soft to empty state on store error.
**Test (AC-1/2):** 200 + lists distinct entities once; empty DB → empty state, no crash.

### Step 4 — `render.account_detail_page` + `not_found_page`
`account_detail_page(*, summary, runs, public_mem, private_mem, backend, ok="")`: header + cumulative
provenance donut (reuse `_aside` Chart.js), run-timeline table, and two memory sections via
`_mem_section`/`_mem_row` (boundary-badged, strength hint). Danger-zone panel: default shows a
"Purge" link to `?confirm=purge`; confirm state shows the `POST` button + cancel. `not_found_page`
for unknown entities.
**Test (render-level, AC-4/6/8):** detail HTML has both "Public signal"/"Private signal" sections with
correct badges; cumulative counts match the run sum; default danger panel has no POST form, the
`confirm` variant does.

### Step 5 — `GET /accounts/{entity}` (+ `?confirm=purge`)
Normalize the inbound key; gather `runs_for` + `list_for_entity` (split by boundary); render detail.
No runs **and** no memory → `not_found_page`. `?confirm=purge` reveals the confirm panel. Wire entity
links from the dashboard recent-runs + `/artifacts` rows.
**Test (AC-3/4/6/9/10):** detail 200 with timeline + memory; unknown → not-found (200, not 500);
spaces/case key round-trips; finding text escaped.

### Step 6 — `POST /accounts/{entity}/purge`
Normalize key → `MemoryStore.purge_entity` → redirect `/accounts?ok=…`. Safe-method guarantee: GET
never deletes.
**Test (AC-7/8):** seed entity → GET detail (still present after) → POST purge → absent from
`/accounts` + detail is not-found; `?confirm=purge` GET deletes nothing.

### Step 7 — Housekeeping
Docstrings; confirm `recall` + boundary tests untouched; update `MEMORY.md`, `docs/specs/README.md`,
`.remember/remember.md`.
**Test (AC-11):** full `pytest -q` green; SENTINEL-002 boundary tests still pass (agent path intact).

---

## Definition of done
- AC-1..AC-11 covered by passing tests (store + routes via TestClient with `SENTINEL_DATA_DIR` tmp).
- An operator can browse accounts, open one, read its full timeline + boundary-separated memory, and
  purge it behind a confirm — with no agent-path or boundary-invariant change.
- The account view is provably side-effect-free (AC-5) and never feeds memory into a prompt (AC-11).
- Unknown entities and store errors degrade gracefully; all text escaped.

## Estimate
~7 atomic steps. Most logic is three SELECT-based store methods (Step 1, carries the AC-5 read-only
test) + presentation; purge reuses existing `purge_entity`.
