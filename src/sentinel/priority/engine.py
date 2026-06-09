"""Deterministic account-priority engine (SENTINEL-010).

``compute_account_priority(entity, *, allowed_boundaries, now, config)`` is the one scoring entry
point. It builds a :class:`PriorityContext` from the data SENTINEL-002/004 already hold
(``RunStore`` runs + boundary-filtered ``MemoryStore.recall``), runs every signal in the single
``REGISTRY``, and returns a :class:`PriorityScore` with a per-signal ``breakdown`` and cited
``reasons``.

**No LLM, no network** (NFR-1): the score is pure arithmetic and the reasons are templated from the
cited data, never generated. The boundary invariant (AC-10/NFR-3) is *inherited* — signals only see
``ctx.memory``, which came from the ``MemoryStore.recall`` choke-point — not re-implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from sentinel.memory import DataBoundary, MemoryEntry, MemoryStore, RunRecord, RunStore
from sentinel.memory.schema import normalize_entity, utcnow
from sentinel.priority import signals as _signals  # the ONE registry + primitives

Tier = Literal["hot", "warm", "cold"]

_ALL_BOUNDARIES: frozenset[DataBoundary] = frozenset({DataBoundary.PUBLIC, DataBoundary.PRIVATE})


# --------------------------------------------------------------------------- #
# Context handed to every signal
# --------------------------------------------------------------------------- #
@dataclass
class PriorityContext:
    """Everything a signal may read. ``memory`` is **already boundary-filtered** (the guarantee)."""

    entity: str
    runs: list[RunRecord]              # newest-first (RunStore.runs_for ordering)
    memory: list[MemoryEntry]          # boundary-filtered via MemoryStore.recall
    allowed_boundaries: frozenset[DataBoundary]
    now: datetime
    half_life_days: float = 14.0       # recency half-life (cfg.priority.recency_half_life_days)
    # Signals append user-facing reasons here as a side channel; the engine collects + ranks them.
    reasons: list["Reason"] = field(default_factory=list)

    def add_reason(
        self,
        text: str,
        signal: str,
        *,
        source_label: str = "",
        source_url: str | None = None,
        boundary: DataBoundary = DataBoundary.PUBLIC,
    ) -> None:
        """Append a cited reason. Lets signals (in signals.py) emit reasons without importing
        the ``Reason`` model from this module — keeps the registry module cycle-free."""
        self.reasons.append(
            Reason(
                text=text,
                signal=signal,
                source_label=source_label,
                source_url=source_url,
                boundary=boundary,
            )
        )


class Reason(BaseModel):
    """One cited, human-readable justification behind a signal's contribution (AC-9)."""

    text: str
    signal: str
    source_label: str = ""
    source_url: str | None = None
    boundary: DataBoundary = DataBoundary.PUBLIC


class PriorityScore(BaseModel):
    """The deterministic, auditable output of one compute (AC-1)."""

    entity: str
    display_name: str = ""
    score: float                       # 0-100
    tier: Tier
    breakdown: dict[str, float] = Field(default_factory=dict)   # signal name → raw [0,1]
    reasons: list[Reason] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)              # e.g. "signal X unavailable"
    computed_at: datetime = Field(default_factory=utcnow)


def _tier_for(score: float, hot: float, warm: float) -> Tier:
    if score >= hot:
        return "hot"
    if score >= warm:
        return "warm"
    return "cold"


def compute_account_priority(
    entity: str,
    *,
    allowed_boundaries=_ALL_BOUNDARIES,
    now: datetime | None = None,
    config=None,
    runs: list[RunRecord] | None = None,
    memory: list[MemoryEntry] | None = None,
) -> PriorityScore:
    """Score one entity deterministically. Identical inputs ⇒ identical score (AC-2).

    ``runs``/``memory`` may be injected (tests, batch reuse); otherwise they are read from
    ``RunStore``/``MemoryStore``. ``allowed_boundaries`` is the SENTINEL-002 gate: a ``{PUBLIC}``
    call cannot surface a private-sourced reason (AC-10). No LLM, no network in this path.
    """
    from sentinel.config import load_config  # lazy → avoids import cycle at module load

    cfg = config or load_config()
    pcfg = cfg.priority
    now = now or utcnow()
    allowed = frozenset(DataBoundary(b) for b in allowed_boundaries)
    key = normalize_entity(entity)

    if runs is None:
        runs = RunStore().runs_for(key)
    if memory is None:
        # The choke-point: boundary filtering happens HERE, once. reinforce_on_read=False keeps
        # scoring side-effect-free (auditable, repeatable) — a view must not mutate memory strength.
        memory = MemoryStore().recall(
            key, allowed, limit=200, token_budget=10**9, now=now, reinforce_on_read=False
        )

    display = runs[0].target if runs else entity
    ctx = PriorityContext(
        entity=key,
        runs=runs,
        memory=memory,
        allowed_boundaries=allowed,
        now=now,
        half_life_days=pcfg.recency_half_life_days,
    )

    # Effective weights: registry defaults overlaid by cfg.priority.weights (admin tuning, NFR-5).
    registry = _signals.REGISTRY
    effective: dict[str, float] = {
        name: pcfg.weights.get(name, sig.weight) for name, sig in registry.items()
    }
    total = sum(w for w in effective.values() if w > 0)

    breakdown: dict[str, float] = {}
    notes: list[str] = []
    weighted = 0.0
    for name, sig in registry.items():
        try:
            raw = sig.fn(ctx)
        except Exception as exc:  # isolation (AC-4): one bad signal never sinks the score
            raw = sig.default
            notes.append(f"signal '{name}' unavailable ({type(exc).__name__})")
        raw = min(1.0, max(0.0, raw))  # signals promise [0,1]; enforce it defensively
        breakdown[name] = raw
        w = effective.get(name, 0.0)
        if total > 0 and w > 0:
            weighted += raw * (w / total)

    score = min(100.0, max(0.0, weighted * 100.0))   # clamp (AC-5); empty registry ⇒ 0
    tier = _tier_for(score, pcfg.hot_threshold, pcfg.warm_threshold)

    # Only the top-contributing signals produce user-facing reasons (keeps a row readable). Reasons
    # were appended to ctx.reasons by the signal fns; rank them by the signal's weighted contribution.
    contribution = {
        name: breakdown.get(name, 0.0) * (effective.get(name, 0.0) / total if total else 0.0)
        for name in registry
    }
    ranked = sorted(
        ctx.reasons, key=lambda r: contribution.get(r.signal, 0.0), reverse=True
    )

    return PriorityScore(
        entity=key,
        display_name=display,
        score=round(score, 2),
        tier=tier,
        breakdown=breakdown,
        reasons=ranked,
        notes=notes,
        computed_at=now,
    )
