# SENTINEL-004 — Reports & Accounts

**Step:** Spec · **Status:** ✅ Built (2026-06-07, 17 tests; suite 109 green) · **Author:** 2026-06-07
**Depends on:** SENTINEL-002 (`RunStore`, `MemoryStore`, `RunRecord`, `MemoryEntry`, `compute_delta`)
**Blocks:** richer delta/timeline surfacing; SENTINEL-005 (audit/right-to-deletion builds on purge)

---

## 1. Context / problem

SENTINEL-002 made every run durable (`run_records`) and gave each researched entity an accumulating,
boundary-tagged memory (`memory_entries`). But the dashboard only exposes this as a **flat, global
run list** (`/artifacts`) — newest-runs-first across *all* targets. There is no way to answer the
question a pilot user actually asks: *"What do we know about **this** account, and how has it changed
across the times we've researched it?"*

The data to answer that already exists in SQLite. What's missing is an **entity-centric view**: an
Accounts index (one row per distinct target) and an Account detail page (run timeline + accumulated
memory + cumulative provenance). This is also where the "since last run" delta — currently shown once,
transiently, on a fresh artifact — becomes durable and browsable.

## 2. Goal / non-goals

**Goal:** Two new read surfaces plus a deletion control, all over the existing stores:
1. **Accounts index** (`/accounts`) — every distinct entity researched, with run count, last run,
   and cumulative public/private signal.
2. **Account detail** (`/accounts/{entity}`) — that entity's run timeline (newest first), its
   accumulated memory split into **Public** and **Private** sections, and a cumulative provenance
   chart.
3. **Purge** (`/accounts/{entity}/purge`) — operator-initiated, confirmed deletion of an entity's
   memory **and** run history (the data-subject "right to deletion" surface).

**Non-goals:**
- No editing of memory entries (no manual add/edit of findings — memory is agent-derived).
- No new agent behaviour; no change to `recall` or the boundary invariant.
- No auth / per-user scoping (single-operator pilot; audit log is SENTINEL-005).
- No cross-entity analytics beyond what the dashboard already shows.
- No export/download (later nicety).

## 3. Personas

P1 **Analyst** (primary — opens an account before a call to see everything known + what changed),
P2 **Admin** (reviews coverage across accounts), P3 **Compliance** (exercises purge for a
data-subject request; confirms private signal is clearly separated from public).

## 4. User stories

- **US-4.1** As an Analyst, I can see a list of **all accounts/competitors** I've researched, each
  with how many times and when last, so I can pick one.
- **US-4.2** As an Analyst, I can open an account and see **every run** against it in time order,
  with each run's public/private/gap counts and a link to its saved artifact.
- **US-4.3** As an Analyst, I can see the **accumulated memory** for an account, with **public and
  private signal clearly separated and badged**, so the sovereignty boundary is visible at a glance.
- **US-4.4** As an Analyst, **viewing** an account never changes what the agent remembers (looking is
  not reinforcement) — the page is a faithful, side-effect-free read.
- **US-4.5** As a Compliance officer, I can **purge** an account — removing its memory and run history
  — behind an explicit confirmation, and verify it's gone.
- **US-4.6** As any user, opening an **unknown** account shows a clean "not found", never a crash.

## 5. Acceptance criteria (testable, binary)

- [ ] **AC-1** `GET /accounts` lists each distinct entity exactly once, with run count, last-run time,
  and cumulative public/private finding totals; entities are ordered by most-recent activity.
- [ ] **AC-2** With no runs, `/accounts` renders an empty state (no crash, no empty table).
- [ ] **AC-3** `GET /accounts/{entity}` shows that entity's runs newest-first, each with mode, backend,
  public/private/gaps counts, saved-to reference, and timestamp.
- [ ] **AC-4** The detail page renders accumulated memory in **two labeled sections** — Public and
  Private — each entry boundary-badged; an entity with only public memory shows no private entries.
- [ ] **AC-5** Rendering the detail page is **read-only**: a memory entry's `strength` / `access_count`
  / `last_reinforced_at` are unchanged after the page is fetched (no reinforcement side-effect — the
  distinguishing property vs. `recall`).
- [ ] **AC-6** The detail page's cumulative provenance counts equal the sum of public/private across
  that entity's runs.
- [ ] **AC-7** `POST /accounts/{entity}/purge` deletes the entity's memory **and** runs; afterward the
  entity is absent from `/accounts` and its detail page returns the not-found view.
