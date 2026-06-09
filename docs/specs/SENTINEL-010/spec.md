# SENTINEL-010 — Account Prioritization (Deterministic Focus List)

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-002 (`MemoryStore`/`RunStore`, `decayed_strength`), 004 (Accounts index /
`EntitySummary`), 005 (governance — reasons obey boundary)
**Blocks:** the demo "who do I focus on **now**?" screen
**Source:** [`../../intelligence-to-action/srs.md`](../../intelligence-to-action/srs.md) FR-101..107 ·
[`business-analysis.md`](../../intelligence-to-action/business-analysis.md) US-C1..C4

---

## 1. Context / problem

A BD lead with 40 researched accounts opens each brief cold every morning and re-derives priority by
gut; stalled and at-risk accounts slide past their kill date silently. Sentinel already stores every
run (`RunStore`) and a boundary-tagged entity memory (`MemoryStore`), and the Accounts index
(SENTINEL-004) already lists *what* we've researched — but nothing answers *"who needs attention
first, and why?"*. ZoomInfo and 6sense answer it with **black-box ML scores** a regulated buyer
cannot audit. Our wedge is a **deterministic, explainable, cited** score: pure-code arithmetic over
the data we already hold, with a per-signal breakdown the user can inspect — and a single signal
**registry** an admin extends without touching the scorer core (LeadFlow ran three overlapping
scorers; we keep exactly one).

> **Not a solution restatement:** the ask is not "add a score column." It is "rank the accounts by
> who needs action now, show the cited reasons, and let an admin tune the weights — all without an
> LLM in the arithmetic and without leaking private signal into a public view."

## 2. Goal / non-goals

**Goal:**
1. `compute_account_priority(entity, *, allowed_boundaries)` → `{score 0-100, tier, breakdown}`,
   computed **deterministically** (no LLM, no network).
2. A **signal registry**: `register_signal(name, weight, fn)`; the engine normalizes weights to 1.0,
   isolates per-signal failures (default value), and clamps the result to 0-100. One registry is the
   single source of truth.
3. Reusable `normalize(value, low, high, invert)` + half-life **time-decay** primitives for signals.
4. A ranked **focus list** on the dashboard: each row carries human-readable `reasons[]`, each reason
   linked to a cited finding / memory entry / run.
5. The breakdown is **persisted + auditable**; the focus list loads in < 1 s (NFR-2: < 200 ms/entity).
6. **Boundary-safe:** priority reasons respect the SENTINEL-002 invariant — a public-only context
   never surfaces a private-sourced reason.

**Non-goals:** ML / learned segmentation, vector search (deterministic registry + filters only);
auto-actions on high-priority accounts (006); editing weights via UI beyond a simple form (admin can
edit config); cross-entity clustering. Ships **dark-compatible**: the focus list is an additive route;
existing pages are unchanged.

## 3. Personas

P1 **BD lead** — one screen ranking accounts by who needs attention, each with a cited reason.
P2 **Admin** — add/weight a signal without touching the scorer core. P3 **Compliance** — the focus
list must never leak private data into a public view; the score must be auditable (deterministic).

## 4. Acceptance criteria (testable, binary)

- [ ] **AC-1** `compute_account_priority(entity, *, allowed_boundaries={PUBLIC,PRIVATE})` returns a
  `PriorityScore{score:float 0-100, tier:Literal["hot","warm","cold"], breakdown:dict[str,float],
  reasons:list[Reason]}`, with **no** LLM/network call in the path. (FR-101)
- [ ] **AC-2** Scoring is **deterministic**: identical inputs ⇒ identical score across runs
  (test asserts equality over repeated calls). (FR-101/103)
- [ ] **AC-3** `register_signal(name, weight, fn)` adds a signal; the engine **normalizes** registered
  weights so they sum to 1.0 before the weighted sum (a test with weights {2,2} ≡ {1,1}). (FR-104)
- [ ] **AC-4** A signal `fn` that raises is **isolated**: it contributes its declared default (0.0),
  the engine still returns a score, and the failure is noted in the breakdown/trace, not raised. (FR-104)
- [ ] **AC-5** The final score is **clamped** to [0,100] regardless of signal values/weights. (FR-104)
- [ ] **AC-6** Exactly **one** registry module is the source of truth; there is no second/parallel
  scorer (asserted structurally — one `register_signal`, one `compute_account_priority`). (FR-105)
- [ ] **AC-7** `normalize(value, low, high, invert=False)` maps to [0,1] (clamped; `invert` flips);
  `half_life_decay(age_days, half_life)` ∈ (0,1], `=1` at age 0, `=0.5` at one half-life. (FR-106)
