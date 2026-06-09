# SENTINEL-002 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval
**Borrows:** BiltIQ Agent OS `memory/{schemas,store,strength,dedup}.py` (patterns, not code)

---

## 1. Architecture overview

A new `sentinel.memory` package backed by a single SQLite file. The orchestrator gains a
**memory loop** around the existing run: recall (boundary-scoped) → run → persist + extract +
delta. The boundary invariant lives in **one choke-point read method**; nothing else touches the
table.

```
run_async(target, mode, ...)
   │  allowed = {PUBLIC} if mode==competitor else {PUBLIC, PRIVATE}
   ├─▶ MemoryStore.recall(entity=target, allowed)         ──┐ boundary-filtered, decayed-ranked
   │      → memory_context text  + reinforce_on_read         │ (PRIVATE never enters a public run)
   ├─▶ (optional) inject memory_context into synthesizer  ◀──┘ via the 001 note-substitution slot
   ├─▶ … existing ADK pipeline … → artifact
   ├─▶ RunStore.save(RunRecord)                              persistent (dashboard reads this)
   ├─▶ MemoryStore.process_run(artifact)                    extract findings → boundary-tagged entries
   └─▶ delta = diff(this_run, prior_run)                    "since last run"
```

## 2. New package: `src/sentinel/memory/`

### 2.1 `schema.py`
- Reuse `artifacts.schemas.Boundary` as **`DataBoundary`** (PUBLIC/PRIVATE) — one boundary type
  across tool layer, artifacts, and memory (the whole point).
- `MemoryType(str, Enum)`: `finding | preference | decision | observation`.
- `MemoryEntry(BaseModel)`: `id`(uuid4 hex), `entity`(normalized lower), `boundary: DataBoundary`,
  `memory_type`, `content`, `source_label`, `source_url|None`, `created_at`, `content_hash`,
  SM-2 state (`strength=1.0`, `interval_days=1.0`, `ease=2.5`, `last_reinforced_at`,
  `access_count=0`), `quarantined=False`.
- `RunRecord(BaseModel)`: `id`, `entity`, `target`, `mode`, `backend`, `kind`, `public`, `private`,
  `gaps`, `reference`, `finding_texts: list[str]`, `created_at`.
- `MemoryDelta(BaseModel)`: `added: list[str]`, `removed: list[str]`, `summary: str`,
  `prior_run_at: datetime | None`.

### 2.2 `strength.py` (pure, no I/O — borrowed shape)
- `decayed_strength(entry, now) -> float` (Leitner interval + recency decay).
- `reinforce(entry, signal) -> entry` — POSITIVE diminishing-returns to a ceiling; NEUTRAL no-op.
- `STRENGTH_FLOOR`, `STRENGTH_CEIL` constants.

### 2.3 `store.py` (SQLite, the choke point)
```python
class MemoryStore:
    def __init__(self, path: Path | str = data_dir()/"sentinel.db"): ...   # WAL, ensure schema
    # THE invariant — every read goes through here:
    def recall(self, entity, allowed: set[DataBoundary], *, limit=8, token_budget=1200) -> list[MemoryEntry]:
        # SQL WHERE entity=? AND quarantined=0 AND boundary IN (allowed)
        # + Python re-assert boundary ∈ allowed (defense in depth)
        # rank by decayed_strength, drop < floor, top-k, truncate to token budget; reinforce_on_read
    def write(self, entry: MemoryEntry) -> str:
        # fail-closed: if boundary not a valid DataBoundary → entry.quarantined = True
        # dedup: (entity, boundary, content_hash) exists → reinforce instead of insert
    def process_run(self, entity, artifact) -> int:        # extract findings → write entries
    def purge_entity(self, entity) -> None
    def decay(self) -> int                                  # archive below floor (scheduled)
```
`RunStore` (same db, table `run_records`): `save`, `list(limit)`, `latest_for(entity)`, `all()`.

`data_dir()` = `SENTINEL_DATA_DIR` env or `./data`; gitignored.

### 2.4 `extraction.py` (deterministic — borrowed FactExtractor shape)
`extract_entries(entity, artifact) -> list[MemoryEntry]`: walk the artifact's `Finding` lists and
emit one entry per finding **stamped with that finding's `source.boundary`**:
- Battlecard → strengths/weaknesses/pricing_signals/recent_developments (all PUBLIC).
- AccountBrief → public_signal (PUBLIC), private_signal (PRIVATE).
- `memory_type=finding`; `content=finding.text`; source from `finding.source`.
- (merged_insights/how_to_win/recommended_actions are derived prose → **not** stored in v1 to avoid
  mis-tagging a private-derived insight as public; revisit in a later increment.)

