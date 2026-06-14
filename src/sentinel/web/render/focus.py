"""render.focus — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from urllib.parse import quote
from sentinel.artifacts.schemas import Boundary

from .accounts import _account_href
from .base import _badge, shell

# --------------------------------------------------------------------------- #
# Focus list (SENTINEL-010) — deterministic, cited account prioritization.
# A row's score/tier/reasons all come from compute_account_priority; this layer only escapes and
# lays out. A reason carrying a private boundary is rendered with the private badge so an operator
# can see at a glance which signal it came from (the engine already drops private reasons from a
# public-only score, so nothing leaks here — AC-10).
# --------------------------------------------------------------------------- #
_TIER_STYLE = {
    "hot": "color:#ff8a8a;background:rgba(255,80,80,.12);border:1px solid #7f3030",
    "warm": "color:var(--private);background:var(--private-bg);border:1px solid #5a4413",
    "cold": "color:var(--muted);background:var(--panel);border:1px solid var(--line)",
}


def _tier_badge(tier: str) -> str:
    style = _TIER_STYLE.get(tier, _TIER_STYLE["cold"])
    return (f"<span class='badge' style='{style};text-transform:uppercase;"
            f"letter-spacing:.05em'>{escape(tier)}</span>")


def _reason_html(r) -> str:
    """One cited reason: text + optional source link + a private badge when private-sourced."""
    badge = _badge(r.boundary) if r.boundary == Boundary.PRIVATE else ""
    src = ""
    if getattr(r, "source_url", None):
        src = (f" <span class='src'>· <a href='{escape(r.source_url)}' rel='noopener' "
               f"target='_blank'>{escape(r.source_label or 'source')}</a></span>")
    elif getattr(r, "source_label", ""):
        src = f" <span class='src'>· {escape(r.source_label)}</span>"
    return f"<li>{badge}{escape(r.text)}{src}</li>"


def _breakdown_html(breakdown: dict, notes: list) -> str:
    """Auditable per-signal detail in a collapsed <details> — the deterministic receipt (AC-11)."""
    rows = "".join(
        f"<tr><td class='mono'>{escape(name)}</td>"
        f"<td class='mono'>{raw:.2f}</td>"
        f"<td><div style='height:6px;border-radius:4px;background:var(--accent);"
        f"width:{max(2, min(100, int(raw * 100)))}%'></div></td></tr>"
        for name, raw in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    )
    note = (f"<p class='note' style='margin:6px 0 0'>{escape('; '.join(notes))}</p>" if notes else "")
    return (
        "<details style='margin-top:6px'><summary class='src' style='cursor:pointer'>"
        "Signal breakdown</summary>"
        "<table style='margin-top:6px'><thead><tr><th>Signal</th><th>Raw</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table>{note}</details>"
    )


def _entity_href(entity: str, project_by_entity: dict | None) -> str:
    """Focus rows are entity-keyed (PriorityScore has no project_id), but the operator wants to
    land on the entity's PROJECT — the account page is a thin memory view (user feedback
    2026-06-12). The caller passes a {entity: project_id} map resolved from run records;
    entities with no project (legacy runs) keep the account link."""
    pid = (project_by_entity or {}).get(entity)
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return _account_href(entity)


def _focus_row(rank: int, s, project_by_entity: dict | None = None) -> str:
    reasons = "".join(_reason_html(r) for r in s.reasons[:3]) or "<li class='src'>—</li>"
    return (
        f"<tr><td class='mono'>{rank}</td>"
        f"<td><a href='{_entity_href(s.entity, project_by_entity)}' style='color:var(--accent-2)'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td>"
        f"<td><ul class='find' style='margin:0'>{reasons}</ul>"
        f"{_breakdown_html(s.breakdown, s.notes)}</td></tr>"
    )


def focus_page(*, scores: list, backend: str, enabled: bool = True, project: str = "sovereign",
               project_by_entity: dict | None = None) -> str:
    """Ranked focus list — highest priority first, each row cited and auditable (AC-9)."""
    if not enabled:
        content = ("<div class='card'><div class='empty'>The focus list is turned off. "
                   "Enable <b>Prioritization</b> in "
                   "<a href='/settings' style='color:var(--accent-2)'>Settings</a> to rank "
                   "accounts by who needs attention now.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    if not scores:
        content = ("<div class='card'><div class='empty'>No accounts to prioritize yet. "
                   "<a href='/projects' style='color:var(--accent-2)'>Run a task</a> and the focus "
                   "list ranks every researched account here, with cited reasons.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    rows = "".join(_focus_row(i, s, project_by_entity) for i, s in enumerate(scores, start=1))
    content = (
        "<p class='note'>Who needs attention now — ranked by a deterministic, cited score (no "
        "LLM in the arithmetic). Each reason links to the finding behind it; the breakdown shows "
        "every signal. Tune the weights in "
        "<a href='/settings' style='color:var(--accent-2)'>Settings</a>.</p>"
        "<div class='card' style='padding:6px 8px;margin-top:16px'><table><thead><tr>"
        "<th>#</th><th>Account</th><th>Score</th><th>Tier</th><th>Why now</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)


def focus_card(scores: list, project_by_entity: dict | None = None) -> str:
    """Compact 'Top 5 to focus on' card for the dashboard (OQ-2). Empty string when no scores."""
    top = [s for s in scores if s.tier != "cold"][:5] or scores[:5]
    if not top:
        return ""
    rows = "".join(
        f"<tr><td><a href='{_entity_href(s.entity, project_by_entity)}' style='color:var(--accent-2)'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td></tr>"
        for s in top
    )
    return (
        "<div class='section-h' style='margin-top:16px'><h2>Top to focus on</h2>"
        "<a class='btn ghost' href='/focus'>Open focus list</a></div>"
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>Account</th><th>Score</th><th>Tier</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
