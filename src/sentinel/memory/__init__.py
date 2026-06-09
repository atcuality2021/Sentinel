"""Sentinel memory harness (SENTINEL-002).

Durable, boundary-aware memory: System-2 entity memory (``MemoryStore``) + an episodic run log
(``RunStore``), both in one SQLite file. The boundary invariant — PRIVATE memory can never enter a
public-only run — is enforced at the single ``MemoryStore.recall`` choke-point. Borrowed in shape
from BiltIQ Agent OS; adapted to Sentinel's two-value ``DataBoundary``.
"""

from __future__ import annotations

from sentinel.memory.delta import compute_delta
from sentinel.memory.extraction import boundary_counts, extract_entries, finding_texts
from sentinel.memory.schema import (
    DataBoundary,
    EntitySummary,
    MemoryDelta,
    MemoryEntry,
    MemoryType,
    RunRecord,
    normalize_entity,
)
from sentinel.memory.store import MemoryStore, RunStore, data_dir, db_path

__all__ = [
    "MemoryStore",
    "RunStore",
    "MemoryEntry",
    "RunRecord",
    "MemoryDelta",
    "EntitySummary",
    "MemoryType",
    "DataBoundary",
    "compute_delta",
    "extract_entries",
    "finding_texts",
    "boundary_counts",
    "normalize_entity",
    "data_dir",
    "db_path",
]
