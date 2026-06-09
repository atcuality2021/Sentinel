# SENTINEL-004 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture overview

Pure read/aggregate layer over the two SQLite tables SENTINEL-002 already populates, plus one
destructive control (purge) that reuses the existing `MemoryStore.purge_entity`. No new tables, no
new agent code, no change to `recall` or the boundary invariant.

```
GET /accounts ─────▶ RunStore.entities()                 → accounts_page          (AC-1, AC-2)

GET /accounts/{e} ─▶ RunStore.runs_for(e)                → timeline
                  ─▶ MemoryStore.list_for_entity(e)      → public + private memory (read-only, AC-5)
                  ─▶ (cumulative provenance from runs)    → account_detail_page    (AC-3,4,6)
                     unknown e (no runs, no memory)        → not_found_page         (AC-9)

POST /accounts/{e}/purge ─▶ MemoryStore.purge_entity(e)  → redirect /accounts      (AC-7, AC-8)
```

The one subtle design decision is **why the account page does not call `recall`**. `recall` is the
*agent* memory path: it is mode-gated (a competitor run sees only PUBLIC), it **reinforces on read**
(testing effect), and it truncates to a token budget. None of that is correct for a human browsing an
account — they should see everything, unchanged, with provenance visible. So we add a separate,
read-only `list_for_entity` **inside the store module** (raw SQL stays encapsulated — the "no table
reads outside the store" rule holds) that does no reinforcement, no budgeting, and no mode gate.
`recall` remains the single agent choke-point; the boundary invariant is untouched.

## 2. New store methods (`memory/store.py`, `memory/schema.py`)

```python
# schema.py — a small read-model for the index (RunStore-derived; no memory dependency)
class EntitySummary(BaseModel):
    entity: str            # normalized key (URL)
    display_name: str      # most-recent RunRecord.target
    runs: int
    last_run_at: datetime
    public: int            # cumulative across runs
    private: int
    modes: list[str]       # distinct modes seen (e.g. ["competitor"])
    kinds: list[str]       # distinct artifact kinds

# store.py
class RunStore:
    def entities(self) -> list[EntitySummary]: ...     # GROUP BY entity, ORDER BY max(created_at) DESC
    def runs_for(self, entity: str) -> list[RunRecord]: ...  # WHERE entity=? ORDER BY created_at DESC

class MemoryStore:
    def list_for_entity(
        self, entity: str, *, allowed: Iterable[DataBoundary] | None = None,
        include_quarantined: bool = False,
    ) -> list[MemoryEntry]:
        """Read-only memory for HUMAN DISPLAY. No reinforcement, no budget, no mode gate.
        NOT the agent path — never inject this into a prompt; agents use recall()."""
```

`entities()` is a single aggregate query: `SELECT entity, COUNT(*), MAX(created_at), SUM(public),
SUM(private) … GROUP BY entity`. `display_name`/`modes`/`kinds` come from a small per-entity follow-up
(or `GROUP_CONCAT`) — cheap at pilot scale. `list_for_entity` mirrors `recall`'s SQL **minus** the
reinforcement/budget/sort-by-decay; it sorts by `created_at DESC` (or strength desc) and returns all
matching rows. The read-only guarantee (AC-5) is structural: the method issues only `SELECT`.

## 3. Routes (`web/app.py`)

| Method | Path | Effect |
|---|---|---|
| GET | `/accounts` | `accounts_page(RunStore().entities())` |
| GET | `/accounts/{entity}` | detail: `runs_for` + `list_for_entity`; not-found if both empty |
| GET | `/accounts/{entity}?confirm=purge` | detail with the purge confirm panel revealed |
| POST | `/accounts/{entity}/purge` | `purge_entity`; redirect `/accounts?ok=…` |

`{entity}` is treated as a normalized key: the route calls `normalize_entity` on the inbound value so
a link built from a summary's `entity` round-trips, and a hand-typed mixed-case name still resolves
(AC-10). Not-found = no runs **and** no memory for the key (AC-9). All routes fail-soft: a store
exception renders the empty/unavailable state, never a 500 (NFR-6).

## 4. Rendering (`web/render.py`)

Three new functions, reusing the existing shell, cards, table, badges, and donut:

- `accounts_page(*, accounts: list[EntitySummary], backend)` — a `.card` table: Account (link) ·
  Modes · Runs · Public/Private badges · Last run. Empty state mirrors `artifacts_page`.
- `account_detail_page(*, summary, runs, public_mem, private_mem, backend, ok="")` —
  - Header card: display name, modes/kinds pills, runs count, last run; a cumulative provenance donut
    (reuse `_aside`'s Chart.js pattern) fed by summary.public/private (AC-6).
  - **Run timeline**: a table (newest first) — Mode · Backend · Public/Private/Gaps badges ·
    Saved-to · When (reuse the dashboard row style).
  - **Accumulated memory**: two sections via a shared `_mem_section("Public signal", entries)` /
    `_mem_section("Private signal", entries)` helper — each entry boundary-badged, with a small
    strength/last-seen hint (`_mem_row`). Empty sections render nothing (AC-4).
  - **Danger zone**: a `.card.err`-tinted panel. Default state shows a "Purge account" link →
    `?confirm=purge`; confirm state shows the explicit `POST …/purge` button + a cancel link (AC-8).
- `not_found_page(*, what, backend)` — clean "no such account" card with a link back to `/accounts`.

Add `("accounts", "Accounts", "doc"/"users", "/accounts")` to `_NAV` (new `users` icon), and wire
`/` recent-runs + `/artifacts` rows to link their entity to `/accounts/{entity}`. All cfg/finding/
entity text escaped (NFR-5).

## 5. File-by-file

| File | Change |
|---|---|
| `src/sentinel/memory/schema.py` | NEW `EntitySummary` model |
| `src/sentinel/memory/store.py` | `RunStore.entities`, `RunStore.runs_for`, `MemoryStore.list_for_entity` |
| `src/sentinel/memory/__init__.py` | export `EntitySummary` |
| `src/sentinel/web/render.py` | `accounts_page`, `account_detail_page`, `not_found_page`, `_mem_section`/`_mem_row`, nav + `users` icon; link entities from dashboard/artifacts rows |
| `src/sentinel/web/app.py` | 3 routes (2 GET, 1 POST); fail-soft; normalized key |
| `tests/test_accounts.py` | NEW — AC-1..AC-11 (store methods + routes via TestClient) |

No changes to `recall`, extraction, strength, orchestrator, or config.

## 6. Testing strategy

- **Store (fast, tmp db via `SENTINEL_DATA_DIR`):** seed a few `RunRecord`s + `MemoryEntry`s across
  two entities; assert `entities()` collapses to one row per entity with correct counts/order;
  `runs_for` ordering; `list_for_entity` returns both boundaries and, crucially, **does not mutate**
  strength/access_count (AC-5 — read the entry, call the method, re-read, assert equal); `allowed=`
  filter narrows boundaries.
- **Routes (TestClient + tmp db):** `/accounts` lists/empties (AC-1/2); detail shows timeline +
  separated memory sections (AC-3/4); cumulative counts match (AC-6); unknown entity → not-found
  (AC-9); name with spaces/case round-trips + escapes (AC-10).
- **Purge (AC-7/8):** seed entity → `GET` detail (assert still present afterwards — safe method) →
  `POST …/purge` → assert absent from `/accounts` and detail is not-found. Assert no delete on the
  `?confirm=purge` GET.
- **No-regression (AC-11):** full suite; `recall` untouched; reuse the SENTINEL-002 boundary tests as
  the guard that the agent path is unchanged.

## 7. Risks & mitigations

- **R-1 boundary perception** — separate badged sections + read-only method + never-injected;
  `recall` stays the sole agent path. (spec R-1)
- **R-2 key vs name** — normalize on the way in; display latest `target`; round-trip test. (spec R-2)
- **R-3 destructive purge** — POST-only + confirm step + redirect; audit trail deferred to 005.

## 8. Rollback

Additive. Deleting the routes + page functions + the three store methods leaves 001/002/003
untouched. No schema migration (reads existing tables; `EntitySummary` is an in-memory read-model).
