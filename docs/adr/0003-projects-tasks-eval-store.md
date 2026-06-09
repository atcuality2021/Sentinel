# ADR 0003: Project / Task / Plan persistence in the existing SQLite store

**Status:** accepted
**Date:** 2026-06-08
**Deciders:** @harish
**Related task:** SENTINEL-012 (Phase 1, Step 4)
**Revision:** v2 — scope cut + orphan story + memory/run asymmetry, after a 2-reviewer pass
(biltiq-plan-reviewer + architecture-critic). See "Review responses" at the bottom.

## Context

SENTINEL-012 turns Sentinel from a single-target/single-mode tool into a universal research agent
organised around **Projects** and **Tasks** (objective × domain × persona), executed by an
orchestrator that emits an inspectable **Plan** of **Steps**. None of these entities have anywhere
to live: the store today (`memory/store.py`) holds exactly two tables — `memory_entries` (System-2
entity memory, the boundary choke-point) and `run_records` (the episodic dashboard log). Both are
keyed by `entity`, with no notion of which project a run belongs to. We need durable storage for the
new entities **and** a way to scope existing runs/memory to a project — without breaking the ~117
existing rows a pilot DB already holds, and without weakening the SENTINEL-002 boundary invariant.

**Two reviewers flagged a root assumption this ADR originally made and the data model does not
enforce: that an entity belongs to one project.** It does not. A run is episodic and naturally
project-scoped; entity *memory* is keyed by `entity` and is legitimately shared across projects (the
operator may research "Datadog" under two different projects and should see all their own facts). v2
treats the two stores **asymmetrically** because of this (see Decision §3).

## Decision

**Extend the existing single-file SQLite store additively.** No new database, no new engine.

1. **Three new tables** (NOT four — `agent_specs` is cut, see §"Scope") created by the existing
   `_ensure_schema` script (`CREATE TABLE IF NOT EXISTS`): `projects`, `tasks`, `plans`. Nested
   fields (Plan.steps, Project.settings/source_docs) are stored as JSON `TEXT` columns — matching
   the existing `sources`/`finding_texts` precedent in `run_records` — so a row maps 1:1 to its
   pydantic model via `model_dump_json()` / `model_validate_json()`.
2. **A nullable `project_id TEXT` column** added to both `run_records` and `memory_entries` via the
   existing additive `ALTER TABLE ADD COLUMN` mechanism (`_RUN_MIGRATIONS`, extended with a new
   `_MEMORY_MIGRATIONS` for `memory_entries`). `NULL` ⇒ a legacy / unscoped row, returned unchanged
   by every existing read.
3. **Asymmetric use of `project_id` — this is the load-bearing decision:**
   - On **`run_records`** it is a *real scoping key*: the dashboard reads gain an OPTIONAL
     `project_id` filter. Runs are episodic, so scoping is correct and lossless.
   - On **`memory_entries`** it is *best-effort provenance only* — recorded on write, but
     **`recall` and `list_for_entity` do NOT filter by it** (no Phase-1 consumer, and a
     project-scoped recall would silently drop the operator's own PRIVATE facts about an entity
     researched under another project). The boundary choke-point (`recall`) is therefore
     **untouched**; the SENTINEL-002 PUBLIC/PRIVATE invariant is the only access gate, unchanged.
     Memory **dedup stays project-agnostic** (`write` dedups on `entity+boundary+content_hash` as
     today): two projects researching one entity share the deduped fact, and its `project_id`
     records the first writer. AC-1 wording adjusted to "runs carry their `project_id`; memory
     records best-effort project provenance."
4. **Orphan integrity — defense in depth (both mitigations, mirroring the boundary invariant's
   SQL-filter + Python-reassert pattern):**
   - **Cascade:** a new `purge_project(project_id)` deletes the project's `tasks`/`plans` rows and
     NULLs `project_id` on its `run_records`/`memory_entries` (memory/runs survive — they're
     entity-owned, not project-owned). `purge_entity` is unchanged (entity-scoped).
   - **Defensive reads:** task/plan reads tolerate a missing parent — a `Task` whose project row is
     gone, or a `Plan` whose task row is gone, reads back cleanly (no crash); the orphan is
     surfaced, not fatal. Tested.

