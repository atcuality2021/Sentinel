"""SQLite-backed memory + run stores (SENTINEL-002).

A single file under ``data/`` holds two tables: ``memory_entries`` (System-2 entity memory) and
``run_records`` (episodic log feeding the dashboard). Connections are short-lived and WAL-mode so
the async web app and the orchestrator can share the file safely (design §7 R-3).

The boundary invariant lives in **one** method — ``MemoryStore.recall`` — which filters in SQL and
re-asserts in Python (defense in depth). Writes are **fail-closed**: an entry whose boundary is not
a valid ``DataBoundary`` is quarantined, never returned by any recall (AC-4). No other code reads
the table directly (design §7 R-1, enforced by review).
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from sentinel.artifacts.schemas import AgentSpec, Plan, Project, Task
from sentinel.memory.schema import (
    DataBoundary,
    EntityRelation,
    EntitySummary,
    MemoryEntry,
    RunRecord,
    normalize_entity,
    utcnow,
)
from sentinel.memory.strength import (
    HOT_THRESHOLD,
    STRENGTH_FLOOR,
    ReinforceSignal,
    decayed_strength,
    reinforce,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id                 TEXT PRIMARY KEY,
    entity             TEXT NOT NULL,
    boundary           TEXT NOT NULL,
    memory_type        TEXT NOT NULL,
    content            TEXT NOT NULL,
    source_label       TEXT NOT NULL,
    source_url         TEXT,
    created_at         TEXT NOT NULL,
    content_hash       TEXT NOT NULL,
    strength           REAL NOT NULL,
    interval_days      REAL NOT NULL,
    ease               REAL NOT NULL,
    last_reinforced_at TEXT NOT NULL,
    access_count       INTEGER NOT NULL,
    quarantined        INTEGER NOT NULL,
    project_id         TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_entity ON memory_entries(entity);
CREATE INDEX IF NOT EXISTS idx_mem_dedup
    ON memory_entries(entity, boundary, content_hash);

CREATE TABLE IF NOT EXISTS run_records (
    id            TEXT PRIMARY KEY,
    entity        TEXT NOT NULL,
    target        TEXT NOT NULL,
    mode          TEXT NOT NULL,
    backend       TEXT NOT NULL,
    kind          TEXT NOT NULL,
    public        INTEGER NOT NULL,
    private       INTEGER NOT NULL,
    gaps          INTEGER NOT NULL,
    reference     TEXT NOT NULL,
    finding_texts TEXT NOT NULL,
    sources       TEXT NOT NULL DEFAULT '[]',
    run_seq       INTEGER NOT NULL DEFAULT 0,
    project_id    TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_entity ON run_records(entity);
CREATE INDEX IF NOT EXISTS idx_run_created ON run_records(created_at);
-- NOTE: idx_run_project is created in _ensure_schema AFTER the project_id column migration, so it
-- works on a pre-012 DB where the column doesn't exist until the ALTER runs.

-- SENTINEL-012 (ADR-0003) — Project / Task / Plan. Nested fields live in the `data` JSON column
-- (model_dump_json ↔ model_validate_json); the duplicated scalar columns exist only for indexed
-- lookup/filtering. `agent_specs` is deliberately deferred to a Phase-3 follow-up ADR.
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    status     TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id      TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status  TEXT NOT NULL,
    data    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_plan_task ON plans(task_id);

-- SENTINEL-012 (ADR-0004) — the AgentRegistry's durable home (Phase 3, Step 14). The follow-up to
-- ADR-0003's deferred fourth table. Full AgentSpec JSON lives in `data` (source of truth); the
-- scalar columns are denormalised only for keyed lookup + score/version ranking in `resolve`.
CREATE TABLE IF NOT EXISTS agent_specs (
    id          TEXT PRIMARY KEY,
    capability  TEXT NOT NULL,
    domain      TEXT NOT NULL,
    version     INTEGER NOT NULL,
    eval_score  REAL,
    active      INTEGER NOT NULL,
    origin      TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spec_key ON agent_specs(capability, domain, active);

-- KB sources: per-project crawl/upload records (SENTINEL-016)
CREATE TABLE IF NOT EXISTS kb_sources (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    url         TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'web',
    status      TEXT NOT NULL DEFAULT 'pending',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kb_project ON kb_sources(project_id);

-- User feedback on task results (Gap 4: user modeling loop)
CREATE TABLE IF NOT EXISTS user_feedback (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    task_id    TEXT NOT NULL,
    run_id     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    signal     INTEGER NOT NULL,  -- +1 thumbs-up, -1 thumbs-down
    note       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_fb_run ON user_feedback(run_id);
CREATE INDEX IF NOT EXISTS idx_fb_entity ON user_feedback(entity);

-- Semantic knowledge graph: directed entity relationships (SENTINEL-016 G-06)
-- Each edge: from_entity → rel_type → to_entity (e.g. "biltiq ai → competitor → crayon")
CREATE TABLE IF NOT EXISTS entity_relations (
    id           TEXT PRIMARY KEY,
    from_entity  TEXT NOT NULL,
    rel_type     TEXT NOT NULL,
    to_entity    TEXT NOT NULL,
    boundary     TEXT NOT NULL DEFAULT 'public',
    context      TEXT NOT NULL DEFAULT '',
    project_id   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON entity_relations(from_entity);
CREATE INDEX IF NOT EXISTS idx_rel_to   ON entity_relations(to_entity);

-- Procedural memory: proven plan execution traces (SENTINEL-016 G-07)
-- Captures which step sequence produced high-quality output for a given domain,
-- so the planner can bias toward successful patterns on future tasks.
CREATE TABLE IF NOT EXISTS procedural_traces (
    id             TEXT PRIMARY KEY,
    domain         TEXT NOT NULL,
    step_sequence  TEXT NOT NULL,  -- JSON array of capability names in execution order
    eval_score     REAL,
    project_id     TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trace_domain ON procedural_traces(domain, eval_score);

-- Prospective memory: future-triggered follow-up actions (SENTINEL-016 G-09)
-- Agent schedules a task at save-time; run_dag surfaces unfired due tasks at
-- recall-time as "Pending follow-ups" context so the synthesizer acts on them.
CREATE TABLE IF NOT EXISTS prospective_tasks (
    id                TEXT PRIMARY KEY,
    entity            TEXT NOT NULL,
    trigger_condition TEXT NOT NULL,  -- human-readable when/why condition
    action_hint       TEXT NOT NULL,  -- what to do when triggered
    due_at            TEXT NOT NULL,  -- ISO-8601 UTC; checked on each run_dag
    fired             INTEGER NOT NULL DEFAULT 0,
    project_id        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ptask_entity ON prospective_tasks(entity, fired, due_at);
"""


