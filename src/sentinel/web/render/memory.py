"""render.memory — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import _icon, _project_subnav, shell

def project_memory_page(*, project, records: list, backend: str,
                        ok: str = "", err: str = "",
                        semantic_facts: list = None) -> str:
    """Memory tab — episodic run records scoped to this project."""
    semantic_facts = semantic_facts or []
    pid = escape(project.id)
    banner = ""
    if ok:
        banner = f"<div class='card pad-sm' style='margin-bottom:16px;color:var(--ok)'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card pad-sm' style='margin-bottom:16px;color:var(--bad)'>{escape(err)}</div>"

    def _row(r) -> str:
        ts = str(r.created_at or "")[:16]
        n_findings = len(getattr(r, "finding_texts", []) or [])
        run_id = escape(str(r.id))
        return (
            f"<tr>"
            f"<td><a href='/accounts/{escape(r.entity)}'><b>{escape(r.entity)}</b></a></td>"
            f"<td><span class='pill'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td class='num'>{n_findings}</td>"
            f"<td class='muted mono'>{ts}</td>"
            f"<td><form method='post' "
            f"action='/projects/{pid}/memory/{run_id}/delete' "
            f"onsubmit=\"return confirm('Remove this run from episodic memory?')\">"
            f"<button type='submit' class='btn sm danger'>Delete</button>"
            f"</form></td>"
            f"</tr>"
        )

    # ── Episodic runs card (left, 2fr) — every research run scoped to project ──
    if records:
        rows_html = "".join(_row(r) for r in records)
        header_pill = f"<span class='pill'>{len(records)} record(s)</span>"
        episodic_card = (
            "<div class='card'>"
            f"<div class='card-head'><h2>Episodic runs</h2>{header_pill}</div>"
            "<div class='table-wrap'><table class='table'><thead><tr>"
            "<th>Target</th><th>Mode</th><th>Provenance</th>"
            "<th class='num'>Findings</th><th>When</th><th></th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
            "<p class='note' style='margin:14px 0 0'>"
            "Deleting removes the record from episodic recall; "
            "accumulated entity facts are unaffected.</p></div>"
        )
    else:
        episodic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Episodic runs</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('spark')}</div>"
            "No run records for this project yet. "
            "Complete a research task to populate episodic memory.</div></div>"
        )

    # ── Semantic facts card (right, 1fr) — live heads as a scannable stack ──
    if semantic_facts:
        def _fact_inline(f) -> str:
            label = escape(f.source_label) if getattr(f, "source_label", "") else ""
            src = f" <span class='muted' style='font-size:11.5px'>· {label}</span>" if label else ""
            return (
                "<div class='inline'>"
                "<span class='badge ok'>live</span>"
                "<span style='font-size:13px'>"
                f"<b>{escape(f.entity)}</b> — {escape(f.content)}{src}</span>"
                "</div>"
            )
        sem_rows = "<div class='divider'></div>".join(
            _fact_inline(f) for f in semantic_facts
        )
        semantic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Semantic facts</h2>"
            "<span class='pill'>live heads</span></div>"
            f"<div class='stack'>{sem_rows}</div></div>"
        )
    else:
        semantic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Semantic facts</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('brain')}</div>"
            "No entity facts accumulated yet.</div></div>"
        )

    content = (
        banner
        + "<div class='split' style='align-items:start'>"
        + episodic_card + semantic_card
        + "</div>"
    )
    return shell(
        active="projects", title=f"{project.name} · Memory", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "memory", project.name),
    )