## Scope (cut from v1)

- **`agent_specs` table DEFERRED to a Phase-3 follow-up ADR.** Its first and only consumer is the
  AgentRegistry (`agent/registry.py`, plan.md Step 14 — Phase 3b, recommended *deferred past the
  2026-06-11 deadline*, spec §8 descope). The additive migration mechanism makes adding the table
  later free, which removes the "avoid a second migration" rationale for shipping it now. Shipping
  it early would only add a web-mutable surface + migration/test cost ahead of any reader (YAGNI).
  `AgentSpec` the **pydantic model** still ships in Step 3 (already done) — only its *table* waits.
- **`plans` is KEPT** (not cut): Phase 2's hand-built DAG (plan.md Step 10) must persist
  `Step.status` + timing for resume-from-last-good (spec §9.4) — that per-task runtime state needs a
  home now, even though the *Planner* that composes Plans is Phase 3.

## Alternatives considered

1. **A separate `projects.db` file / second store class** — Rejected: the dashboard joins runs to
   memory by entity; a second file forces cross-file reads with no transactional story and doubles
   WAL/connection management for no isolation benefit at single-operator scale.
2. **Postgres / a real RDBMS** — Rejected: operational overhead unjustified for a single-operator
   pilot; SQLite-WAL already satisfies the concurrent async-web + orchestrator access pattern.
3. **A normalised `steps` table (row per Step) instead of JSON-on-`plans`** — Rejected *for now*,
   with an explicit trigger: a Plan is read/written whole in Phase 2's single-task sequential DAG,
   so JSON is fine. **The normalization trigger is per-step `status` writes during execution**
   (plan.md Step 10/12): once steps update status mid-run, JSON-blob updates become a
   read-modify-write of the whole `plans` row — a lost-update hazard if the orchestrator and web app
   ever write concurrently. Phase 2 is single-writer/sequential so it survives; revisit at the first
   concurrent-write or cross-plan step query ("all failed `compare` steps" for eval triage).
4. **A foreign-key constraint on `project_id`** — Rejected: SQLite FK enforcement is off by default
   and a hard FK complicates the legacy-`NULL` backfill and purge. We enforce the relationship in
   the store layer (the `purge_project` cascade + defensive reads of §3.4), consistent with how the
   boundary invariant is enforced in code rather than schema.
5. **Filter `recall` by `project_id` (v1's proposal)** — Rejected: see Decision §3; silently drops
   the operator's own PRIVATE facts and has no Phase-1 consumer.

## Consequences

**Positive:**
- One file, one backup, one connection model; the WAL/short-lived-connection design extends
  naturally. Legacy rows render untouched (`project_id IS NULL` flows through every read; the
  run-side filter is opt-in). Forward-only, additive — no data rewrite, no downtime.
- Row↔model symmetry (JSON columns + pydantic) keeps the store thin: each new entity = a table +
  a `_row_to_*` mapper + an insert, mirroring the existing pattern.
- The run/memory asymmetry makes the sovereignty story *stronger*, not weaker: the boundary
  choke-point is provably unchanged, and the brief never loses the operator's own facts to scoping.

**Negative / risks:**
- JSON columns aren't independently queryable in SQL (can't `WHERE` on a step's status without
  loading the plan). Accepted; the normalization trigger is named above.
- A new writable surface (`projects/tasks/plans`) widens what the web app can mutate; inserts MUST
  use parameterised queries only (no f-string SQL) — enforced by `security-pre-edit` + the AP-#5
  review gate. The `recall` boundary path is *not* in this surface (unchanged).
- Memory `project_id` is best-effort (first-writer) — acceptable because memory is deliberately
  cross-project; documented so no one mistakes it for a scoping key.

**Tech debt accepted:**
- No FK integrity in the schema (cascade + defensive reads in the store layer instead).
- JSON `plans.steps` until the per-step-status-write trigger forces normalization.

