"""render.artifacts — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape
from sentinel.artifacts.schemas import AccountBrief, Battlecard, Boundary, Finding, Gap, Source

from .accounts import _run_href
from .base import _CHARTJS, _badge, _icon, _project_subnav, shell
from .plan import _artifact_html

def _source(s: Source) -> str:
    if s.url:
        return (f"<span class='src'>· <a href='{escape(s.url)}' rel='noopener' "
                f"target='_blank'>{escape(s.label)}</a></span>")
    return f"<span class='src'>· {escape(s.label)}</span>"


def _run_sources(sources: list[Source]) -> str:
    """Persisted provenance for one timeline row (SENTINEL-008). A legacy row (pre-008, no
    captured sources) shows a neutral dash — never an empty cell that reads as "0 sources"."""
    if not sources:
        return "<span class='muted'>—</span>"
    return "".join(_source(s) for s in sources)


def _findings(title: str, items: list[Finding]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li>{_badge(f.source.boundary)}{escape(f.text)}{_source(f.source)}</li>" for f in items
    )
    return f"<h2 class='sec'>{escape(title)}</h2><ul class='find'>{rows}</ul>"


def _plain(title: str, items: list[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{escape(x)}</li>" for x in items)
    return f"<h2 class='sec'>{escape(title)}</h2><ul class='plain'>{rows}</ul>"


_PRIORITY_RANK = {"high": 0, "med": 1, "low": 2}


def _strategy_block(artifact) -> str:
    """Strategy overlay sections for the dashboard (SENTINEL-009). Empty when nothing populated."""
    out = ""
    if getattr(artifact, "assessment", None):
        out += f"<h2 class='sec'>Strategic assessment</h2><p>{escape(artifact.assessment)}</p>"
    actions = getattr(artifact, "action_plan", None) or []
    if actions:
        rows = "".join(
            f"<tr><td><span class='badge neutral'>{escape(a.priority)}</span></td>"
            f"<td>{escape(a.action)}</td><td>{escape(a.timeline)}</td>"
            f"<td>{escape(a.rationale)}</td></tr>"
            for a in sorted(actions, key=lambda x: _PRIORITY_RANK.get(x.priority, 9))
        )
        out += (
            "<h2 class='sec'>Action plan</h2>"
            "<div class='table-wrap'><table class='table'><thead><tr>"
            "<th>Priority</th><th>Action</th><th>Timeline</th><th>Rationale</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>"
        )
    objections = getattr(artifact, "objection_handling", None) or []
    if objections:
        rows = "".join(
            f"<li><b>{escape(o.objection)}</b> → {escape(o.reframe)}</li>" for o in objections
        )
        out += f"<h2 class='sec'>Objection handling</h2><ul class='plain'>{rows}</ul>"
    return out


def _gaps(items: list[Gap]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li>{_badge(g.boundary)}<span class='gap'>{escape(g.what_was_missing)}</span> "
        f"<span class='src'>— {escape(g.impact)}</span></li>" for g in items
    )
    return f"<h2 class='sec'>Gaps (sources unavailable)</h2><ul class='find'>{rows}</ul>"


def provenance_counts(artifact) -> tuple[int, int]:
    """(public, private) finding counts for an artifact — drives the per-artifact donut."""
    pub = priv = 0
    if isinstance(artifact, Battlecard):
        for f in (artifact.strengths + artifact.weaknesses + artifact.pricing_signals
                  + artifact.recent_developments):
            pub += f.source.boundary is Boundary.PUBLIC
            priv += f.source.boundary is Boundary.PRIVATE
    elif isinstance(artifact, AccountBrief):
        pub = len(artifact.public_signal)
        priv = len(artifact.private_signal)
    return pub, priv


def _aside(artifact, backend: str, reference: str) -> str:
    pub, priv = provenance_counts(artifact)
    data = json.dumps({"pub": pub, "priv": priv})
    js = (
        "<script src='" + _CHARTJS + "'></script><script>"
        "var d=__DATA__,_C=getComputedStyle(document.documentElement),"
        "MUT=(_C.getPropertyValue('--muted')||'#8b97a8').trim(),"
        "PANEL=(_C.getPropertyValue('--panel')||'#0e1420').trim();"
        "new Chart(document.getElementById('cArt'),{type:'doughnut',"
        "data:{labels:['Public','Private'],datasets:[{data:[d.pub,d.priv],"
        "backgroundColor:['#4ea1ff','#ffb24d'],borderColor:PANEL,borderWidth:2}]},"
        "options:{cutout:'62%',plugins:{legend:{position:'bottom',labels:{color:MUT,"
        "boxWidth:12,font:{size:11}}}}}});</script>"
    ).replace("__DATA__", data)
    card = (
        "<div class='card'><h3 class='ch'>Signal provenance</h3>"
        "<div class='chart-wrap' style='height:180px'><canvas id='cArt'></canvas></div>"
        "<div style='margin-top:14px;display:flex;flex-direction:column;gap:8px'>"
        f"<span class='pill'><span class='dotmark {'v' if backend=='vllm' else 'g'}'></span>"
        f"Backend: <b>{escape(backend)}</b></span>"
        f"<span class='pill'>Saved: <b>{escape(reference)}</b></span></div></div>"
    )
    return card, js


def _trace(trace: list[str]) -> str:
    if not trace:
        return ""
    return ("<details style='margin-top:18px'><summary>Run trace (observability)</summary>"
            f"<div class='trace'>{escape(chr(10).join(trace))}</div></details>")


def _delta_block(delta) -> str:
    """"Since last run" card (SENTINEL-002, AC-8). Empty string when there's no delta."""
    if delta is None:
        return ""
    chips = ""
    if getattr(delta, "added", None):
        chips += f"<span class='badge public'>+{len(delta.added)} new</span> "
    if getattr(delta, "removed", None):
        chips += f"<span class='badge private'>-{len(delta.removed)} dropped</span>"
    items = "".join(f"<li>{escape(t)}</li>" for t in (delta.added or [])[:6])
    new_list = f"<ul class='since-list' style='margin:10px 0 0;padding-left:18px'>{items}</ul>" if items else ""
    return (
        "<div class='card' style='margin-bottom:18px'>"
        "<h3 class='ch'>Since last run</h3>"
        f"<div class='summary'>{escape(delta.summary)}</div>"
        f"<div style='margin-top:8px'>{chips}</div>{new_list}</div>"
    )


