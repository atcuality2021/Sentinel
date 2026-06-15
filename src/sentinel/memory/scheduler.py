# src/sentinel/memory/scheduler.py
"""CrawlScheduler — decides WHEN to enqueue crawl jobs, nothing else."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sentinel.memory.schema import normalize_entity, utcnow

PRIORITY_INTERVALS: dict[str, dict[str, timedelta]] = {
    "high":   {"website": timedelta(hours=1),  "email": timedelta(hours=1),
               "youtube": timedelta(hours=2),  "social": timedelta(hours=3)},
    "medium": {"website": timedelta(hours=6),  "email": timedelta(hours=6),
               "youtube": timedelta(hours=12), "social": timedelta(hours=12)},
    "low":    {"website": timedelta(hours=24), "email": timedelta(hours=24),
               "youtube": timedelta(hours=48), "social": timedelta(hours=48)},
}

_PRIORITY_INT: dict[str, int] = {"high": 10, "medium": 5, "low": 2}


class CrawlScheduler:
    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)

    def tick(self) -> int:
        """Enqueue overdue jobs for all configured entities. Returns jobs inserted."""
        now = utcnow()
        inserted = 0
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            configs = conn.execute("SELECT * FROM entity_source_config").fetchall()
            for cfg in configs:
                entity = cfg["entity"]
                priority_str = cfg["priority"] or "medium"
                intervals = PRIORITY_INTERVALS[priority_str]
                priority_int = _PRIORITY_INT[priority_str]
                sources: list[str] = json.loads(cfg["sources_enabled"] or '["website"]')
                for source in sources:
                    if source not in intervals:
                        continue
                    # Skip if a pending or running job already exists
                    existing = conn.execute(
                        "SELECT 1 FROM crawl_jobs WHERE entity=? AND source_type=? "
                        "AND status IN ('pending','running')",
                        (entity, source),
                    ).fetchone()
                    if existing:
                        continue
                    # Check last done
                    last_row = conn.execute(
                        "SELECT MAX(done_at) as last FROM crawl_jobs "
                        "WHERE entity=? AND source_type=? AND status='done'",
                        (entity, source),
                    ).fetchone()
                    last_done_str = last_row["last"] if last_row else None
                    if last_done_str:
                        last_done = datetime.fromisoformat(last_done_str).replace(tzinfo=timezone.utc)
                        if now - last_done < intervals[source]:
                            continue  # not yet due
                    # Enqueue (UNIQUE index prevents duplicates within same hour window)
                    try:
                        conn.execute(
                            "INSERT INTO crawl_jobs "
                            "(id, entity, source_type, status, priority, scheduled_at) "
                            "VALUES (?, ?, ?, 'pending', ?, ?)",
                            (uuid4().hex, entity, source, priority_int, now.isoformat()),
                        )
                        inserted += 1
                    except sqlite3.IntegrityError:
                        pass  # duplicate in same hour window — safe to ignore
            conn.commit()
        return inserted

    def force_enqueue(self, entity: str, *, priority: int = 10) -> int:
        """Immediately enqueue all enabled sources for entity regardless of interval."""
        entity = normalize_entity(entity)
        now = utcnow()
        inserted = 0
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            cfg_row = conn.execute(
                "SELECT sources_enabled FROM entity_source_config WHERE entity=?", (entity,)
            ).fetchone()
            if not cfg_row:
                return 0
            sources: list[str] = json.loads(cfg_row["sources_enabled"] or '["website"]')
            for source in sources:
                # DELETE only terminal rows in the same hour window so force always lands
                # but never orphans an in-flight worker (status='running').
                conn.execute(
                    "DELETE FROM crawl_jobs WHERE entity=? AND source_type=? "
                    "AND status IN ('done', 'failed') "
                    "AND strftime('%Y-%m-%dT%H', scheduled_at) = strftime('%Y-%m-%dT%H', ?)",
                    (entity, source, now.isoformat()),
                )
                try:
                    conn.execute(
                        "INSERT INTO crawl_jobs "
                        "(id, entity, source_type, status, priority, scheduled_at) "
                        "VALUES (?, ?, ?, 'pending', ?, ?)",
                        (uuid4().hex, entity, source, priority, now.isoformat()),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass  # running job already occupies this hour window — leave it alone
            conn.commit()
        return inserted