## Migration plan (column-by-column)

- **Tables:** `_SCHEMA` gains three `CREATE TABLE IF NOT EXISTS` blocks + indexes:
  `tasks(project_id)`, `plans(task_id)`. (No `agent_specs` index — table deferred.)
- **Columns:** `_ensure_schema` runs `_RUN_MIGRATIONS` against `run_records` (adds `project_id`) and
  a new `_MEMORY_MIGRATIONS` against `memory_entries` (adds `project_id`), both
  `ADD COLUMN project_id TEXT` (nullable, no default). Idempotent: guarded by `PRAGMA table_info`,
  exactly as the existing mechanism.
- **Models:** `RunRecord` and `MemoryEntry` gain `project_id: str | None = None`; `_row_to_run` /
  `_row_to_entry` read `r["project_id"]` via the existing defensive `r["col"]`-with-default idiom;
  insert column lists + value tuples extend by one.
- **Reads — run side (real filter), the complete inventory Step 6's UI consumes:** optional
  `project_id: str | None = None` on `RunStore.list`, `all`, `latest_for`, `runs_for`, `entities`,
  and `count` → append `AND project_id=?` when set. **Memory side: no filter added** (Decision §3).
- **New methods:** `purge_project(project_id)`; project/task/plan CRUD; defensive parent-tolerant
  reads.
- **Reversibility:** forward-only (SQLite can't easily drop a column); the column is nullable and
  ignored by old code paths, so a *code* rollback leaves the DB readable.

## Test plan (AC-1, migration)

- **CRUD round-trip** on `projects`/`tasks`/`plans` (insert → read → model equality).
- **No-regression (read):** a legacy run/memory row with `project_id IS NULL` still appears in
  `runs_for`/`entities`/`recall`/`list`/`all` with no filter.
- **No-regression (write byte-identity):** a `RunRecord` saved with `project_id=None` round-trips to
  a `_row_to_run` output equal to today's — **tied to the Phase-0 golden/characterization test** so
  "ships dark" is the actual gate, not a weaker NULL-render check.
- **Positive write (AC-1):** `RunStore.save` and `MemoryStore.write` persist a non-NULL
  `project_id` and read it back; a project-scoped run query returns only that project's rows; a
  different `project_id` returns none.
- **Memory provenance (AC-1, adjusted):** writing the same entity fact under two projects dedups to
  one row whose `project_id` is the first writer; `recall` returns it regardless of project (proves
  the boundary path is unscoped and lossless).
- **Orphan integrity:** `purge_project` deletes tasks/plans and NULLs run/memory `project_id`;
  reading a `Task`/`Plan` whose parent was removed degrades cleanly (no crash).
- **Idempotency:** create the *old* schema, re-open, assert `project_id` is added and existing rows
  read back.

## Review responses (v1 → v2)
- **FK/orphan claim was fictional** → added a real `purge_project` cascade **and** defensive reads,
  both tested (the dev chose belt-and-suspenders).
- **`recall` filter was a silent-PRIVATE-drop trap** → removed; memory `project_id` is provenance,
  not a filter; boundary choke-point untouched.
- **Scope over-reach (`agent_specs` YAGNI)** → cut to a Phase-3 follow-up ADR.
- **Read inventory incomplete** → added `list`/`all`/`count` to the run-side filter set.
- **Under-tested AC-1 write path** → added positive write + provenance + golden-tie-in tests.
- **"Revisit later" on JSON steps** → named the concrete normalization trigger + concurrency caveat.

## References
- `docs/specs/SENTINEL-012/{spec.md §8/§9.8, AC-1; design.md §9.8; plan.md Step 4/10/14}`
- `src/sentinel/memory/store.py` (`_RUN_MIGRATIONS`, `_ensure_schema`, `recall` choke-point:176,
  `write` dedup:276, `purge_entity`:298, `list`:418, `all`:425, `count`:321)
- ADR-0001 (tiering), ADR-0002 (remote A2A)
