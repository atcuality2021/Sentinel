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
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad' style='margin-bottom:16px'>{escape(err)}</div>"

    def _row(r) -> str:
        ts = str(r.created_at or "")[:16]
        n_findings = len(getattr(r, "finding_texts", []) or [])
        run_id = escape(str(r.id))
        return (
            f"<tr>"
            f"<td><a href='/accounts/{escape(r.entity)}' style='color:var(--accent-2)'>"
            f"{escape(r.entity)}</a></td>"
            f"<td><span class='pill' style='font-size:11.5px'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td style='text-align:right'>{n_findings}</td>"
            f"<td class='mono'>{ts}</td>"
            f"<td><form method='post' "
            f"action='/projects/{pid}/memory/{run_id}/delete' "
            f"onsubmit=\"return confirm('Remove this run from episodic memory?')\">"
            f"<button type='submit' class='btn' "
            f"style='background:var(--bad);padding:4px 10px;font-size:12px'>Delete</button>"
            f"</form></td>"
            f"</tr>"
        )

    _sem_live = len(semantic_facts) > 0
    _sem_desc = (
        f"Entity facts extracted and accumulated across runs ({len(semantic_facts)} facts)"
        if _sem_live else "Entity facts extracted and accumulated across runs"
    )
    memory_types = (
        "<div class='grid cards3' style='margin-bottom:24px'>"
        + "".join(
            f"<div class='gc'><div class='gc-ico'>{_icon(ico)}</div>"
            f"<div class='gc-t'>{name}</div><div class='gc-d'>{desc}</div>"
            f"<div class='gc-tags'><span class='tag pv {'live' if live else 'dark'}' "
            f"style='{'opacity:.5' if not live else ''}'>"
            f"{'live' if live else 'phase 2'}</span></div></div>"
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
        table = (
            "<div class='card' style='padding:6px 8px;overflow:auto'>"
            "<table><thead><tr>"
            "<th>Entity</th><th>Mode</th><th>Backend</th>"
            "<th style='text-align:right'>Findings</th><th>When</th><th></th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        header_line = (
            f"<p class='note' style='margin-bottom:12px'>{len(records)} run record(s) in this project. "
            "Deleting removes the record from episodic recall; accumulated entity facts are unaffected.</p>"
        )
    else:
        table = "<div class='card'><div class='empty'>No run records for this project yet. " \
                "Complete a research task to populate episodic memory.</div></div>"
        header_line = ""

    # Semantic facts section
    if semantic_facts:
        def _fact_row(f) -> str:
            ts = str(f.created_at or "")[:10]
            return (
                f"<tr>"
                f"<td style='font-weight:500'>{escape(f.entity)}</td>"
                f"<td>{escape(f.content)}</td>"
                f"<td><span class='pill' style='font-size:11px'>{escape(f.source_label)}</span></td>"
                f"<td class='mono' style='color:var(--fg-2);font-size:12px'>{ts}</td>"
                f"</tr>"
            )
        sem_rows = "".join(_fact_row(f) for f in semantic_facts)
        sem_section = (
            "<div class='section-h' style='margin-top:24px'><h2>Semantic Memory</h2></div>"
            f"<p class='note' style='margin-bottom:12px'>{len(semantic_facts)} entity fact(s) "
            "extracted from completed research tasks.</p>"
            "<div class='card' style='padding:6px 8px;overflow:auto'>"
            "<table><thead><tr>"
            "<th>Entity</th><th>Fact</th><th>Source</th><th>Date</th>"
            "</tr></thead>"
            f"<tbody>{sem_rows}</tbody></table></div>"
        )
    else:
        sem_section = ""

    content = (banner + memory_types
               + "<div class='section-h'><h2>Episodic Memory</h2></div>"
               + header_line + table + sem_section)
    return shell(
        active="projects", title=f"{project.name} · Memory", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "memory", project.name),
    )
