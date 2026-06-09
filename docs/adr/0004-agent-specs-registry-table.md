# ADR 0004: `agent_specs` registry table — the Phase-3 follow-up deferred by ADR-0003

**Status:** accepted
**Date:** 2026-06-08
**Deciders:** @harish
**Related task:** SENTINEL-012 (Phase 3, Step 14 — AgentRegistry)
**Supersedes the "deferred" note in:** ADR-0003 §Scope (which cut `agent_specs` from the v2 store and
named "a Phase-3 follow-up ADR" as its home — this is that ADR).

## Context

ADR-0003 shipped `projects`/`tasks`/`plans` and **explicitly deferred** the fourth table,
`agent_specs`, on a YAGNI argument: its only consumer was the not-yet-built AgentRegistry, and "the
additive migration mechanism makes adding the table later free." Step 14 builds that registry. The
registry's job (design §2.1 / §10.3, AC-21) is to make specialists **reusable by `(capability,
domain)`** rather than rebuilt per task, and to let the Phase-3 planner (Step 15) **create** a new
`AgentSpec` on a capability miss — a created spec that must **survive** the process that minted it so
the autonomy gate (Step 16) can show it for approval and a later task can reuse it.

In-memory-only was considered and rejected for *this* step (see Alternatives): the planner's created
specs are the first artifacts that genuinely need durability across the orchestrator/web boundary,
and shipping the table now keeps the registry's read/write surface identical whether a spec is a
seed or a survivor — no second code path to add in Step 15.

`AgentSpec` the **pydantic model** already shipped in Step 3 (schemas.py:303). This ADR adds only its
**table** + a thin `SpecStore`, mirroring ADR-0003's row↔model pattern exactly.

## Decision

**Extend the existing single-file SQLite store additively with one table.** No new database, no new
engine — the same mechanism (`CREATE TABLE IF NOT EXISTS` in `_SCHEMA`) ADR-0003 used.

1. **One new table, `agent_specs`,** keyed by `id`. The full `AgentSpec` JSON lives in a `data TEXT`
   column (the source of truth, `model_dump_json()` ↔ `model_validate_json()`); the scalar columns
   `capability`, `domain`, `version`, `eval_score`, `active`, `origin` are **denormalised only for
   indexed lookup/ranking** — identical to how `tasks`/`plans` denormalise `project_id`/`status`.
2. **`resolve(capability, domain)` reuses, never rebuilds (AC-21).** It reads the **active** specs
   for the key and returns the **highest-scoring** one, ranked by `(eval_score ?? -1.0, version)` —
   so a graded spec beats an ungraded one, a newer version breaks ties, and an ungraded seed still
   resolves when it is the only candidate. The reuse guarantee is a *read*, not a build: resolving a
   capability that already has a spec creates **no** duplicate agent.
3. **Created specs are validated before they can be stored-and-run (AC-12).** `validate_agent_spec`
   enforces four invariants — `role ∈ Role`, `output_schema_ref ∈ KNOWN_OUTPUT_SCHEMAS`,
   `reasoner ⇒ no tools` (REASONER_ROLES tool-free, the SENTINEL-011 latency/sovereignty guard as a
   *build-time* invariant), and `tools ⊆ ALLOWED_TOOLS` (no off-allow-list capability escalation,
   §9.2). The validator is pure (no I/O) and is the choke-point both `build_from_spec` (raises) and
   the Step-15 planner (checks) call.
4. **No boundary escalation through the registry.** An `AgentSpec.boundaries` list is FIXED on the
   spec (§9.2); a created spec inherits, it cannot widen, the boundaries — enforced in Step 17. The
   table stores `boundaries` inside `data` only; there is no SQL path that mutates it post-write.

## Scope

- **IN:** the `agent_specs` table; `SpecStore` (save / get / `active_specs(capability, domain)` /
  `deactivate` / list); the `AgentRegistry` seam (seed from `SKILL_SPECS`, `resolve`, `register`,
  `validate_agent_spec`, `build_from_spec`).
- **OUT (Step 15+):** the planner that *emits* created specs; re-wiring `dag.py`'s per-step staffing
  from `SKILL_SPECS` to `registry.resolve` (seed skills keep flowing through `SKILL_SPECS`/
  `build_step_agents` this step — the registry indexes them, it does not yet replace the pipeline
  builder). `eval_score` write-back from the Step-12 runner onto a spec row (the column exists now;
  the writer lands when the eval loop is wired to production).

## Alternatives considered

1. **In-memory registry, defer the table again (ADR-0003's standing recommendation).** Rejected
   *for this step* by an explicit dev decision: the planner's created specs (Step 15) need to survive
   immediately, and a same-step table avoids shipping an in-memory store then rewriting it to a
   persisted one a step later. The YAGNI argument that held in Phase 1 (no reader) no longer holds —
   Step 15 is the reader, one step out.
2. **A normalised column per `AgentSpec` field instead of `data` JSON.** Rejected: a spec is
   read/written whole, exactly like a `Plan`; JSON-on-`data` keeps the row↔model mapper trivial and
   matches the established precedent. The denormalised scalars cover every query the registry makes
   (lookup by key, rank by score/version).
3. **A `UNIQUE(capability, domain, version)` constraint.** Rejected for now: versioning/supersession
   policy is the registry's job (Step 15 mints `version = max+1`), enforced in the store layer like
   ADR-0003's FK substitute, not in schema — consistent with this codebase's "integrity in code,
   not constraints" stance. Revisit if concurrent spec writers appear.

## Consequences

**Positive:**
- One file, one backup, one connection model — the table slots into the existing `_SCHEMA`
  executescript with zero new machinery. Forward-only, additive: a pre-014 DB gains the table on
  next open via `CREATE TABLE IF NOT EXISTS`; no data rewrite, no downtime, legacy rows untouched.
- Row↔model symmetry (JSON `data` + pydantic) keeps `SpecStore` thin — a table + one `_row_to_spec`
  mapper + insert, exactly mirroring `_row_to_plan`.
- The sovereignty story is *unchanged*: `build_from_spec` routes through `make_agent`/`resolve_model`,
  so a spec built under `cloud_allowed=False` constructs **no Gemini object** — provable by
  introspection, identical to every other agent (SENTINEL-005 NFR-2).

**Negative / risks:**
- A new **web-mutable surface** (specs the planner/UI can write) widens what the app can persist.
  Mitigated: every insert is parameterised (no f-string SQL, AP #5 gate); and **nothing reaches the
  table unvalidated** — `validate_agent_spec` is the choke-point, rejecting tool-bearing reasoners
  and off-allow-list tools before a row is written.
- `eval_score` is nullable and unwritten until the eval loop is wired (Step 12 → production). Until
  then `resolve` ranks ungraded seeds by version only — correct, just coarse.

**Tech debt accepted:**
- No `UNIQUE`/FK in schema (supersession + key-uniqueness enforced in the registry layer).
- `data`-JSON specs aren't independently queryable in SQL (can't `WHERE` on a tool name without
  loading the spec) — accepted; the scalar columns cover the registry's actual queries.

## Migration plan (column-by-column)

- **Table:** `_SCHEMA` gains one `CREATE TABLE IF NOT EXISTS agent_specs (...)` block + an index
  `idx_spec_key ON agent_specs(capability, domain, active)`. Because it is a *new table* (not a new
  column on an existing one), it needs no `ALTER`/`_…_MIGRATIONS` entry — `executescript` creates it
  on any DB, new or pre-existing.
- **Model:** none — `AgentSpec` already exists (schemas.py:303).
- **Mapper:** `_row_to_spec(r)` = `AgentSpec.model_validate_json(r["data"])` (mirrors `_row_to_plan`).
- **New store:** `SpecStore` with `save_spec`, `get_spec`, `active_specs(capability, domain)`,
  `deactivate(spec_id)`, `list_specs` — all parameterised.
- **Reversibility:** forward-only (SQLite can't easily drop a table); a *code* rollback leaves the
  table present-but-unread — old code never references `agent_specs`, so the DB stays readable.

## Test plan (AC-12 / AC-21, migration)

- **CRUD round-trip** on `agent_specs` (insert → read → model equality).
- **No-regression:** opening a pre-014 DB (the ADR-0003 three-table schema) adds `agent_specs` and
  leaves `projects`/`tasks`/`plans` + their rows untouched; idempotent on re-open.
- **`resolve` reuse (AC-21):** two active specs for one `(capability, domain)` with scores 0.6/0.9 →
  `resolve` returns the 0.9 spec; an ungraded lone seed still resolves; resolving creates no row.
- **`validate_agent_spec` rejects (AC-12):** a reasoner with a tool, and an off-allow-list tool, are
  each rejected with a named violation; a clean spec passes.
- **`build_from_spec` sovereignty (AC-12):** a spec built under `cloud_allowed=False` constructs a
  `LiteLlm` (not a Gemini id string) on the reasoner tier — zero Gemini, by introspection.

## References
- ADR-0003 §Scope (the deferral this ADR closes), §"Migration plan" (the pattern reused here).
- `docs/specs/SENTINEL-012/{spec.md §8/§9.2/§10.3, AC-12/AC-21; design.md §2.1/§10.3; plan.md Step 14}`
- `src/sentinel/artifacts/schemas.py` (`AgentSpec`:303, `KNOWN_OUTPUT_SCHEMAS`:416)
- `src/sentinel/config/schema.py` (`Role`:18, `REASONER_ROLES`:30)
- `src/sentinel/memory/store.py` (`_SCHEMA`:37, `_ensure_schema`:148, `_row_to_plan`:230, `ProjectStore`:573)
