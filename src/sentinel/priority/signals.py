"""Signal registry + scoring primitives (SENTINEL-010).

This module is the **single source of truth** for account-priority signals (AC-6). There is exactly
one ``REGISTRY``, one ``register_signal`` entry point, and one set of reusable primitives
(``normalize``, ``half_life_decay``). LeadFlow shipped three overlapping scorers; we keep one.

A *signal* is a tiny pure function ``fn(ctx) -> float`` returning a raw score in ``[0, 1]``. The
engine (``engine.py``) normalizes the registered weights to sum to 1.0, isolates per-signal failures
(a raising ``fn`` contributes its declared ``default``), and clamps the weighted sum to ``[0, 100]``.

No LLM, no network — pure arithmetic over the data SENTINEL-002/004 already persist (NFR-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # avoids a cycle: engine imports REGISTRY from here; signals only duck-type ctx.
    from sentinel.priority.engine import PriorityContext

# A signal reads the (already boundary-filtered) context and returns a raw score in [0, 1].
SignalFn = Callable[["PriorityContext"], float]


@dataclass(frozen=True)
class _Signal:
    name: str
    weight: float          # default weight; cfg.priority.weights[name] overlays this at compute time
    fn: SignalFn
    default: float = 0.0    # contributed when fn raises (AC-4)


# The ONE registry (AC-6). Module-level, populated at import by register_signal calls below.
REGISTRY: dict[str, _Signal] = {}


def register_signal(name: str, weight: float, fn: SignalFn, *, default: float = 0.0) -> None:
    """Register (or replace) a signal. The engine normalizes weights, so absolute scale is free."""
    REGISTRY[name] = _Signal(name=name, weight=weight, fn=fn, default=default)


# --------------------------------------------------------------------------- #
# Reusable primitives (AC-7)
# --------------------------------------------------------------------------- #
def normalize(value: float, low: float, high: float, invert: bool = False) -> float:
    """Map ``value`` from ``[low, high]`` onto ``[0, 1]``, clamped. ``invert`` flips the result.

    A degenerate range (``high == low``) maps to 0.0 — no information, neutral contribution.
    """
    if high == low:
        return 0.0
    x = (value - low) / (high - low)
    x = min(1.0, max(0.0, x))
    return 1.0 - x if invert else x


def half_life_decay(age_days: float, half_life: float) -> float:
    """Exponential half-life decay: ``1.0`` at age 0, ``0.5`` at one half-life, → 0 as age grows.

    Used by recency-style signals: a freshly-touched account scores ~1, a long-stale one ~0. A
    non-positive ``half_life`` is meaningless ⇒ 0.0 (treat as fully decayed rather than raise).
    """
    if half_life <= 0:
        return 0.0
    if age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life)


# --------------------------------------------------------------------------- #
# Seed signals (AC-8) — all over data SENTINEL-002/004 already hold. Each is a small pure fn that
# reads ctx, returns a raw score in [0,1], and (when it fires) appends a cited reason via
# ctx.add_reason. A sparse/empty input returns the neutral default rather than raising — belt-and-
# suspenders with the engine's per-signal isolation. ``private_engagement`` is the only boundary-
# gated one: it counts only PRIVATE entries in ctx.memory, which is empty under a {PUBLIC} call.
# --------------------------------------------------------------------------- #
from sentinel.artifacts.schemas import Boundary as _Boundary  # noqa: E402  (kept near use)


def _age_days(ctx: "PriorityContext", when) -> float:
    return (ctx.now - when).total_seconds() / 86400.0


def _recency(ctx: "PriorityContext") -> float:
    """How recently we ran research on this account. Stale accounts surface for a refresh."""
    if not ctx.runs:
        return 0.0
    age = _age_days(ctx, ctx.runs[0].created_at)
    score = half_life_decay(age, ctx.half_life_days)
    days = int(round(age))
    when = "today" if days <= 0 else f"{days} day{'s' if days != 1 else ''} ago"
    ctx.add_reason(f"Last researched {when}", "recency")
    return score


def _new_material(ctx: "PriorityContext") -> float:
    """Findings the latest run surfaced that prior runs had not — fresh intel worth acting on."""
    if not ctx.runs:
        return 0.0
    latest = ctx.runs[0].finding_texts
    prior = {f for r in ctx.runs[1:] for f in r.finding_texts}
    fresh = [f for f in latest if f not in prior]
    if not fresh:
        return 0.0
    ctx.add_reason(
        f"{len(fresh)} new finding{'s' if len(fresh) != 1 else ''} in the latest run", "new_material"
    )
    return normalize(len(fresh), 0, 8)


def _volume(ctx: "PriorityContext") -> float:
    """Cumulative research depth — total findings gathered across all runs for this account."""
    total = sum(len(r.finding_texts) for r in ctx.runs)
    if total <= 0:
        return 0.0
    ctx.add_reason(
        f"{total} finding{'s' if total != 1 else ''} across {len(ctx.runs)} run"
        f"{'s' if len(ctx.runs) != 1 else ''}",
        "volume",
    )
    return normalize(total, 0, 20)


def _private_engagement(ctx: "PriorityContext") -> float:
    """Depth of PRIVATE (MCP-sourced) signal. Boundary-gated: zero under a public-only call (AC-10).

    Reads only ``ctx.memory``, which the engine already filtered through ``MemoryStore.recall`` —
    so a ``{PUBLIC}`` context carries no PRIVATE entries and this contributes 0 with no leak.
    """
    private = [m for m in ctx.memory if m.boundary == _Boundary.PRIVATE]
    if not private:
        return 0.0
    ctx.add_reason(
        f"{len(private)} private touchpoint{'s' if len(private) != 1 else ''} recorded",
        "private_engagement",
        boundary=_Boundary.PRIVATE,
    )
    return normalize(len(private), 0, 10)


def _competitor_move(ctx: "PriorityContext") -> float:
    """Recency of the freshest logged finding — a proxy for recent competitor/market movement.

    Distinct from ``recency`` (which times the *run*): this times the freshest *memory entry*, so a
    newly-recorded development scores high even between full runs.
    """
    if not ctx.memory:
        return 0.0
    freshest = max(ctx.memory, key=lambda m: m.created_at)
    age = _age_days(ctx, freshest.created_at)
    score = half_life_decay(age, ctx.half_life_days)
    if score <= 0:
        return 0.0
    ctx.add_reason(
        "Recent development logged",
        "competitor_move",
        source_label=freshest.source_label,
        source_url=freshest.source_url,
        boundary=freshest.boundary,
    )
    return score


# Register the seed set once, at import. Weights are relative (the engine normalizes to 1.0); they
# encode the pilot's default priority shape and are overridable via cfg.priority.weights (NFR-5).
register_signal("recency", 0.30, _recency)
register_signal("new_material", 0.25, _new_material)
register_signal("volume", 0.15, _volume)
register_signal("private_engagement", 0.20, _private_engagement)
register_signal("competitor_move", 0.10, _competitor_move)
