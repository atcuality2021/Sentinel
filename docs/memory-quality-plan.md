# Memory Quality — Implementation Plan (both targets)

**Status:** Plan. Applies [`memory-system-architecture`](../../.claude/projects/-home-atc-Desktop-Sentinel/memory/memory-system-architecture.md)
(agent-memory head) to two concrete targets.
**Date:** 2026-06-14
**Goal stated by dev:** fix the memory problem AND improve the quality issue.
**Two targets:** (B) Sentinel **product** memory — the *quality* win; (A) the **agent** write-hook —
the *reliability* win.

---

## Finding — Sentinel product memory is ~70% there

Verified against the tree 2026-06-14:

| Architecture rule | Sentinel today | Status |
|---|---|---|
| Recall reads only live heads | `recall()` filters `quarantined=0` (`store.py:420/441`) — **quarantine = the not-live tier** | **DONE** |
| Exact-dup → drop / reinforce | `add` dedups by `content_hash` → SM-2 reinforce (`store.py:517`) | **DONE** |
| Detect same-topic conflict | G-10 logs a `memory_conflicts` row (`store.py:542`) | **DONE (detect only)** |
| **Auto-resolve → one live head** | none — conflict sits **advisory**; both entries stay non-quarantined | **MISSING** |
| **Policy: newer + more trusted wins** | `resolve_conflict(keep="a")` (`store.py:609`) — arbitrary default | **MISSING** |
| Loser kept as history w/ replaced-by link | loser quarantined on manual resolve, but **no `superseded_by` link** | **PARTIAL** |
| Curator + golden-question safety | none | **MISSING** |

**The quality defect:** between a conflict being logged and a human calling `resolve_conflict`, `recall()`
returns **both** contradicting findings → a research output can cite two opposite "facts" about one entity.
The fix is small because the demotion machinery (quarantine) already exists and recall already honors it.

---

## Target B — SENTINEL-021: auto-reconcile product memory  *(the quality fix; ~6 steps)*

> **SUPERSEDED for build (2026-06-14):** the build-ready, code-grounded version of Target B now lives in
> `docs/specs/SENTINEL-021/{spec,design,plan}.html`. Those resolve the naming correction
> (`write()`@store.py:516, not `add()`/517) and bake in OQ-1 (PRIVATE>PUBLIC) / OQ-2 (write-time only) /
> OQ-3 (auto-derived golden questions). The summary below is kept as the original Think-note rationale.

**Goal:** for one entity+topic, recall serves exactly one live head — the newer, more-trusted finding —
with the loser kept (quarantined) and linked, automatically.

1. **Resolution policy** (`store.py`, new pure fn `_pick_winner(a, b) -> (winner, loser)`): newer
   `created_at` wins; tie-break by `strength`/`access_count` (SM-2 trust), then boundary (PRIVATE >
   PUBLIC as more-vetted, or per ADR). Pure + unit-testable, no LLM. Resolves the arbitrary `keep="a"`.
2. **Auto-resolve at write:** where G-10 logs a conflict (`store.py:542-563`), immediately call the
   policy and quarantine the loser in the same transaction — conflict row written `status='resolved_*'`,
   not `'open'`. Both entries never co-exist live. Keep it fail-soft (never break a write).
3. **`superseded_by` link:** add column to `memory_entries` via `_MEMORY_MIGRATIONS` (`store.py:293`,
   the proven idempotent ALTER pattern); set it on the quarantined loser → audit trail / wake-up path.
4. **Recall-time safety net:** in `recall()` collapse any *un-logged* same-topic-prefix non-quarantined
   pair to the policy winner (belt-and-suspenders for pre-fix rows + race windows). Cheap; reuses the
   same `_pick_winner`.
5. **Curator pass:** a `reconcile_open_conflicts()` method that auto-resolves the existing `status='open'`
   backlog via policy, wrapped in the **golden-question check** — snapshot N entity recalls, reconcile,
   re-recall; roll back any entity whose answer degraded. Wire to the `memory-curator` skill /
   `/biltiq-engineering:siem` cadence.
6. **Surface:** memory/accounts UI shows "reconciled — N superseded" instead of silently dropping; a
   conflicts view lists resolved + (rare) flagged-for-human rows.

**Tests:** two contradicting findings, same entity → recall returns only the winner; loser quarantined +
`superseded_by` set; policy picks newer/stronger deterministically; backlog reconcile clears `open`;
golden-question rollback fires when a recall degrades; exact-dup still reinforces (no regression).
**Acceptance:** seed two opposite findings for one entity → a research run cites only one, the newer.

## Target A — agent write-hook + curator cadence  *(reliability; lighter, mostly config)*

**Goal:** the agent stops being even a part-time librarian for its own `memory/` store.

1. **Write-hook** (`.claude` Stop/PostToolUse hook): on a memory-file write, run the architecture's
   decision tree — exact-dup → drop; same-slug → ensure single index line; new → append index line —
   and flag any same-topic collision for demotion. Until this lands, I run it by hand (already do).
2. **Index = live-head invariant enforced by the hook:** the hook guarantees one `MEMORY.md` line per
   slug and strips lines whose file is `status: superseded`.
3. **Curator cadence:** schedule `memory-curator` at session-end / weekly with the golden-question
   snapshot→re-ask→rollback (same safety net as B-5). Episodic stays in `.remember/`, never a head.

**Tests:** hook drops an exact-dup write; hook refuses a second live line for an existing slug;
superseded files don't appear in the injected index.

---

## Sequencing & why

- **B first.** It's real, testable code in this repo, it's the quality win the dev named, and it's
  surgical (the pipeline is 70% built). Ship SENTINEL-021 through the Attack Loop.
- **A second.** Lighter, mostly harness config; the *rules* already give the benefit (I apply them by
  hand) — the hook just removes my attention from the loop. No spec scaffold needed; it's `.claude` config.
- **Shared module:** `_pick_winner` policy + the golden-question check are written once for B and reused
  conceptually by A's curator. Don't build two reconcilers.

## Ready-to-start gate (BiltIQ)

Target B needs `/docs/specs/SENTINEL-021/{spec,design,plan}.html` before Build (no-vibe-coding rule).
Next action on approval: `/biltiq-engineering:new-task SENTINEL-021` → think → plan → build. Target A
proceeds in parallel as harness config (no SENTINEL id).