- [ ] **AC-8** Purge is **not** reachable by a safe method: a `GET` of the account page does not delete
  anything; deletion happens only via the explicit `POST` after a confirmation step.
- [ ] **AC-9** `GET /accounts/{unknown}` returns the not-found view (HTTP 200 page, not a 500).
- [ ] **AC-10** Entities whose names contain spaces / mixed case / punctuation route correctly
  (normalized key round-trips) and all entity/finding text is HTML-escaped (no stored XSS).
- [ ] **AC-11** All existing tests pass; `MemoryStore.recall` and the boundary invariant are unchanged
  (the new read path is display-only and never feeds an agent).

## 6. Functional requirements

- **FR-1** A `RunStore.entities()` aggregation returns one summary per distinct entity (display name,
  run count, last-run timestamp, cumulative public/private, modes/kinds seen).
- **FR-2** A `RunStore.runs_for(entity)` returns that entity's runs, newest-first.
- **FR-3** A `MemoryStore.list_for_entity(entity, *, allowed=None, include_quarantined=False)` returns
  entries for human display — **no reinforcement, no token budget, no mode gate** — optionally
  filtered to a boundary set. Lives in the store module (raw table access stays encapsulated).
- **FR-4** `/accounts` renders the index from `entities()`; `/accounts/{entity}` renders timeline
  (`runs_for`) + memory (`list_for_entity`) + a per-account provenance chart.
- **FR-5** Account links are wired from the dashboard "recent runs" and `/artifacts` rows to the
  matching `/accounts/{entity}`.
- **FR-6** Purge is a two-step control: the detail page surfaces a confirm affordance; `POST
  …/purge` calls `MemoryStore.purge_entity` and redirects to `/accounts`.
- **FR-7** A "Accounts" item is added to the sidebar nav.

## 7. Non-functional

- **NFR-1 (no side effects on read)** The account view must not reinforce or otherwise mutate memory
  (AC-5). It uses `list_for_entity`, never `recall`.
- **NFR-2 (boundary integrity)** Public and private memory are rendered in separate, badged sections;
  the mode-gated agent choke-point (`recall`) and the "table read only inside the store" rule are
  preserved. The display read path is never wired into agent context.
- **NFR-3 (safe methods)** No state change on `GET`; deletion only via `POST` with confirmation.
- **NFR-4** Server-rendered HTML, no JS framework (Chart.js CDN for the donut only), consistent shell.
- **NFR-5** Typed; no `Any`; all entity/target/finding text escaped.
- **NFR-6 (fail-soft)** A store error degrades to an empty/"unavailable" state, never a 500 in the UI.

## 8. Out of scope

Auth, audit logging (→005), manual memory editing, export/download, scheduled retention enforcement
(decay job exists in 002; surfacing/forcing it is 005), cross-entity comparison views.

## 9. Dependencies

SENTINEL-002 (`RunStore`, `MemoryStore`, `RunRecord`, `MemoryEntry`, `normalize_entity`,
`purge_entity`, `compute_delta`), existing web shell/render helpers, FastAPI path params, Chart.js.

## 10. Risks

- **R-1 (boundary bypass perception)** A human-facing view that shows *both* public and private memory
  could read as undermining the sovereignty thesis. *Mitigation:* it's an operator view, not an agent
  run; render public/private in **separate badged sections** (makes the boundary *more* visible);
  keep `recall` the sole agent path; the new method is read-only and never injected into a prompt.
  Documented loudly in code + design.
- **R-2 (entity key vs display name)** `entity` is normalized (lowercased, whitespace-collapsed) while
  `target` is the original display string. *Mitigation:* route by normalized key; display the most
  recent `target` as the name; round-trip tested (AC-10).
- **R-3 (accidental deletion)** Purge is destructive and irreversible. *Mitigation:* POST-only +
  explicit confirm step (AC-8); redirect + success banner; (audit trail lands in 005).

## 11. Open questions

- **OQ-1** Keep `/artifacts` as the global "Reports" list, or fold it into Accounts? *Proposed:* keep
  it (it answers "what shipped recently"); Accounts answers "what about this entity". Both link across.
  **Resolved (build):** kept `/artifacts`; its rows now link each target to `/accounts/{entity}` (FR-5).
- **OQ-2** Show decayed/low-strength memory on the account page? *Proposed:* show all non-quarantined
  entries with a strength indicator; don't hide decay — it's honest signal for the operator.
  **Resolved (build):** `list_for_entity` returns all non-quarantined entries (no floor), sorted
  strength-first; each row shows a `strength X.X · seen N×` hint. Decay is visible, not hidden.