def render_battlecard(
    b: Battlecard, *, backend: str, reference: str, trace: list[str], delta=None
) -> str:
    vert = (f"<span class='pill'>Vertical: <b>{escape(b.vertical_context)}</b></span>"
            if b.vertical_context else "")
    aside, js = _aside(b, backend, reference)
    main = (
        f"<div class='card'><div class='card-head'>"
        f"<h2 style='font-size:24px'>Battlecard — {escape(b.target)}</h2>{vert}</div>"
        f"<div class='summary'>{escape(b.one_line_summary)}</div>"
        f"<h2 class='sec'>Positioning</h2><p>{escape(b.positioning)}</p>"
        + _findings("Strengths", b.strengths)
        + _findings("Weaknesses", b.weaknesses)
        + _findings("Pricing signals", b.pricing_signals)
        + _findings("Recent developments", b.recent_developments)
        + _plain("How to win against them", b.how_to_win)
        + _strategy_block(b)
        + _gaps(b.gaps) + _trace(trace) + "</div>"
    )
    content = f"{_delta_block(delta)}<div class='split'>{main}{aside}</div>"
    return shell(active="artifacts", title=f"Battlecard — {b.target}", content=content,
                 backend=backend, body_scripts=js)


def render_account_brief(
    a: AccountBrief, *, backend: str, reference: str, trace: list[str], delta=None
) -> str:
    vert = (f"<span class='pill'>Vertical: <b>{escape(a.vertical_context)}</b></span>"
            if a.vertical_context else "")
    aside, js = _aside(a, backend, reference)
    main = (
        f"<div class='card'><div class='card-head'>"
        f"<h2 style='font-size:24px'>Account Brief — {escape(a.account)}</h2>{vert}</div>"
        f"<div class='summary'>{escape(a.one_line_summary)}</div>"
        + _findings("Public signal", a.public_signal)
        + _findings("Private signal", a.private_signal)
        + _plain("Merged insights (public ⊕ private)", a.merged_insights)
        + _plain("Recommended actions", a.recommended_actions)
        + _strategy_block(a)
        + _gaps(a.gaps) + _trace(trace) + "</div>"
    )
    content = f"{_delta_block(delta)}<div class='split'>{main}{aside}</div>"
    return shell(active="artifacts", title=f"Account Brief — {a.account}", content=content,
                 backend=backend, body_scripts=js)