- [ ] **AC-8** ≥ 4 seed signals are registered over existing data: `recency` (days since last run),
  `new_material` (findings added in the latest run / delta), `volume` (cumulative findings),
  `private_engagement` (count of PRIVATE memory — boundary-gated), [competitor mode] `competitor_move`
  (recent-developments recency). (OQ-4)
- [ ] **AC-9** The dashboard shows a **ranked focus list** (highest score first); each row shows
  score, tier, and `reasons[]`; each reason references a concrete finding/memory/run
  (`source_label`/`url`/run reference). (FR-102)
- [ ] **AC-10** **Boundary invariant:** calling `compute_account_priority(entity,
  allowed_boundaries={PUBLIC})` yields **no** private-sourced reason and the `private_engagement`
  signal contributes 0 — proven by a test seeding PRIVATE memory then scoring public-only. (FR-107)
- [ ] **AC-11** The computed breakdown is **persisted** (auditable) and re-readable for an entity. (FR-103)
- [ ] **AC-12** Computing one entity's score is < 200 ms with no network (timed test, mocked clock). (NFR-2)
- [ ] **AC-13** All existing tests pass; SENTINEL-002 boundary tests + 004 Accounts index unchanged;
  the focus-list route is additive. (NFR-7)

## 5. Functional requirements

- **FR-1** `priority/signals.py` (NEW): module-level `REGISTRY`; `register_signal(name, weight, fn,
  *, default=0.0)`; primitives `normalize`, `half_life_decay`; the seed signals.
- **FR-2** `priority/engine.py` (NEW): `PriorityContext`, `PriorityScore`, `Reason`,
  `compute_account_priority(entity, *, allowed_boundaries, now=None, config=None)`; weight
  normalization, per-signal isolation, clamp, tiering.
- **FR-3** `priority/store.py` (NEW) **or** reuse the SENTINEL-002 SQLite file: persist a
  `PriorityRecord{entity, score, tier, breakdown, reasons, computed_at}`; `latest_for(entity)`.
- **FR-4** `config/schema.py`: `PriorityConfig{enabled=True, weights:dict[str,float],
  hot_threshold, warm_threshold, recency_half_life_days}`; add `priority` to `SentinelConfig`.
- **FR-5** `web/app.py` + `render.py`: `/focus` route (or dashboard card) rendering the ranked list +
  per-row reasons + a breakdown drill-down.

## 6. Non-functional

- **NFR-1** Deterministic-first: no LLM in the arithmetic; reasons are templated from cited data, not
  generated. (SRS NFR-5)
- **NFR-2** < 200 ms / entity, no network. (SRS NFR-2)
- **NFR-3** Boundary invariant inviolable — reasons + signals are boundary-filtered at the
  `MemoryStore.recall` choke-point, not after. (SRS C-3 / FR-107)
- **NFR-4** Typed; no `Any`, no unjustified `# type: ignore`.
- **NFR-5** Weights/thresholds are admin-editable config (no redeploy). (SRS NFR-6)

## 7. Risks

- **R-1 Deterministic score feels arbitrary** if opaque. *Mitigation:* always render the cited
  breakdown; weights are config (AC-9/FR-4).
- **R-2 Re-importing LeadFlow's triple-scorer debt.** *Mitigation:* one registry, asserted (AC-6).
- **R-3 Boundary leak via a reason string.** *Mitigation:* signals receive only boundary-filtered
  memory; AC-10 test scores public-only over seeded private data.
- **R-4 Thin signal for accounts with one run.** *Mitigation:* signals fail-soft to neutral; tiering
  tolerates sparse data; seed set tuned with the pilot (OQ-4).
- **R-5 Clock/timezone bugs in decay.** *Mitigation:* single `utcnow` clock (SENTINEL-002); `now`
  injectable for deterministic tests.

## 8. Open questions

- **OQ-1** Persist priority in the SENTINEL-002 DB (new table) or a separate file? *Proposed:* same
  DB, new `priority` table — one data dir, one backup unit.
- **OQ-2** Focus list as its own `/focus` page or a card on the dashboard? *Proposed:* both — a
  dashboard "Top 5 to focus on" card linking to a full `/focus` page.
- **OQ-3** Recompute on every run vs lazily on view? *Proposed:* compute on view (cheap, deterministic)
  + persist the snapshot; recompute-on-run is a fast-follow if the list must be push-fresh.
- **OQ-4** Final seed signal set + weights for the pilot's accounts — needs pilot confirmation
  (recency, new_material, volume, private_engagement, competitor_move proposed).