# --------------------------------------------------------------------------- #
# Paths + connections
# --------------------------------------------------------------------------- #
def data_dir() -> Path:
    return Path(os.getenv("SENTINEL_DATA_DIR", "data"))


def db_path() -> Path:
    return data_dir() / "sentinel.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# Additive columns landed after the initial tables shipped. Each is added to an existing DB only if
# missing (SENTINEL-008 AC-8 / R-4) — old rows read back with the column default. `project_id` is
# the SENTINEL-012 (ADR-0003) scoping column; nullable, no default ⇒ legacy rows read back as None.
_RUN_MIGRATIONS = (
    ("sources", "TEXT NOT NULL DEFAULT '[]'"),
    ("run_seq", "INTEGER NOT NULL DEFAULT 0"),
    ("project_id", "TEXT"),
)
_MEMORY_MIGRATIONS = (
    ("project_id", "TEXT"),
)


def _apply_column_migrations(conn, table: str, migrations) -> None:
    """Add any missing column in ``migrations`` to ``table`` (idempotent, guarded by table_info)."""
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    for col, decl in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _ensure_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(_SCHEMA)
        _apply_column_migrations(conn, "run_records", _RUN_MIGRATIONS)
        _apply_column_migrations(conn, "memory_entries", _MEMORY_MIGRATIONS)
        # Index on the migrated column — created here (not in _SCHEMA) so it works on a pre-012 DB
        # where project_id only exists after the ALTER above.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_project ON run_records(project_id)")
        conn.commit()


def _valid_boundary(b) -> bool:
    try:
        DataBoundary(b)
        return True
    except (ValueError, KeyError):
        return False


# --------------------------------------------------------------------------- #
# Row <-> model
# --------------------------------------------------------------------------- #
def _opt_col(r: sqlite3.Row, name: str):
    """Read a column that may be absent on a row from a DB not yet migrated (ADR-0003 defensive
    read). ``project_id`` is added by an ALTER on open, but a hand-rolled old-schema row in a test
    can lack it — return None rather than raising IndexError."""
    return r[name] if name in r.keys() else None


def _row_to_entry(r: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=r["id"],
        entity=r["entity"],
        boundary=DataBoundary(r["boundary"]),
        memory_type=r["memory_type"],
        content=r["content"],
        source_label=r["source_label"],
        source_url=r["source_url"],
        created_at=r["created_at"],
        content_hash=r["content_hash"],
        strength=r["strength"],
        interval_days=r["interval_days"],
        ease=r["ease"],
        last_reinforced_at=r["last_reinforced_at"],
        access_count=r["access_count"],
        quarantined=bool(r["quarantined"]),
        project_id=_opt_col(r, "project_id"),
    )


def _row_to_run(r: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=r["id"],
        entity=r["entity"],
        target=r["target"],
        mode=r["mode"],
        backend=r["backend"],
        kind=r["kind"],
        public=r["public"],
        private=r["private"],
        gaps=r["gaps"],
        reference=r["reference"],
        finding_texts=json.loads(r["finding_texts"]),
        # pydantic coerces the list-of-dicts back into Source models (AC-8). Old rows → default '[]'/0.
        sources=json.loads(r["sources"] or "[]"),
        run_seq=r["run_seq"] or 0,
        project_id=_opt_col(r, "project_id"),
        created_at=r["created_at"],
    )


# SENTINEL-012 (ADR-0003): the `data` column is the source of truth (full model JSON); the scalar
# columns are denormalised only for indexed lookup. Reconstruct straight from `data`.
def _row_to_project(r: sqlite3.Row) -> Project:
    return Project.model_validate_json(r["data"])


def _row_to_task(r: sqlite3.Row) -> Task:
    return Task.model_validate_json(r["data"])


def _row_to_plan(r: sqlite3.Row) -> Plan:
    return Plan.model_validate_json(r["data"])


# SENTINEL-012 (ADR-0004): reconstruct an AgentSpec straight from its `data` JSON, like every other
# whole-model row (the scalar columns are denormalised duplicates used only for SQL lookup/ranking).
def _row_to_spec(r: sqlite3.Row) -> AgentSpec:
    return AgentSpec.model_validate_json(r["data"])


