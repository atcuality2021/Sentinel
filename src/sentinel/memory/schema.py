"""Memory data models (SENTINEL-002).

The boundary type is the *same* enum the tool layer and artifacts use — re-exported here as
``DataBoundary`` — so a finding's ``source.boundary`` is, unchanged, the memory entry's boundary.
That single shared type is what lets the sovereignty guarantee extend from the tools into storage
without a translation layer that could mis-tag private data as public.

Models are storage-shaped (flat, JSON/SQLite-friendly). SM-2 reinforcement state lives on the
entry itself; the pure kernel that evolves it is in ``strength.py``.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

# One boundary type across tool layer, artifacts, and memory (the whole point).
from sentinel.artifacts.schemas import Boundary as DataBoundary
from sentinel.artifacts.schemas import Source

__all__ = [
    "DataBoundary",
    "MemoryType",
    "MemoryEntry",
    "RunRecord",
    "MemoryDelta",
    "EntitySummary",
    "UserProfile",
    "SessionHandoff",
    "content_hash",
    "normalize_entity",
    "utcnow",
]

_WS = re.compile(r"\s+")


def utcnow() -> datetime:
    """Timezone-aware UTC now — the single clock for all memory timestamps."""
    return datetime.now(timezone.utc)


def normalize_entity(name: str) -> str:
    """Case-insensitive, whitespace-collapsed entity key (OQ-2: exact-match identity for v1)."""
    return _WS.sub(" ", name.strip().lower())


def content_hash(text: str) -> str:
    """Stable hash of normalized text — the dedup key (AC-7)."""
    norm = _WS.sub(" ", text.strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


class MemoryType(str, Enum):
    FINDING = "finding"
    PREFERENCE = "preference"
    DECISION = "decision"
    OBSERVATION = "observation"
    SEMANTIC_FACT = "semantic_fact"


class EntityRelation(BaseModel):
    """One directed edge in the entity knowledge graph (SENTINEL-016 G-06).

    ``from_entity → rel_type → to_entity`` e.g. "biltiq ai → competitor → crayon".
    Boundary mirrors the MemoryEntry contract: PUBLIC edges may reach any agent;
    PRIVATE edges are filtered the same way recall() filters memory entries.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    from_entity: str
    rel_type: str
    to_entity: str
    boundary: DataBoundary = DataBoundary.PUBLIC
    context: str = ""
    project_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _normalise(self) -> "EntityRelation":
        self.from_entity = normalize_entity(self.from_entity)
        self.to_entity = normalize_entity(self.to_entity)
        return self


class MemoryEntry(BaseModel):
    """One boundary-tagged fact about an entity, with SM-2 reinforcement state (AC-2)."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    entity: str
    boundary: DataBoundary
    memory_type: MemoryType = MemoryType.FINDING
    content: str
    source_label: str = ""
    source_url: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    content_hash: str = ""
    # SM-2 / Leitner state (see strength.py)
    strength: float = 1.0
    interval_days: float = 1.0
    ease: float = 2.5
    last_reinforced_at: datetime = Field(default_factory=utcnow)
    access_count: int = 0
    quarantined: bool = False
    # SENTINEL-021: when this entry loses a conflict it is quarantined and this points at the
    # winning entry's id (audit trail + wake-up path). None for live/legacy entries.
    superseded_by: str | None = None
    # Best-effort project provenance (SENTINEL-012 / ADR-0003). NOT a scoping key: memory is
    # entity-keyed and deliberately cross-project, so `recall` never filters by it. Records the
    # first writer of a deduped fact; None for legacy/unscoped entries.
    project_id: str | None = None

    @model_validator(mode="after")
    def _derive(self) -> "MemoryEntry":
        # Normalize the key and backfill the dedup hash. Idempotent on reload from the DB.
        self.entity = normalize_entity(self.entity)
        if not self.content_hash:
            self.content_hash = content_hash(self.content)
        return self


class RunRecord(BaseModel):
    """Episodic record of one completed run — feeds the dashboard and the delta (AC-1, AC-8)."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    entity: str
    target: str
    mode: str
    backend: str
    kind: str = ""
    public: int = 0
    private: int = 0
    gaps: int = 0
    reference: str = ""
    finding_texts: list[str] = Field(default_factory=list)
    # Run versioning / provenance (SENTINEL-008): the run's cited sources + a 1-based per-entity
    # sequence. Default empty/0 so old rows (pre-008) read back cleanly (AC-8).
    sources: list[Source] = Field(default_factory=list)
    run_seq: int = 0
    # Project scoping key (SENTINEL-012 / ADR-0003). Runs are episodic, so this is a real filter
    # key (the dashboard reads scope by it). None for legacy/unscoped runs.
    project_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _norm(self) -> "RunRecord":
        self.entity = normalize_entity(self.entity)
        return self


