"""render.accounts — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from urllib.parse import quote

from .base import _icon, shell

# --------------------------------------------------------------------------- #
# Accounts (SENTINEL-004) — entity index + detail (run timeline + memory)
# --------------------------------------------------------------------------- #
def _account_href(entity: str) -> str:
    """Link to an account by its normalized key. ``safe=''`` encodes spaces/slashes so a key
    like ``acme corp`` round-trips through the path param (AC-10)."""
    return f"/accounts/{quote(entity, safe='')}"


def _run_href(run: dict) -> str:
    """Where a run row should take the operator. Prefer the run's PROJECT — that's where the
    tasks, artifacts and KB live. The account page is an entity-keyed CRM memory view and a
    confusing landing target from the dashboard (user feedback 2026-06-12); it stays only as
    the fallback for legacy/unscoped runs that have no project_id."""
    pid = run.get("project_id")
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return _account_href(run.get("entity", ""))


def _fmt_when(dt) -> str:
    # tz-aware UTC in storage; show the operator local wall-clock.
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def accounts_page(*, accounts: list, backend: str, ok: str = "", project: str = "sovereign") -> str:
    """The Accounts index — one row per distinct entity (AC-1, AC-2)."""
    banner = f"<div class='card pad-sm ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    head = (
        "<div class='page-head'><div class='grow'><h1>Accounts</h1>"
        "<p>Every researched entity, with provenance split and run history.</p></div>"
        "<span class='pill'>scope: all projects</span></div>"
    )
    if not accounts:
        content = (banner + head + "<div class='card'><div class='empty'>"
                   f"<div class='ico'>{_icon('users')}</div>No accounts yet. "
                   "<a href='/projects'>Run a task</a> against a "
                   "competitor or client and it appears here, with its full history.</div></div>")
        return shell(active="accounts", title="Accounts", content=content, backend=backend,
                 project=project)
    rows = ""
    for s in accounts:
        modes = ", ".join(escape(m) for m in s.modes) or "—"
        prov = f"<span class='badge public'>{s.public}</span>"
        if s.private:
            prov += f" <span class='badge private'>{s.private}</span>"
        rows += (
            f"<tr><td><a href='{_account_href(s.entity)}'>"
            f"<b>{escape(s.display_name)}</b></a></td>"
            f"<td class='num mono'>{s.runs}</td>"
            f"<td>{prov}</td>"
            f"<td class='muted'>{modes}</td>"
            f"<td class='muted mono'>{escape(_fmt_when(s.last_run_at))}</td>"
            f"<td><a class='btn sm ghost' href='{_account_href(s.entity)}'>Open</a></td></tr>"
        )
    content = (
        banner + head
        + "<div class='card'><div class='card-head'><h2>Entities</h2></div>"
        "<p class='muted' style='margin-top:0'>Every entity researched, collapsed to one row. Open one "
        "to see its run timeline and accumulated memory — public and private signal kept separate.</p>"
        "<div class='table-wrap'><table class='table'><thead><tr>"
        "<th>Entity</th><th>Runs</th><th>Public / Private</th><th>Modes</th>"
        "<th>Last run</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return shell(active="accounts", title="Accounts", content=content, backend=backend,
                 project=project)