# --------------------------------------------------------------------------- #
# MemoryStore — the boundary choke point
# --------------------------------------------------------------------------- #
class MemoryStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    # --- THE invariant: every read goes through here -------------------------------------- #
    def recall(
        self,
        entity: str,
        allowed: Iterable[DataBoundary],
        *,
        limit: int = 8,
        token_budget: int = 1200,
        now=None,
        reinforce_on_read: bool = True,
        tier: str = "all",
        page: int = 0,
        page_size: int | None = None,
    ) -> list[MemoryEntry]:
        """Return non-quarantined entries for ``entity`` whose boundary ∈ ``allowed`` only.

        A competitor (public-only) run passes ``{PUBLIC}`` and therefore *cannot* receive a PRIVATE
        entry (AC-3). Results are ranked by decayed strength, dropped below the floor, capped at
        ``limit`` and a token budget; reading reinforces (testing effect, AC-6).

        G-08 — hierarchical paging:
        ``tier="hot"``  — only entries with decayed_strength >= HOT_THRESHOLD (reinforced ~2× or more).
        ``tier="cold"`` — entries below HOT_THRESHOLD but above STRENGTH_FLOOR.
        ``tier="all"``  — all above-floor entries (default, backward-compatible).
        ``page`` / ``page_size`` slice within the tier after strength-sorting (0-indexed).
        """
        entity = normalize_entity(entity)
        allowed_set = {DataBoundary(b) for b in allowed}
        if not allowed_set:
            return []
        placeholders = ",".join("?" for _ in allowed_set)
        values = [b.value for b in allowed_set]
        with _connect(self.path) as conn:
            rows = conn.execute(
                f"SELECT * FROM memory_entries "
                f"WHERE entity=? AND quarantined=0 AND boundary IN ({placeholders})",
                (entity, *values),
            ).fetchall()

        entries = [_row_to_entry(r) for r in rows]
        # Defense in depth: re-assert the boundary on the deserialized objects.
        entries = [e for e in entries if e.boundary in allowed_set]

        now = now or utcnow()
        scored = [(e, decayed_strength(e, now)) for e in entries]
        scored = [(e, s) for (e, s) in scored if s >= STRENGTH_FLOOR]
        # G-08: tier filter
        if tier == "hot":
            scored = [(e, s) for (e, s) in scored if s >= HOT_THRESHOLD]
        elif tier == "cold":
            scored = [(e, s) for (e, s) in scored if s < HOT_THRESHOLD]
        scored.sort(key=lambda t: t[1], reverse=True)

        # G-08: page slice (applied before token/limit capping)
        if page_size is not None:
            start = page * page_size
            scored = scored[start: start + page_size]

        selected: list[MemoryEntry] = []
        used = 0
        for entry, _ in scored[:limit]:
            cost = len(entry.content) // 4 + 1  # ~4 chars/token
            if selected and used + cost > token_budget:
                break
            selected.append(entry)
            used += cost

        if reinforce_on_read and selected:
            for entry in selected:
                reinforce(entry, ReinforceSignal.POSITIVE, now=now)
                self._update_strength(entry)
        return selected

    def list_for_entity(
        self,
        entity: str,
        *,
        allowed: Iterable[DataBoundary] | None = None,
        include_quarantined: bool = False,
    ) -> list[MemoryEntry]:
        """Read-only memory for HUMAN DISPLAY (SENTINEL-004). NOT the agent path.

        Unlike :meth:`recall`, this does **no** reinforcement, **no** token budget, and **no**
        mode gate — an operator browsing an account sees everything, unchanged. The read-only
        guarantee (AC-5) is structural: the method issues only ``SELECT``, so a page fetch can
        never mutate ``strength`` / ``access_count`` / ``last_reinforced_at``. Never inject the
        result into a prompt; agents use :meth:`recall`, which is the sole boundary choke-point.

        ``allowed`` optionally narrows to a boundary set (the page renders PUBLIC and PRIVATE in
        separate badged sections by calling this once per boundary). Results are strongest-first
        (``strength DESC``), ties broken by recency — the most-reinforced facts lead, which is
        what an analyst wants before a call.
        """
        entity = normalize_entity(entity)
        sql = "SELECT * FROM memory_entries WHERE entity=?"
        params: list = [entity]
        if not include_quarantined:
            sql += " AND quarantined=0"
        if allowed is not None:
            allowed_set = {DataBoundary(b) for b in allowed}
            if not allowed_set:
                return []
            placeholders = ",".join("?" for _ in allowed_set)
            sql += f" AND boundary IN ({placeholders})"
            params.extend(b.value for b in allowed_set)
        sql += " ORDER BY strength DESC, created_at DESC"
        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def write(self, entry: MemoryEntry) -> str:
        """Insert an entry. Fail-closed on bad boundary (quarantine); dedup → reinforce (AC-4/7)."""
        if not _valid_boundary(entry.boundary):
            entry.quarantined = True
            self._insert(entry, boundary_value=str(entry.boundary))
            return entry.id

        bval = DataBoundary(entry.boundary).value
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM memory_entries "
                "WHERE entity=? AND boundary=? AND content_hash=? AND quarantined=0 LIMIT 1",
                (entry.entity, bval, entry.content_hash),
            ).fetchone()
        if row is not None:
            existing = _row_to_entry(row)
            reinforce(existing, ReinforceSignal.POSITIVE)
            self._update_strength(existing)
            return existing.id

        self._insert(entry, boundary_value=bval)
        return entry.id

    def process_run(self, entity: str, artifact) -> int:
        """Extract findings from a finished artifact and write them as boundary-tagged entries."""
        from sentinel.memory.extraction import extract_entries

        entries = extract_entries(entity, artifact)
        for entry in entries:
            self.write(entry)
        return len(entries)

    # ---------------------------------------------------------------------- #
    # Knowledge graph: entity relations (SENTINEL-016 G-06)
    # ---------------------------------------------------------------------- #

    def upsert_relation(self, rel: "EntityRelation") -> None:
        """Insert or replace a directed entity relation edge. Fail-soft."""
        try:
            with _connect(self.path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO entity_relations "
                    "(id, from_entity, rel_type, to_entity, boundary, context, project_id, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        rel.id, rel.from_entity, rel.rel_type, rel.to_entity,
                        rel.boundary.value, rel.context,
                        rel.project_id, rel.created_at.isoformat(),
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def get_related(
        self,
        entity: str,
        *,
        allowed_boundaries: "set[DataBoundary] | None" = None,
    ) -> list["EntityRelation"]:
        """Return all edges where ``entity`` is either the source or target.

        ``allowed_boundaries`` defaults to ``{PUBLIC}`` — matches the recall() contract.
        Never raises (fail-soft).
        """
        allowed = allowed_boundaries or {DataBoundary.PUBLIC}
        norm = normalize_entity(entity)
        placeholders = ",".join("?" for _ in allowed)
        try:
            with _connect(self.path) as conn:
                rows = conn.execute(
                    f"SELECT * FROM entity_relations "  # noqa: S608
                    f"WHERE (from_entity=? OR to_entity=?) AND boundary IN ({placeholders})"
                    " ORDER BY created_at DESC",
                    (norm, norm, *[b.value for b in allowed]),
                ).fetchall()
            return [
                EntityRelation(
                    id=r["id"], from_entity=r["from_entity"], rel_type=r["rel_type"],
                    to_entity=r["to_entity"], boundary=DataBoundary(r["boundary"]),
                    context=r["context"] or "", project_id=r["project_id"],
                )
                for r in rows
            ]
        except Exception:
            return []

    def purge_entity(self, entity: str) -> None:
        """Remove an entity's memory AND run history (AC-9)."""
        entity = normalize_entity(entity)
        with _connect(self.path) as conn:
            conn.execute("DELETE FROM memory_entries WHERE entity=?", (entity,))
            conn.execute("DELETE FROM run_records WHERE entity=?", (entity,))
            conn.commit()

    def decay(self, *, now=None) -> int:
        """Drop entries that have decayed below the floor (scheduled housekeeping). Returns count."""
        now = now or utcnow()
        removed = 0
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM memory_entries WHERE quarantined=0"
            ).fetchall()
            for r in rows:
                if decayed_strength(_row_to_entry(r), now) < STRENGTH_FLOOR:
                    conn.execute("DELETE FROM memory_entries WHERE id=?", (r["id"],))
                    removed += 1
            conn.commit()
        return removed

    def count(self, entity: str | None = None, *, include_quarantined: bool = False) -> int:
        sql = "SELECT COUNT(*) AS n FROM memory_entries WHERE 1=1"
        params: list = []
        if not include_quarantined:
            sql += " AND quarantined=0"
        if entity is not None:
            sql += " AND entity=?"
            params.append(normalize_entity(entity))
        with _connect(self.path) as conn:
            return conn.execute(sql, params).fetchone()["n"]

    # --- internals ------------------------------------------------------------------------ #
    def _insert(self, entry: MemoryEntry, *, boundary_value: str) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO memory_entries "
                "(id, entity, boundary, memory_type, content, source_label, source_url, "
                " created_at, content_hash, strength, interval_days, ease, last_reinforced_at, "
                " access_count, quarantined, project_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry.id,
                    entry.entity,
                    boundary_value,
                    entry.memory_type.value
                    if hasattr(entry.memory_type, "value")
                    else str(entry.memory_type),
                    entry.content,
                    entry.source_label,
                    entry.source_url,
                    entry.created_at.isoformat(),
                    entry.content_hash,
                    entry.strength,
                    entry.interval_days,
                    entry.ease,
                    entry.last_reinforced_at.isoformat(),
                    entry.access_count,
                    int(entry.quarantined),
                    entry.project_id,
                ),
            )
            conn.commit()

    def _update_strength(self, entry: MemoryEntry) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "UPDATE memory_entries SET strength=?, interval_days=?, ease=?, "
                "last_reinforced_at=?, access_count=? WHERE id=?",
                (
                    entry.strength,
                    entry.interval_days,
                    entry.ease,
                    entry.last_reinforced_at.isoformat(),
                    entry.access_count,
                    entry.id,
                ),
            )
            conn.commit()

    # ---------------------------------------------------------------------- #
    # Prospective memory (SENTINEL-016 G-09)
    # ---------------------------------------------------------------------- #

    def schedule_task(
        self,
        entity: str,
        trigger_condition: str,
        action_hint: str,
        due_at: "datetime",
        *,
        project_id: str | None = None,
    ) -> str:
        """Schedule a future follow-up for ``entity``.

        Returns the new task id. Fail-soft: any DB error is swallowed and an
        empty string is returned so callers never crash.
        """
        import uuid as _uuid
        from sentinel.memory.schema import utcnow as _utcnow
        task_id = _uuid.uuid4().hex
        try:
            with _connect(self.path) as conn:
                conn.execute(
                    "INSERT INTO prospective_tasks "
                    "(id, entity, trigger_condition, action_hint, due_at, project_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (task_id, normalize_entity(entity), trigger_condition, action_hint,
                     due_at.isoformat(), project_id),
                )
                conn.commit()
        except Exception:
            return ""
        return task_id

    def due_tasks(
        self,
        entity: str,
        *,
        now: "datetime | None" = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """Return unfired prospective tasks for ``entity`` that are due on or before ``now``.

        Each dict: ``{id, trigger_condition, action_hint, due_at}``. Fail-soft → [].
        """
        from sentinel.memory.schema import utcnow as _utcnow
        now = now or _utcnow()
        try:
            sql = (
                "SELECT id, trigger_condition, action_hint, due_at "
                "FROM prospective_tasks "
                "WHERE entity=? AND fired=0 AND due_at <= ?"
            )
            params: list = [normalize_entity(entity), now.isoformat()]
            if project_id is not None:
                sql += " AND (project_id=? OR project_id IS NULL)"
                params.append(project_id)
            sql += " ORDER BY due_at ASC"
            with _connect(self.path) as conn:
                rows = conn.execute(sql, params).fetchall()
            return [
                {"id": r["id"], "trigger_condition": r["trigger_condition"],
                 "action_hint": r["action_hint"], "due_at": r["due_at"]}
                for r in rows
            ]
        except Exception:
            return []

    def mark_fired(self, task_id: str) -> None:
        """Mark a prospective task as fired so it won't surface again. Fail-soft."""
        try:
            with _connect(self.path) as conn:
                conn.execute(
                    "UPDATE prospective_tasks SET fired=1 WHERE id=?", (task_id,)
                )
                conn.commit()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# RunStore — episodic log (dashboard reads this; survives restart, AC-1)
# --------------------------------------------------------------------------- #
class RunStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    def save(self, rec: RunRecord) -> str:
        # 1-based per-entity sequence (SENTINEL-008 AC-8): assigned at save time from prior count, so
        # the caller need not track it. ``rec.run_seq`` is set so the in-memory record reflects it.
        if not rec.run_seq:
            rec.run_seq = len(self.runs_for(rec.entity)) + 1
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO run_records "
                "(id, entity, target, mode, backend, kind, public, private, gaps, reference, "
                " finding_texts, sources, run_seq, project_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rec.id,
                    rec.entity,
                    rec.target,
                    rec.mode,
                    rec.backend,
                    rec.kind,
                    rec.public,
                    rec.private,
                    rec.gaps,
                    rec.reference,
                    json.dumps(rec.finding_texts),
                    json.dumps([s.model_dump() for s in rec.sources]),
                    rec.run_seq,
                    rec.project_id,
                    rec.created_at.isoformat(),
                ),
            )
            conn.commit()
        # G-05: embed and index the run for semantic episodic recall. Fail-soft — a missing
        # embed server must never prevent a run record from being saved.
        try:
            from sentinel.memory.episodic_vector import embed_and_index_run
            embed_and_index_run(
                rec.id, rec.entity, rec.finding_texts, data_dir(), project_id=rec.project_id
            )
        except Exception:
            pass
        return rec.id

    # SENTINEL-012 (ADR-0003): every run-side read takes an OPTIONAL ``project_id``. Default None ⇒
    # no filter ⇒ byte-identical to pre-012 (legacy NULL rows flow through). Runs are episodic, so
    # project_id is a real scoping key here (unlike memory, which is deliberately cross-project).
    def list(self, limit: int = 50, *, project_id: str | None = None) -> list[RunRecord]:
        sql = "SELECT * FROM run_records"
        params: list = []
        if project_id is not None:
            sql += " WHERE project_id=?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]

    def all(self, *, project_id: str | None = None) -> list[RunRecord]:
        sql = "SELECT * FROM run_records"
        params: list = []
        if project_id is not None:
            sql += " WHERE project_id=?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC"
        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]

    def count(self, *, project_id: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM run_records"
        params: list = []
        if project_id is not None:
            sql += " WHERE project_id=?"
            params.append(project_id)
        with _connect(self.path) as conn:
            return conn.execute(sql, params).fetchone()["n"]

    def latest_for(self, entity: str, *, project_id: str | None = None) -> RunRecord | None:
        entity = normalize_entity(entity)
        sql = "SELECT * FROM run_records WHERE entity=?"
        params: list = [entity]
        if project_id is not None:
            sql += " AND project_id=?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with _connect(self.path) as conn:
            row = conn.execute(sql, params).fetchone()
        return _row_to_run(row) if row is not None else None

    # --- entity-centric reads (SENTINEL-004) ---------------------------------------------- #
    def entities(self, *, project_id: str | None = None) -> list[EntitySummary]:
        """One summary per distinct entity, newest-activity first (AC-1).

        A single ordered scan grouped in Python: because rows arrive newest-first, the first
        time an entity is seen is its latest run — so the display name and ``last_run_at`` come
        from that row, and dict insertion order is already newest-activity-first.
        """
        sql = "SELECT * FROM run_records"
        params: list = []
        if project_id is not None:
            sql += " WHERE project_id=?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC"
        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        by_entity: dict[str, list[RunRecord]] = {}
        for rec in (_row_to_run(r) for r in rows):
            by_entity.setdefault(rec.entity, []).append(rec)
        return [EntitySummary.from_runs(entity, recs) for entity, recs in by_entity.items()]

    def runs_for(self, entity: str, *, project_id: str | None = None) -> list[RunRecord]:
        """That entity's runs, newest-first (AC-3) — the account timeline."""
        entity = normalize_entity(entity)
        sql = "SELECT * FROM run_records WHERE entity=?"
        params: list = [entity]
        if project_id is not None:
            sql += " AND project_id=?"
            params.append(project_id)
        sql += " ORDER BY created_at DESC"
        with _connect(self.path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]

    def recall_episodes(
        self,
        target: str,
        *,
        top_k: int = 3,
        mode: str | None = None,
        project_id: str | None = None,
    ) -> list[RunRecord]:
        """Top-K episodic recall for a target — exact entity match + keyword LIKE search +
        optional KB-semantic supplement when ``project_id`` is supplied.

        Strategy (priority):
        1. Exact entity match (same normalized target) — most recent runs first.
        2. Keyword LIKE search over ``finding_texts`` JSON for words ≥ 4 chars from the target.
        3. KB semantic search: when ``project_id`` is provided and results < top_k, query the
           project's ChromaDB index for the target phrase and find run records that cited the
           matched source URLs — bridging semantic KB content to episodic run history.
        Results are deduped by entity (each entity appears at most once, its newest run).

        Never raises — any storage error returns ``[]`` (fail-soft, NFR-03 / SENTINEL-015 FR-02).
        """
        entity = normalize_entity(target)
        keywords = [w for w in entity.split() if len(w) >= 4]

        seen: set[str] = set()
        results: list[RunRecord] = []

        try:
            with _connect(self.path) as conn:
                # 1. Exact entity match
                exact_sql = "SELECT * FROM run_records WHERE entity=? ORDER BY created_at DESC"
                for r in conn.execute(exact_sql, (entity,)).fetchall():
                    rec = _row_to_run(r)
                    if rec.entity not in seen:
                        seen.add(rec.entity)
                        results.append(rec)
                    if len(results) >= top_k:
                        return results

                # 2. Keyword LIKE search
                if keywords:
                    like_conds = " OR ".join("finding_texts LIKE ?" for _ in keywords)
                    params: list = [f"%{k}%" for k in keywords]
                    kw_sql = f"SELECT * FROM run_records WHERE ({like_conds})"  # noqa: S608
                    if mode:
                        kw_sql += " AND mode=?"
                        params.append(mode)
                    kw_sql += " ORDER BY created_at DESC LIMIT ?"
                    params.append(top_k * 5)
                    for r in conn.execute(kw_sql, params).fetchall():
                        rec = _row_to_run(r)
                        if rec.entity not in seen:
                            seen.add(rec.entity)
                            results.append(rec)
                        if len(results) >= top_k:
                            break

                # 3. KB semantic supplement — only when short on results and project_id given
                if project_id and len(results) < top_k:
                    try:
                        import os

                        from sentinel.kb.search import hybrid_search

                        kb_dir = str(data_dir() / "kb")
                        kb_hits = hybrid_search(project_id, kb_dir, entity, rerank_top_k=5)
                        related_urls = [h.url for h in kb_hits if h.url]
                        if related_urls:
                            url_params: list = [f"%{u}%" for u in related_urls]
                            url_conds = " OR ".join("sources LIKE ?" for _ in url_params)
                            url_params.append(top_k * 3)
                            url_sql = (  # noqa: S608
                                f"SELECT * FROM run_records WHERE ({url_conds})"
                                " ORDER BY created_at DESC LIMIT ?"
                            )
                            for r in conn.execute(url_sql, url_params).fetchall():
                                rec = _row_to_run(r)
                                if rec.entity not in seen:
                                    seen.add(rec.entity)
                                    results.append(rec)
                                if len(results) >= top_k:
                                    break
                    except Exception:
                        pass  # KB unavailable or not yet indexed — degrade silently

                # 4. Dense vector search over episodic ChromaDB index (G-05)
                if len(results) < top_k:
                    try:
                        from sentinel.memory.episodic_vector import semantic_search_run_ids

                        run_ids = semantic_search_run_ids(entity, data_dir(), top_k=top_k * 2)
                        if run_ids:
                            ph = ",".join("?" for _ in run_ids)
                            vec_sql = (  # noqa: S608
                                f"SELECT * FROM run_records WHERE id IN ({ph})"
                                " ORDER BY created_at DESC"
                            )
                            for r in conn.execute(vec_sql, run_ids).fetchall():
                                rec = _row_to_run(r)
                                if rec.entity not in seen:
                                    seen.add(rec.entity)
                                    results.append(rec)
                                if len(results) >= top_k:
                                    break
                    except Exception:
                        pass  # episodic vector index unavailable — degrade silently
        except Exception:
            return []

        return results[:top_k]

    def delete_run(self, run_id: str, *, project_id: str | None = None) -> bool:
        """Delete a single run record by id. Returns True if a row was deleted.

        When ``project_id`` is supplied the DELETE is scoped: the run must belong to that project
        or rowcount is 0 (returns False). This prevents IDOR — callers in a project context must
        always pass project_id so a run from another project cannot be deleted via a crafted URL.
        """
        try:
            with _connect(self.path) as conn:
                if project_id is not None:
                    cur = conn.execute(
                        "DELETE FROM run_records WHERE id=? AND project_id=?",
                        (run_id, project_id),
                    )
                else:
                    cur = conn.execute("DELETE FROM run_records WHERE id=?", (run_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False


# --------------------------------------------------------------------------- #
# ProjectStore — Project / Task / Plan (SENTINEL-012, ADR-0003)
# --------------------------------------------------------------------------- #
class ProjectStore:
    """Project / Task / Plan persistence.

    The ``data`` column holds the full pydantic JSON (the source of truth); the scalar columns
    (``project_id``/``task_id``/``status``) are denormalised only for indexed lookup. There is no
    FK — referential integrity is the store's job (ADR-0003 §3.4), via two complementary mechanisms:
    ``purge_project`` cascades, AND task/plan reads are *orphan-tolerant* (they never join a parent,
    so a row whose parent was removed still reads back cleanly rather than crashing).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    # --- projects ------------------------------------------------------------------------- #
    def save_project(self, p: Project) -> str:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects (id, name, data, created_at) VALUES (?,?,?,?)",
                (p.id, p.name, p.model_dump_json(), p.created_at),
            )
            conn.commit()
        return p.id

    def get_project(self, project_id: str) -> Project | None:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return _row_to_project(row) if row is not None else None

    def get_project_by_name(self, name: str) -> "Project | None":
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE lower(name)=lower(?) ORDER BY created_at DESC LIMIT 1",
                (name,),
            ).fetchone()
        return _row_to_project(row) if row is not None else None

    def list_projects(self) -> list[Project]:
        with _connect(self.path) as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [_row_to_project(r) for r in rows]

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and cascade to its tasks and plans. Returns True if the project existed."""
        with _connect(self.path) as conn:
            task_ids = [
                r["id"] for r in
                conn.execute("SELECT id FROM tasks WHERE project_id=?", (project_id,)).fetchall()
            ]
            for tid in task_ids:
                conn.execute("DELETE FROM plans WHERE task_id=?", (tid,))
            conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
            cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()
        return cur.rowcount > 0

    # --- tasks ---------------------------------------------------------------------------- #
    def save_task(self, t: Task) -> str:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (id, project_id, status, data, created_at) "
                "VALUES (?,?,?,?,?)",
                (t.id, t.project_id, t.status, t.model_dump_json(), t.created_at),
            )
            conn.commit()
        return t.id

    def get_task(self, task_id: str) -> Task | None:
        """Read a task by id. Orphan-tolerant: returns it even if its project row is gone."""
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return _row_to_task(row) if row is not None else None

    def tasks_for_project(self, project_id: str) -> list[Task]:
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY created_at DESC", (project_id,)
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    def delete_task(self, task_id: str) -> None:
        """Remove a task and its plan(s) — lets the operator tidy the Tasks list (no cascade beyond
        plans; runs/artifacts are episodic and kept for the audit trail)."""
        with _connect(self.path) as conn:
            conn.execute("DELETE FROM plans WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            conn.commit()

    # --- plans ---------------------------------------------------------------------------- #
    def save_plan(self, pl: Plan) -> str:
        # One plan per task. The plan id is deterministic (``plan-{task_id}``), so a re-plan REPLACES
        # by id — but any SIBLING rows from the old id-collision era (e.g. a stale 's1' plan saved under
        # a step slug) would otherwise linger and be served ahead of the fresh plan by ``plan_for_task``.
        # Drop them in the same transaction so a task always resolves to exactly its current plan.
        with _connect(self.path) as conn:
            conn.execute("DELETE FROM plans WHERE task_id=? AND id<>?", (pl.task_id, pl.id))
            conn.execute(
                "INSERT OR REPLACE INTO plans (id, task_id, status, data) VALUES (?,?,?,?)",
                (pl.id, pl.task_id, pl.status, pl.model_dump_json()),
            )
            conn.commit()
        return pl.id

    def get_plan(self, plan_id: str) -> Plan | None:
        """Read a plan by id. Orphan-tolerant: returns it even if its task row is gone."""
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return _row_to_plan(row) if row is not None else None

    def plan_for_task(self, task_id: str) -> Plan | None:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM plans WHERE task_id=? LIMIT 1", (task_id,)).fetchone()
        return _row_to_plan(row) if row is not None else None

    # --- cascade (the FK substitute) ------------------------------------------------------ #
    def purge_project(self, project_id: str) -> None:
        """Delete a project and its tasks/plans, and NULL ``project_id`` on its runs/memory.

        Runs and memory SURVIVE (they are entity-owned, not project-owned) — only their project
        provenance is cleared (ADR-0003 §3.4). Parameterised throughout; no f-string SQL.
        """
        with _connect(self.path) as conn:
            task_ids = [
                r["id"] for r in conn.execute(
                    "SELECT id FROM tasks WHERE project_id=?", (project_id,)
                )
            ]
            for tid in task_ids:
                conn.execute("DELETE FROM plans WHERE task_id=?", (tid,))
            conn.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.execute("UPDATE run_records SET project_id=NULL WHERE project_id=?", (project_id,))
            conn.execute("UPDATE memory_entries SET project_id=NULL WHERE project_id=?", (project_id,))
            conn.commit()


class SpecStore:
    """`agent_specs` persistence — the AgentRegistry's durable home (ADR-0004).

    The same row↔model shape as ``ProjectStore``: ``data`` holds the full ``AgentSpec`` JSON (the
    source of truth); the scalar columns are denormalised only so ``resolve`` can look up by
    ``(capability, domain)`` and rank by score/version in SQL+Python without loading every spec.
    There is no FK and no ``UNIQUE`` — supersession/versioning is the registry layer's job (ADR-0004
    §Alternatives), mirroring how ADR-0003 keeps integrity in code, not schema. Every write is
    parameterised (no f-string SQL — AP #5).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    def save_spec(self, spec: AgentSpec) -> str:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_specs "
                "(id, capability, domain, version, eval_score, active, origin, data) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (spec.id, spec.capability, spec.domain, spec.version, spec.eval_score,
                 int(spec.active), spec.origin, spec.model_dump_json()),
            )
            conn.commit()
        return spec.id

    def get_spec(self, spec_id: str) -> AgentSpec | None:
        with _connect(self.path) as conn:
            row = conn.execute("SELECT * FROM agent_specs WHERE id=?", (spec_id,)).fetchone()
        return _row_to_spec(row) if row is not None else None

    def active_specs(self, capability: str, domain: str) -> list[AgentSpec]:
        """Every ACTIVE spec for a ``(capability, domain)`` key — the candidate set ``resolve``
        ranks. Ordering is left to the registry (it ranks by score then version)."""
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_specs WHERE capability=? AND domain=? AND active=1",
                (capability, domain),
            ).fetchall()
        return [_row_to_spec(r) for r in rows]

    def deactivate(self, spec_id: str) -> None:
        """Mark a spec inactive (supersession) — it stops being a ``resolve`` candidate but its row
        survives for provenance/audit."""
        with _connect(self.path) as conn:
            conn.execute("UPDATE agent_specs SET active=0 WHERE id=?", (spec_id,))
            conn.commit()

    def update_eval_score(self, spec_id: str, score: float) -> None:
        """Write a grading result back to the spec row so resolve() ranks it correctly.

        Also updates the `data` JSON so the reconstructed AgentSpec carries the score.
        Fail-soft: any error is silently swallowed — a scoring miss must never break a run.
        """
        try:
            spec = self.get_spec(spec_id)
            if spec is None:
                return
            spec.eval_score = score
            with _connect(self.path) as conn:
                conn.execute(
                    "UPDATE agent_specs SET eval_score=?, data=? WHERE id=?",
                    (score, spec.model_dump_json(), spec_id),
                )
                conn.commit()
        except Exception:
            pass

    def list_specs(self) -> list[AgentSpec]:
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM agent_specs ORDER BY capability, domain, version DESC"
            ).fetchall()
        return [_row_to_spec(r) for r in rows]

    # ---------------------------------------------------------------------- #
    # Procedural memory (SENTINEL-016 G-07)
    # ---------------------------------------------------------------------- #

    def record_procedural_trace(
        self,
        domain: str,
        steps: list[str],
        *,
        eval_score: float | None = None,
        project_id: str | None = None,
    ) -> str:
        """Persist a proven plan structure so the planner can reuse successful patterns.

        ``steps`` is the ordered list of capability names that executed successfully.
        Returns the new trace id. Fail-soft.
        """
        import uuid as _uuid
        trace_id = _uuid.uuid4().hex
        try:
            with _connect(self.path) as conn:
                conn.execute(
                    "INSERT INTO procedural_traces (id, domain, step_sequence, eval_score, project_id) "
                    "VALUES (?,?,?,?,?)",
                    (trace_id, domain, json.dumps(steps), eval_score, project_id),
                )
                conn.commit()
        except Exception:
            pass
        return trace_id

    def best_traces_for(self, domain: str, top_k: int = 3) -> list[dict]:
        """Return up to ``top_k`` highest-scored procedural traces for ``domain``.

        Each dict has ``steps`` (list[str]), ``eval_score`` (float|None), ``id``.
        Returns [] on any error (fail-soft).
        """
        try:
            with _connect(self.path) as conn:
                rows = conn.execute(
                    "SELECT id, step_sequence, eval_score FROM procedural_traces "  # noqa: S608
                    "WHERE domain=? ORDER BY eval_score DESC NULLS LAST LIMIT ?",
                    (domain, top_k),
                ).fetchall()
            return [
                {"id": r["id"], "steps": json.loads(r["step_sequence"]), "eval_score": r["eval_score"]}
                for r in rows
            ]
        except Exception:
            return []


class KBStore:
    """Persists KB source records (crawl status, chunk counts) in SQLite."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    def save(self, source: dict) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kb_sources "
                "(id, project_id, url, source_type, status, chunk_count, error) "
                "VALUES (?,?,?,?,?,?,?)",
                (source["id"], source["project_id"], source["url"],
                 source["source_type"], source["status"],
                 source["chunk_count"], source.get("error")),
            )
            conn.commit()

    def list_for_project(self, project_id: str) -> list[dict]:
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM kb_sources WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, source_id: str) -> dict | None:
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM kb_sources WHERE id=?", (source_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_status(
        self, source_id: str, status: str, chunk_count: int = 0, error: str | None = None
    ) -> None:
        with _connect(self.path) as conn:
            conn.execute(
                "UPDATE kb_sources SET status=?, chunk_count=?, error=? WHERE id=?",
                (status, chunk_count, error, source_id),
            )
            conn.commit()

    def delete(self, source_id: str, project_id: str) -> bool:
        with _connect(self.path) as conn:
            cur = conn.execute(
                "DELETE FROM kb_sources WHERE id=? AND project_id=?",
                (source_id, project_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete_for_project(self, project_id: str) -> None:
        with _connect(self.path) as conn:
            conn.execute("DELETE FROM kb_sources WHERE project_id=?", (project_id,))
            conn.commit()


# --------------------------------------------------------------------------- #
# FeedbackStore — user thumbs-up/down on task results (Gap 4: user modeling)
# --------------------------------------------------------------------------- #
class FeedbackStore:
    """Persist and read user feedback signals on task run results.

    A +1 signal (thumbs-up) triggers SM-2 reinforcement on the memory entries that
    were stored from the same entity during that run — so approved research stays in
    recall longer. A -1 signal weakens those entries by applying a negative reinforce
    (lowering ease/strength), making low-quality results fade faster.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    def save(
        self,
        *,
        project_id: str,
        task_id: str,
        run_id: str,
        entity: str,
        signal: int,
        note: str | None = None,
    ) -> str:
        import uuid

        fb_id = str(uuid.uuid4())
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO user_feedback (id, project_id, task_id, run_id, entity, signal, note) "
                "VALUES (?,?,?,?,?,?,?)",
                (fb_id, project_id, task_id, run_id, normalize_entity(entity), signal, note),
            )
            conn.commit()
        self._apply_to_memory(entity=entity, signal=signal)
        return fb_id

    def list_for_run(self, run_id: str) -> list[dict]:
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM user_feedback WHERE run_id=? ORDER BY created_at DESC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def aggregate_signal(self, entity: str) -> int:
        """Sum of all +1/-1 signals for an entity — positive = more good runs than bad."""
        entity = normalize_entity(entity)
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(signal), 0) AS total FROM user_feedback WHERE entity=?",
                (entity,),
            ).fetchone()
        return int(row["total"]) if row else 0

    def _apply_to_memory(self, *, entity: str, signal: int) -> None:
        """Reinforce (+1) or weaken (-1) the entity's memory entries in response to feedback."""
        if signal == 0:
            return
        try:
            mem = MemoryStore(self.path)
            from sentinel.memory.schema import DataBoundary

            entries = mem.list_for_entity(
                entity, allowed=[DataBoundary.PUBLIC, DataBoundary.PRIVATE]
            )
            for entry in entries:
                if signal > 0:
                    reinforce(entry, ReinforceSignal.POSITIVE)
                else:
                    # Weaken: partial decay — lower strength and ease without quarantining
                    entry.strength = max(entry.strength * 0.6, STRENGTH_FLOOR)
                    entry.ease = max(entry.ease - 0.15, 1.3)
                mem._update_strength(entry)
        except Exception:
            pass  # feedback never breaks the request path