class MemoryDelta(BaseModel):
    """"Since last run" diff between this run and the prior run for the same entity (AC-8)."""

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    summary: str = ""
    prior_run_at: datetime | None = None


class UserProfile(BaseModel):
    """Operator preference profile (SENTINEL-016 G-14).

    Evolves from explicit ratings and implicit corrections; injected into the
    synthesizer instruction as a "## User preferences" block so output framing
    adapts over time without prompt engineering.
    """

    user_id: str
    verbosity: int = Field(default=3, ge=1, le=5,
                           description="1=very concise, 5=very detailed")
    citation_density: int = Field(default=3, ge=1, le=5,
                                  description="1=minimal citations, 5=cite every claim")
    domain_level: str = Field(default="analyst",
                              description="executive | analyst | expert")
    preferred_format: str = Field(default="bullets",
                                  description="bullets | prose | table")
    updated_at: datetime = Field(default_factory=utcnow)


class SessionHandoff(BaseModel):
    """A2A cross-session coordination envelope — SENTINEL-016 G-17.

    Agent A posts a handoff describing work it cannot complete in the current
    session. Agent B in a future session reads pending() → claims() the handoff
    → executes → completes(). Status lifecycle: pending → claimed → done.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    entity: str
    intent: str = Field(description="What should be done (e.g. 'run full profile')")
    mode: str = Field(default="full", description="Research mode to execute")
    priority: int = Field(default=5, ge=1, le=10, description="1=low, 10=urgent")
    reason: str = Field(default="", description="Why this handoff was created")
    status: str = Field(default="pending", description="pending | claimed | done")
    project_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    claimed_at: datetime | None = None
    done_at: datetime | None = None

    @model_validator(mode="after")
    def _norm(self) -> "SessionHandoff":
        self.entity = normalize_entity(self.entity)
        return self


class EntitySummary(BaseModel):
    """One row of the Accounts index (SENTINEL-004) — a RunStore-derived read-model.

    Aggregates every run against one normalized ``entity`` key: how many, when last, and the
    cumulative public/private provenance split. No memory dependency — the index answers "what
    have we researched and how often", independent of what the agent currently remembers.
    """

    entity: str            # normalized key (whitespace-collapsed, lowercased)
    display_name: str      # most-recent RunRecord.target (the original-cased string)
    runs: int
    last_run_at: datetime
    public: int            # cumulative across runs (AC-6: equals the per-run sum)
    private: int
    modes: list[str] = Field(default_factory=list)   # distinct modes seen
    kinds: list[str] = Field(default_factory=list)    # distinct artifact kinds

    @classmethod
    def from_runs(cls, entity: str, runs: list["RunRecord"]) -> "EntitySummary":
        """Aggregate one entity's runs (newest-first, non-empty) into a summary. Shared by the
        index (``RunStore.entities``) and the detail route so the counts can never drift."""
        return cls(
            entity=normalize_entity(entity),
            display_name=runs[0].target,
            runs=len(runs),
            last_run_at=runs[0].created_at,
            public=sum(r.public for r in runs),
            private=sum(r.private for r in runs),
            modes=sorted({r.mode for r in runs if r.mode}),
            kinds=sorted({r.kind for r in runs if r.kind}),
        )
