"""render.focus — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from urllib.parse import quote
from sentinel.artifacts.schemas import Boundary

from .base import _badge, _icon, shell

# --------------------------------------------------------------------------- #
# Focus list (SENTINEL-010) — deterministic, cited account prioritization.
# A row's score/tier/reasons all come from compute_account_priority; this layer only escapes and
# lays out. A reason carrying a private boundary is rendered with the private badge so an operator
# can see at a glance which signal it came from (the engine already drops private reasons from a
# public-only score, so nothing leaks here — AC-10).
# --------------------------------------------------------------------------- #
# Maps a priority tier to a semantic .badge variant in the new design system.
_TIER_STYLE = {
    "hot": "bad",
    "warm": "warn",
    "cold": "neutral",
}


def _tier_badge(tier: str) -> str:
    cls = _TIER_STYLE.get(tier, "neutral")
    return (f"<span class='badge {cls}' style='text-transform:uppercase;"
            f"letter-spacing:.05em'>{escape(tier)}</span>")


def _reason_html(r) -> str:
    """One cited reason: text + optional source link + a private badge when private-sourced."""
    badge = _badge(r.boundary) if r.boundary == Boundary.PRIVATE else ""
    src = ""
    if getattr(r, "source_url", None):
        src = (f" <span class='muted'>· <a href='{escape(r.source_url)}' rel='noopener' "
               f"target='_blank'>{escape(r.source_label or 'source')}</a></span>")
    elif getattr(r, "source_label", ""):
        src = f" <span class='muted'>· {escape(r.source_label)}</span>"
    return f"<li>{badge}{escape(r.text)}{src}</li>"


def _breakdown_html(breakdown: dict, notes: list) -> str:
    """Auditable per-signal detail in a collapsed <details> — the deterministic receipt (AC-11)."""
    rows = "".join(
        f"<tr><td class='mono'>{escape(name)}</td>"
        f"<td class='num mono'>{raw:.2f}</td>"
        f"<td><div style='height:6px;border-radius:4px;background:var(--accent);"
        f"width:{max(2, min(100, int(raw * 100)))}%'></div></td></tr>"
        for name, raw in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    )
    note = (f"<p class='muted' style='margin:6px 0 0'>{escape('; '.join(notes))}</p>" if notes else "")
    return (
        "<details style='margin-top:6px'><summary class='muted' style='cursor:pointer'>"
        "Signal breakdown</summary>"
        "<div class='table-wrap'><table class='table' style='margin-top:6px'><thead><tr>"
        "<th>Signal</th><th>Raw</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>{note}</details>"
    )


def _entity_href(entity: str, project_by_entity: dict | None) -> str:
    """Focus rows are entity-keyed (PriorityScore has no project_id), but the operator wants to
    land on the entity's PROJECT — the account page is a thin memory view (user feedback
    2026-06-12). The caller passes a {entity: project_id} map resolved from run records;
    entities with no project (legacy runs) keep the account link."""
    pid = (project_by_entity or {}).get(entity)
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return "/projects"


def _focus_row(rank: int, s, project_by_entity: dict | None = None) -> str:
    href = _entity_href(s.entity, project_by_entity)
    reasons = "".join(_reason_html(r) for r in s.reasons[:3]) or "<li class='muted'>—</li>"
    return (
        f"<tr><td class='num mono'>{rank}</td>"
        f"<td><a href='{href}'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='num mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td>"
        f"<td><ul class='find' style='margin:0'>{reasons}</ul>"
        f"{_breakdown_html(s.breakdown, s.notes)}</td>"
        f"<td><a class='btn sm ghost' href='{href}'>Open</a></td></tr>"
    )


def focus_page(*, scores: list, backend: str, enabled: bool = True, project: str = "sovereign",
               project_by_entity: dict | None = None) -> str:
    """Ranked focus list — highest priority first, each row cited and auditable (AC-9)."""
    head = (
        "<div class='page-head'><div class='grow'><h1>Focus list</h1>"
        "<p>Entities ranked by priority score with cited reasons.</p></div>"
        "<span class='pill'>scope: all projects</span></div>"
    )
    if not enabled:
        content = (head + "<div class='card'><div class='empty'>"
                   f"<div class='ico'>{_icon('target')}</div>The focus list is turned off. "
                   "Enable <b>Prioritization</b> in "
                   "<a href='/settings'>Settings</a> to rank "
                   "accounts by who needs attention now.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    if not scores:
        content = (head + "<div class='card'><div class='empty'>"
                   f"<div class='ico'>{_icon('target')}</div>No accounts to prioritize yet. "
                   "<a href='/projects'>Run a task</a> and the focus "
                   "list ranks every researched account here, with cited reasons.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    rows = "".join(_focus_row(i, s, project_by_entity) for i, s in enumerate(scores, start=1))
    content = (
        head
        + "<p class='muted'>Who needs attention now — ranked by a deterministic, cited score (no "
        "LLM in the arithmetic). Each reason links to the finding behind it; the breakdown shows "
        "every signal. Tune the weights in "
        "<a href='/settings'>Settings</a>.</p>"
        "<div class='card'><div class='card-head'><h2>Ranked accounts</h2>"
        "<span class='pill'><span class='dot' style='color:var(--accent)'></span>"
        "deterministic</span></div>"
        "<div class='table-wrap'><table class='table'><thead><tr>"
        "<th>#</th><th>Account</th><th>Score</th><th>Tier</th><th>Why now</th><th></th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)


def focus_card(scores: list, project_by_entity: dict | None = None) -> str:
    """Compact 'Top 5 to focus on' card for the dashboard (OQ-2). Empty string when no scores."""
    top = [s for s in scores if s.tier != "cold"][:5] or scores[:5]
    if not top:
        return ""
    rows = "".join(
        f"<tr><td><a href='{_entity_href(s.entity, project_by_entity)}'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='num mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td></tr>"
        for s in top
    )
    return (
        "<div class='card' style='margin-top:16px'>"
        "<div class='card-head'><h2>Top to focus on</h2>"
        "<a class='btn ghost' href='/focus'>Open focus list</a></div>"
        "<div class='table-wrap'><table class='table'><thead><tr>"
        "<th>Account</th><th>Score</th><th>Tier</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
