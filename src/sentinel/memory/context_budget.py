"""Context window budget allocator (SENTINEL-016 G-11).

Splits a total token budget across the memory injection slots so no single
source crowds out the others. Default proportions are tuned for a 2400-token
block that sits inside a ~4000-token instruction suffix.

Usage in run_dag::

    budget = ContextBudget(total=2400)
    hot = mem.recall(target, ..., token_budget=budget.slot("entity_hot"))
    cold = mem.recall(target, ..., token_budget=budget.slot("entity_cold"))
    ...

If ``total`` is None (memory config has no explicit limit), each slot falls
back to its default cap so behaviour is backward-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_PROPORTIONS: dict[str, float] = {
    "kb": 0.30,
    "entity_hot": 0.30,
    "entity_cold": 0.15,
    "episodic": 0.25,
}

_DEFAULTS: dict[str, int] = {
    "kb": 800,
    "entity_hot": 800,
    "entity_cold": 400,
    "episodic": 600,
}


@dataclass
class ContextBudget:
    """Per-slot token budget derived from a single total cap.

    Slots are defined in ``_PROPORTIONS``. Unknown slot names fall back to 200
    tokens (fail-soft) so new callers never raise.
    """

    total: int | None = None
    _slots: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.total is not None:
            self._slots = {
                name: max(1, int(self.total * frac))
                for name, frac in _PROPORTIONS.items()
            }
        else:
            self._slots = dict(_DEFAULTS)

    def slot(self, name: str) -> int:
        """Return the token budget for the named slot.

        Falls back to 200 for unknown slot names so new callers never raise.
        """
        return self._slots.get(name, 200)
