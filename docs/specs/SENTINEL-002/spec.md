# SENTINEL-002 — Memory Harness & Persistence

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (config) · **Blocks:** SENTINEL-004 (Accounts)
**Borrows from:** BiltIQ Agent OS — see [`docs/borrowed-from-agent-os.md`](../../borrowed-from-agent-os.md)

---

## 1. Context / problem

Sentinel currently has **no memory**. The dashboard run store is in-process and dies on restart;
the agent learns nothing across runs; running the same account twice produces an identical brief
with no "what changed." A real pilot user expects the opposite: the second brief on *Acme Bank*
should open with *"Since your last brief 9 days ago: deal moved to negotiation; 2 new public
signals."* That requires durable, boundary-aware memory.

We borrow the proven shape from BiltIQ Agent OS (four memory systems, deterministic extraction,
SM-2 reinforcement, and — critically — its **boundary-filter-on-every-read + fail-closed-on-write**
discipline) and adapt it to Sentinel: SQLite/file storage, ADK callbacks, and a **two-value
`DataBoundary {PUBLIC, PRIVATE}`** instead of multi-tenant visibility.

## 2. Goal / non-goals

**Goal:** A durable memory harness that (a) persists every run (episodic), (b) accumulates a
per-entity profile across runs, (c) recalls relevant prior memory into a new run **without ever
letting PRIVATE memory enter a public-only context**, and (d) surfaces a "since last run" delta.
Memory respects the same public/private boundary the tool layer enforces — extending the
sovereignty guarantee into storage.

**Non-goals:**
- No vector DB (Qdrant) — trigger/FTS + content-hash dedup; embeddings optional later.
- No multi-tenant / RBAC / scopes.
- No org-preferences editor UI (the store supports it; editing is SENTINEL-003/004).
- No LLM-based extractor in v1 (deterministic only; a local-vLLM Tier-2 is a noted follow-up that
  fits the on-prem story).

## 3. Personas

P4 Account owner ("what changed since last time"), P1 Analyst (richer briefs), P3 Compliance
(boundary-safe memory, retention/purge), P2 Admin (memory config from SENTINEL-001 `MemoryConfig`).

## 4. The four memory systems (adapted)

| # | System | Sentinel form | Lifetime |
|---|---|---|---|
| 1 | Knowledge | the run artifacts themselves (battlecards/briefs on disk) | until deleted |
| 2 | **Agent/entity memory** | `MemoryEntry` rows per competitor/account, boundary-tagged | reinforced/decayed |
| 3 | Working memory | ADK session state (this run) — already exists | one run |
| 4 | Session/project | `MEMORY.md` (dev) — already exists | curated |

This task builds **System 2** and the **episodic run log**, and wires the System-2 ↔ run loop.

## 5. User stories

- **US-7.1** As an *Account owner*, re-running an entity shows a "Since last run" delta (new public
  signals, changed deal stage) derived from prior memory.
- **US-7.2** As an *Admin*, durable org/entity preferences are injected into synthesis (config-gated
  by `MemoryConfig.inject_org_prefs`).
- **US-7.3** As a *Compliance officer*, I can set retention and **purge an entity's memory**; and I
  am guaranteed PRIVATE memory never surfaces in a public-only (competitor) run.
- **US-2.1 (delta)** The dashboard reads runs from the durable store (survives restart).

## 6. Acceptance criteria (testable, binary)

- [ ] **AC-1** Every completed run is persisted as a `RunRecord` (target, mode, backend, counts,
  reference, timestamp) and survives process restart; the dashboard reads from it.
- [ ] **AC-2** `MemoryEntry` carries a `boundary: DataBoundary` (PUBLIC|PRIVATE), `memory_type`,
  `entity`, provenance, SM-2 strength fields, `content`, `created_at`, `quarantined`.
- [ ] **AC-3 (the boundary invariant)** `recall(entity, allowed_boundaries)` returns **only**
  entries whose boundary ∈ allowed. A competitor (public-only) run can never receive a PRIVATE
  entry — proven by a test that seeds a PRIVATE entry and asserts it is absent from a public recall.
