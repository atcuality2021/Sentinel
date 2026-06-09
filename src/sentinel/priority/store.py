"""Persisted, auditable priority snapshots (SENTINEL-010, AC-11).

One ``priority_records`` table in the **same** SENTINEL-002 SQLite file (OQ-1: one data dir, one
backup unit). Each compute appends a row, so the table is an audit trail — ``latest_for`` returns
the newest snapshot, ``history_for`` the full series. Mirrors the short-lived WAL connection pattern
of ``memory/store.py`` so the async web app and any batch recompute can share the file safely.

No secrets, no PII beyond the entity name the operator already sees; reasons/breakdown are stored as
JSON exactly as computed, so a reviewer can replay how a score was reached.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sentinel.memory import db_path
from sentinel.memory.schema import normalize_entity, utcnow
from sentinel.priority.engine import PriorityScore, Reason

_SCHEMA = """
CREATE TABLE IF NOT EXISTS priority_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity       TEXT NOT NULL,
    display_name TEXT NOT NULL,
    score        REAL NOT NULL,
    tier         TEXT NOT NULL,
    breakdown    TEXT NOT NULL,
    reasons      TEXT NOT NULL,
    notes        TEXT NOT NULL,
    computed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priority_entity ON priority_records(entity, computed_at);
"""


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(_SCHEMA)


def _row_to_score(r: sqlite3.Row) -> PriorityScore:
    return PriorityScore(
        entity=r["entity"],
        display_name=r["display_name"],
        score=r["score"],
        tier=r["tier"],
        breakdown=json.loads(r["breakdown"]),
        reasons=[Reason(**d) for d in json.loads(r["reasons"])],
        notes=json.loads(r["notes"]),
        computed_at=r["computed_at"],
    )


class PriorityStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else db_path()
        _ensure_schema(self.path)

    def save(self, score: PriorityScore) -> None:
        """Append one snapshot (history-preserving — never overwrites a prior compute)."""
        with _connect(self.path) as conn:
            conn.execute(
                "INSERT INTO priority_records "
                "(entity, display_name, score, tier, breakdown, reasons, notes, computed_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    normalize_entity(score.entity),
                    score.display_name,
                    score.score,
                    score.tier,
                    json.dumps(score.breakdown),
                    json.dumps([r.model_dump(mode="json") for r in score.reasons]),
                    json.dumps(score.notes),
                    (score.computed_at or utcnow()).isoformat()
                    if hasattr(score.computed_at, "isoformat")
                    else str(score.computed_at),
                ),
            )
            conn.commit()

    def latest_for(self, entity: str) -> PriorityScore | None:
        """The most recent snapshot for one entity, or None if never computed."""
        key = normalize_entity(entity)
        with _connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM priority_records WHERE entity=? ORDER BY computed_at DESC, id DESC "
                "LIMIT 1",
                (key,),
            ).fetchone()
        return _row_to_score(row) if row is not None else None

    def history_for(self, entity: str) -> list[PriorityScore]:
        """Full audit series for one entity, newest-first."""
        key = normalize_entity(entity)
        with _connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM priority_records WHERE entity=? ORDER BY computed_at DESC, id DESC",
                (key,),
            ).fetchall()
        return [_row_to_score(r) for r in rows]
