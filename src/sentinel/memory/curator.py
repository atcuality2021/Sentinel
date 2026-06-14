"""SENTINEL-021 — product-memory curator entry point.

The write path (:meth:`MemoryStore.write`) already auto-resolves *new* contradictions at write time,
so live recall never serves two opposing findings. This module is the **cadence** hook: a small,
invokable entry point that clears the residual conflict backlog (rows from pre-021 databases or
write-time races), guarded by the same golden-question rollback as the write path.

Run it from cron, an operator shell, or a maintenance skill::

    python -m sentinel.memory.curator        # reconcile the default DB

It is deliberately *not* called on every run: write-time resolution keeps the live set clean, so the
backlog sweep only needs to run on a low-frequency cadence.
"""

from __future__ import annotations

import sys

from sentinel.memory.store import MemoryStore


def run_curator(store: MemoryStore | None = None) -> dict:
    """Run one reconciliation pass over the open-conflict backlog.

    Returns ``{"resolved": int, "rolled_back": int, "flagged": int}``. Delegates to
    :meth:`MemoryStore.reconcile_open_conflicts`, which is fail-soft and never raises.
    """
    store = store or MemoryStore()
    return store.reconcile_open_conflicts()


def main(argv: list[str] | None = None) -> int:
    result = run_curator()
    print(
        "memory curator · "
        f"resolved={result['resolved']} "
        f"rolled_back={result['rolled_back']} "
        f"flagged={result['flagged']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
