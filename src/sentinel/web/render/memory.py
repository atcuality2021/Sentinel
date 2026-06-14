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
            f"<td><a href='/accounts/{escape(r.entity)}'>{escape(r.entity)}</a></td>"
            f"<td><span class='pill'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td class='num'>{n_findings}</td>"
            f"<td class='mono'>{ts}</td>"
            f"<td><form method='post' "
            f"action='/projects/{pid}/memory/{run_id}/delete' "
            f"onsubmit=\"return confirm('Remove this run from episodic memory?')\">"
            f"<button type='submit' class='btn sm danger'>Delete</button>"
            f"</form></td>"
            f"</tr>"
        )

    _sem_live = len(semantic_facts) > 0
    _sem_desc = (
        f"Entity facts extracted and accumulated across runs ({len(semantic_facts)} facts)"
        if _sem_live else "Entity facts extracted and accumulated across runs"
    )
    memory_types = (
        "<div class='grid cols-3' style='margin-bottom:24px'>"
        + "".join(
            f"<div class='card'><div class='card-head'>"
            f"<h2>{name}</h2>"
            f"<span class='badge {'ok' if live else 'neutral'}'>{'live' if live else 'phase 2'}</span>"
            f"</div>"
            f"<p class='note' style='margin:0;display:flex;align-items:center;gap:10px'>"
            f"<span style='color:var(--muted)'>{_icon(ico)}</span><span>{desc}</span></p></div>"
            for name, ico, desc, live in [
                ("Episodic", "spark", "Run records — every research task this project has run", True),
                ("Semantic", "brain", _sem_desc, _sem_live),
                ("Procedural", "cog", "Learned skills and workflow patterns for this domain", False),
            ]
        )
        + "</div>"
    )

    if records:
        rows_html = "".join(_row(r) for r in records)
        header_pill = f"<span class='pill'>{len(records)} record(s)</span>"
        table = (
            "<div class='card'>"
            f"<div class='card-head'><h2>Episodic Memory</h2>{header_pill}</div>"
            "<p class='note' style='margin:0 0 14px'>"
            "Deleting removes the record from episodic recall; accumulated entity facts are unaffected.</p>"
            "<div class='table-wrap'><table class='table'><thead><tr>"
            "<th>Entity</th><th>Mode</th><th>Backend</th>"
            "<th class='num'>Findings</th><th>When</th><th></th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div></div>"
        )
    else:
        table = (
            "<div class='card'>"
            "<div class='card-head'><h2>Episodic Memory</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('brain')}</div>"
            "No run records for this project yet. "
            "Complete a research task to populate episodic memory.</div></div>"
        )

    # Semantic facts section
    if semantic_facts:
        def _fact_row(f) -> str:
            ts = str(f.created_at or "")[:10]
            return (
                f"<tr>"
                f"<td style='font-weight:500'>{escape(f.entity)}</td>"
                f"<td>{escape(f.content)}</td>"
                f"<td><span class='pill'>{escape(f.source_label)}</span></td>"
                f"<td class='mono'>{ts}</td>"
                f"</tr>"
            )
        sem_rows = "".join(_fact_row(f) for f in semantic_facts)
        sem_section = (
            "<div class='card' style='margin-top:16px'>"
            "<div class='card-head'><h2>Semantic Memory</h2>"
            "<span class='pill'>live heads</span></div>"
            f"<p class='note' style='margin:0 0 14px'>{len(semantic_facts)} entity fact(s) "
            "extracted from completed research tasks.</p>"
            "<div class='table-wrap'><table class='table'><thead><tr>"
            "<th>Entity</th><th>Fact</th><th>Source</th><th>Date</th>"
            "</tr></thead>"
            f"<tbody>{sem_rows}</tbody></table></div></div>"
        )
    else:
        sem_section = ""

    content = banner + memory_types + table + sem_section
    return shell(
        active="projects", title=f"{project.name} · Memory", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "memory", project.name),
    )