### 2.5 `delta.py`
`compute_delta(prior: RunRecord | None, current_texts: list[str]) -> MemoryDelta`: normalized
set-diff of finding texts (added/removed) + a one-line summary; `prior is None` ⇒ "first run".

## 3. Orchestrator integration (`agent/orchestrator.py`)

- Compute `allowed = {PUBLIC}` for competitor, `{PUBLIC, PRIVATE}` for client. **This is the
  enforcement seam**: a competitor run literally cannot pass PRIVATE to `recall`.
- If `cfg.memory.entity_memory`: `mem = store.recall(target, allowed)`; render a compact
  `memory_context` block; pass to the synthesizer via the **SENTINEL-001 note-substitution slot**
  (`note_substitutions={"memory_context": block}`); when memory is empty/disabled the slot is
  substituted with `""` → instruction identical to today (AC-10 no-regression).
- After the run: `RunStore.save(...)`, `store.process_run(target, artifact)`,
  `delta = compute_delta(prior, finding_texts)`. Attach `delta` to `RunResult`.
- Add `{memory_context}` to `render.RESERVED_VARS` and append a `{memory_context}` slot to the
  default synthesizer prompts (empty-substitution yields the original text).

## 4. Dashboard / presentation (`web/`)
- `web/app.py` STORE → back it with `RunStore` (durable). Dashboard/charts/recent now survive restart (AC-1).
- Artifact page + dashboard show the `MemoryDelta` ("Since last run …") when present.

## 5. File-by-file

| File | Change |
|---|---|
| `src/sentinel/memory/__init__.py` | exports store + models |
| `src/sentinel/memory/schema.py` | NEW — MemoryEntry, RunRecord, MemoryDelta, MemoryType |
| `src/sentinel/memory/strength.py` | NEW — SM-2 kernel |
| `src/sentinel/memory/store.py` | NEW — MemoryStore + RunStore (SQLite, choke-point recall) |
| `src/sentinel/memory/extraction.py` | NEW — deterministic finding→entry |
| `src/sentinel/memory/delta.py` | NEW — since-last-run diff |
| `src/sentinel/agent/orchestrator.py` | memory loop; `RunResult.delta`; allowed-boundary seam |
| `src/sentinel/config/render.py` | add `memory_context` reserved var |
| `src/sentinel/config/defaults.py` | synthesizer prompts gain trailing `{memory_context}` slot |
| `src/sentinel/web/app.py` | back STORE with RunStore; show delta |
| `.gitignore` | add `data/` |
| `tests/test_memory.py` | NEW — AC-1..AC-10 (incl. adversarial AC-3) |

## 6. Testing strategy
- **Boundary invariant (AC-3, P0):** seed a PRIVATE entry for "Acme"; `recall("Acme", {PUBLIC})`
  returns it **not**; `recall("Acme", {PUBLIC, PRIVATE})` returns it. Also assert the orchestrator
  passes `{PUBLIC}` for competitor mode.
- **Fail-closed (AC-4):** write an entry with a bogus boundary → stored `quarantined=True` → absent
  from all recall.
- **Persistence (AC-1):** save runs, reopen store, read them back.
- **Extraction (AC-5):** AccountBrief with public+private findings → public entries PUBLIC, private
  entries PRIVATE.
- **Reinforce/decay (AC-6), dedup (AC-7), delta (AC-8), purge (AC-9), gate (AC-10).**
- No live LLM anywhere.

## 7. Risks & mitigations
- **R-1 boundary leak:** single choke-point `recall` + SQL filter + Python re-assert + adversarial
  test. No raw table access elsewhere (lint/review rule).
- **R-3 SQLite + async:** WAL mode, short connections; extraction/save off the response path where
  feasible; fail-soft so a db error never breaks a run.
- **R-2 shallow extraction:** accepted v1; local-vLLM Tier-2 follow-up (off-latency, fail-soft).

## 8. Rollback
Memory is additive and gated. `cfg.memory.entity_memory=False` ⇒ no recall, empty
`{memory_context}` ⇒ outputs identical to SENTINEL-001. Deleting `data/sentinel.db` resets memory.