def render_artifact(artifact, *, backend: str, reference: str, trace: list[str], delta=None) -> str:
    if isinstance(artifact, Battlecard):
        return render_battlecard(
            artifact, backend=backend, reference=reference, trace=trace, delta=delta
        )
    if isinstance(artifact, AccountBrief):
        return render_account_brief(
            artifact, backend=backend, reference=reference, trace=trace, delta=delta
        )
    # SENTINEL-014 domain artifacts (SoftwareBrief, FinancialProfile, AcademicBrief,
    # NutritionBrief, TravelBrief) use the shared _artifact_html card renderer.
    art_dict = artifact.model_dump() if hasattr(artifact, "model_dump") else dict(artifact)
    content = _artifact_html(type(artifact).__name__, art_dict)
    return shell(active="artifacts", title=type(artifact).__name__, content=content, backend=backend)


# --------------------------------------------------------------------------- #
# Artifacts list
# --------------------------------------------------------------------------- #
def artifacts_page(*, artifacts: list[dict], backend: str, project: str = "sovereign",
                   project_id: str = "") -> str:
    """Artifact list — scoped to a project when project_id is provided (shows project subnav)."""
    subnav = _project_subnav(project_id, "artifacts", project) if project_id else ""
    active = "projects" if project_id else "artifacts"
    title = "Artifacts" if not project_id else f"{project} · Artifacts"

    if not artifacts:
        run_link = (f"<a href='/projects/{escape(project_id)}/tasks' style='color:var(--accent-text)'>"
                    "create a research task</a>") if project_id else (
                        "<a href='/projects' style='color:var(--accent-text)'>start a project</a>")
        content = (
            "<div class='card'><div class='empty'>"
            f"<div class='ico'>{_icon('doc')}</div>"
            f"No artifacts yet. {run_link} to generate a battlecard or account brief."
            "</div></div>"
        )
        return shell(active=active, title=title, content=content, backend=backend,
                     project=project, subnav=subnav)

    rows = ""
    for a in artifacts:
        name = escape(a["target"])
        if a.get("project_id") or a.get("entity"):
            name = (f"<a href='{_run_href(a)}' "
                    f"style='color:var(--accent-text)'>{name}</a>")
        # "Add to KB" button — available in project context whenever the run has any content
        kb_btn = ""
        if project_id and a.get("run_id"):
            rid = escape(a["run_id"])
            pid_esc = escape(project_id)
            kb_btn = (
                f"<form method='POST' action='/projects/{pid_esc}/kb/sources/artifact' "
                f"style='display:inline'>"
                f"<input type='hidden' name='run_id' value='{rid}'>"
                f"<button type='submit' class='btn sm ghost' "
                f"title='Index this artifact into the project Knowledge Base'>"
                f"{_icon('database')} Add to KB</button></form>"
            )
        rows += (
            f"<tr><td><b>{name}</b></td><td>{escape(a['kind'])}</td>"
            f"<td><span class='badge public'>{a['public']}</span> "
            f"<span class='badge private'>{a['private']}</span></td>"
            f"<td><span class='dotmark {'v' if a['backend']=='vllm' else 'g'}'></span> "
            f"<span class='mono'>{escape(a['backend'])}</span></td>"
            f"<td class='mono faint'>{escape(a['reference'])}</td>"
            f"<td class='muted'>{escape(a['when'])}</td>"
            f"<td>{kb_btn}</td></tr>"
        )
    content = (
        "<div class='card'>"
        f"<div class='card-head'><h2>All artifacts</h2>"
        f"<span class='pill'>{len(artifacts)} output{'s' if len(artifacts) != 1 else ''}</span></div>"
        "<div class='table-wrap'><table class='table'><thead><tr>"
        "<th>Target</th><th>Kind</th><th>Public / Private</th><th>Backend</th>"
        "<th>Saved to</th><th>When</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></div>"
    )
    return shell(active=active, title=title, content=content, backend=backend,
                 project=project, subnav=subnav)
