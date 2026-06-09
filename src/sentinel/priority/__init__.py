"""Deterministic account prioritization (SENTINEL-010).

A pure-Python scoring layer over the data SENTINEL-002/004 already persist — no LLM, no network.
One registry of signals (``register_signal`` into ``REGISTRY``), one engine
(``compute_account_priority``), one persisted snapshot (``PriorityStore``). The boundary invariant
is inherited from the ``MemoryStore.recall`` choke-point: signals only ever see boundary-filtered
memory, so a public-only score can carry no private-sourced reason.
"""

from __future__ import annotations

from sentinel.priority.engine import (
    PriorityContext,
    PriorityScore,
    Reason,
    compute_account_priority,
)
from sentinel.priority.signals import (
    REGISTRY,
    half_life_decay,
    normalize,
    register_signal,
)
from sentinel.priority.store import PriorityStore

__all__ = [
    "compute_account_priority",
    "PriorityScore",
    "PriorityContext",
    "Reason",
    "register_signal",
    "REGISTRY",
    "normalize",
    "half_life_decay",
    "PriorityStore",
]
