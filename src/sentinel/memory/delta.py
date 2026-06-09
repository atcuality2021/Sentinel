""""Since last run" delta (SENTINEL-002, AC-8).

A normalized set-diff of finding texts between the new run and the most recent prior run for the
same entity. Uses ``content_hash`` so trivial whitespace/case changes don't show up as churn.
``prior is None`` ⇒ first run. Granularity is deliberately simple for v1 (added/removed findings +
one-line summary); sentiment/score trends are a later increment (OQ-1).
"""

from __future__ import annotations

from sentinel.memory.schema import MemoryDelta, RunRecord, content_hash, utcnow


def _by_hash(texts: list[str]) -> dict[str, str]:
    return {content_hash(t): t for t in texts}


def compute_delta(prior: RunRecord | None, current_texts: list[str]) -> MemoryDelta:
    current = _by_hash(current_texts)
    if prior is None:
        return MemoryDelta(
            added=list(current.values()),
            removed=[],
            summary=f"First run for this entity — {len(current)} findings recorded.",
            prior_run_at=None,
        )
    previous = _by_hash(prior.finding_texts)
    added = [t for h, t in current.items() if h not in previous]
    removed = [t for h, t in previous.items() if h not in current]
    days = max((utcnow() - prior.created_at).days, 0)
    when = "today" if days == 0 else f"{days} day{'s' if days != 1 else ''} ago"
    if not added and not removed:
        summary = f"Since last run ({when}): no change in findings."
    else:
        summary = (
            f"Since last run ({when}): +{len(added)} new, -{len(removed)} dropped findings."
        )
    return MemoryDelta(
        added=added, removed=removed, summary=summary, prior_run_at=prior.created_at
    )