- [ ] **AC-4 (fail-closed write)** A write with no/invalid boundary is **quarantined**, never stored
  as usable; quarantined entries are excluded from every recall.
- [ ] **AC-5** Turn-end extraction (deterministic) writes durable entries from a run's findings,
  each stamped with the boundary of its source finding (public finding → PUBLIC entry, etc.).
- [ ] **AC-6** Recall ranks by decayed SM-2 strength, drops below a floor, returns top-k within a
  token budget; reading an entry reinforces it (testing effect); unused entries decay.
- [ ] **AC-7** Dedup: a near-identical entry for the same entity+boundary is merged, not duplicated
  (content-hash / normalized match).
- [ ] **AC-8** "Since last run" delta: re-running an entity yields a structured delta vs the most
  recent prior run (added/changed findings), shown in the artifact and dashboard.
- [ ] **AC-9** Purge: `purge_entity(name)` removes its memory + run history; a subsequent recall is
  empty.
- [ ] **AC-10** Recall injection is config-gated (`MemoryConfig.entity_memory`); off ⇒ behaviour
  identical to today (no regression).
- [ ] **AC-11** All existing tests still pass; new tests cover AC-1..AC-10. No live LLM needed.

## 7. Functional requirements

- **FR-1** `DataBoundary` enum (PUBLIC, PRIVATE) reused from / aligned with `artifacts.schemas.Boundary`.
- **FR-2** `MemoryEntry` pydantic model + `RunRecord` model.
- **FR-3** `MemoryStore` (SQLite) with `recall`, `write`, `process_run` (extract→dedup→write),
  `reinforce_on_read`, `decay`, `purge_entity`; **every read filters by allowed boundaries and
  excludes quarantined**; every write is boundary-validated fail-closed.
- **FR-4** `RunStore` (SQLite, same db) for episodic records feeding the dashboard.
- **FR-5** Pure SM-2/Leitner `strength` kernel (no I/O) — borrowed shape.
- **FR-6** ADK integration: turn-start recall→inject (boundary = the run's allowed set: competitor ⇒
  {PUBLIC}; client ⇒ {PUBLIC, PRIVATE}); turn-end `process_run` write-back.
- **FR-7** Delta computation between a new run and the prior run for the same entity.
- **FR-8** Config: honor `MemoryConfig` (entity_memory, retention_days, inject_org_prefs).

## 8. Non-functional

- **NFR-1 (boundary safety)** PRIVATE memory in a public context is a P0 defect; the invariant is
  enforced at the store read path (not the caller) and covered by an adversarial test (AC-3).
- **NFR-2** Persistence survives restart; single-file SQLite under `data/` (gitignored).
- **NFR-3** On-prem compatible: no cloud calls; memory stays local (honors compliance mode).
- **NFR-4** Recall adds < ~50ms for a pilot-scale store; extraction is off the interactive path.
- **NFR-5** Typed, no `Any`; fail-soft (a memory error degrades to "no memory", never breaks a run).

## 9. Out of scope

Vector/semantic recall, LLM extractor, org-prefs editor UI, multi-tenant, audit log (→ 005).

## 10. Dependencies

SENTINEL-001 (`MemoryConfig`, config plumbing), stdlib `sqlite3`, pydantic. No new heavy deps.

## 11. Risks

- **R-1** Boundary leak via a recall path that forgets the filter. *Mitigation:* single choke-point
  read method; adversarial AC-3 test; no other code touches the table directly.
- **R-2** Deterministic extraction misses implicit learnings. *Accepted* for v1; local-vLLM Tier-2
  is a follow-up (fail-soft, off-latency) per ADR-012 pattern.
- **R-3** SQLite concurrency under the async web app. *Mitigation:* short-lived connections +
  WAL mode; writes are off the request path where possible.

## 12. Open questions

- **OQ-1** Delta granularity v1: just "new vs prior findings + mode/stage change", or also
  sentiment/score trends? *Proposed:* added/removed/changed findings + a one-line summary; trends later.
- **OQ-2** Entity identity: case-insensitive exact name match for v1 (no fuzzy/alias resolution)?
  *Proposed:* yes; alias resolution is a later increment.
