"""SM-2 / Leitner reinforcement kernel (SENTINEL-002) — pure, no I/O.

Borrowed shape from BiltIQ Agent OS ``memory/strength.py``. Two ideas:

* **Decay** — an entry's usefulness fades along a forgetting curve unless it keeps getting recalled.
  ``decayed_strength`` is what recall ranks by, so stale memory naturally sinks below the floor.
* **Reinforcement** — recalling (or re-observing) an entry strengthens it with diminishing returns
  toward a ceiling and lengthens its retention interval (the testing effect). NEUTRAL is a no-op.

Keeping this side-effect-free makes the boundary/recall logic in ``store.py`` easy to reason about
and the behaviour trivial to unit-test with an injected ``now``.
"""

from __future__ import annotations

import math
from enum import Enum

from sentinel.memory.schema import MemoryEntry, utcnow

STRENGTH_FLOOR = 0.05   # recall drops anything decayed below this
STRENGTH_CEIL = 2.0     # reinforcement asymptotes here, never exceeds
HOT_THRESHOLD = 1.2     # G-08: entries >= this are "hot" (reinforced >= 2x)
_GAIN = 0.4             # fraction of the remaining headroom gained per positive reinforcement
_EASE_CEIL = 3.0


class ReinforceSignal(str, Enum):
    POSITIVE = "positive"   # the entry was useful / re-observed
    NEUTRAL = "neutral"     # no signal — leave it untouched


def decayed_strength(entry: MemoryEntry, now=None) -> float:
    """Current effective strength after exponential decay since last reinforcement.

    ``retention = strength * e^(-elapsed_days / interval_days)``. A longer interval (a
    well-reinforced entry) decays more slowly. At ``elapsed == 0`` this is just ``strength``.
    """
    now = now or utcnow()
    elapsed_days = (now - entry.last_reinforced_at).total_seconds() / 86400.0
    if elapsed_days <= 0:
        return entry.strength
    stability = max(entry.interval_days, 0.1)
    return entry.strength * math.exp(-elapsed_days / stability)


def reinforce(
    entry: MemoryEntry, signal: ReinforceSignal = ReinforceSignal.POSITIVE, *, now=None
) -> MemoryEntry:
    """Strengthen an entry in place (diminishing returns to the ceiling). NEUTRAL is identity."""
    if signal == ReinforceSignal.NEUTRAL:
        return entry
    now = now or utcnow()
    entry.strength = entry.strength + (STRENGTH_CEIL - entry.strength) * _GAIN
    entry.interval_days = entry.interval_days * entry.ease
    entry.ease = min(entry.ease + 0.1, _EASE_CEIL)
    entry.last_reinforced_at = now
    entry.access_count += 1
    return entry
