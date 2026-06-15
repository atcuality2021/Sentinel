"""render.accounts — split from render.py (presentation only)."""

from __future__ import annotations
from urllib.parse import quote


def _run_href(run: dict) -> str:
    """Where a run row should take the operator. Prefer the run's PROJECT — that's where the
    tasks, artifacts and KB live. Falls back to /projects for legacy/unscoped runs that have
    no project_id (accounts page removed 2026-06-15)."""
    pid = run.get("project_id")
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return "/projects"


def _fmt_when(dt) -> str:
    # tz-aware UTC in storage; show the operator local wall-clock.
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")
