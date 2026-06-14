"""render.projects — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import _icon, shell

# --------------------------------------------------------------------------- #
# Projects (SENTINEL-012) — the top-level organising construct. Step 6 ships the
# shell: create a project, list projects, open one to a task/results placeholder.
# --------------------------------------------------------------------------- #
def _project_form_fields() -> str:
    """The bare create-project form (no card chrome) so it can sit in a card (empty state) or a
    collapsible <details> (list-first state) without duplicating markup."""
    return (
        "<form class='run' method='post' action='/projects'>"
        "<div><label class='lbl' for='p-name'>Name</label>"
        "<input id='p-name' name='name' placeholder='e.g. BiltIQ market-capture' required></div>"
        "<div><label class='lbl' for='p-website'>Website (optional)</label>"
        "<input id='p-website' name='website' placeholder='https://biltiq.ai'></div>"
        "<div><label class='lbl' for='p-client'>Target / client website (optional)</label>"
        "<input id='p-client' name='client_url' placeholder='https://assam.gov.in'></div>"
        "<div style='grid-column:1/-1'><label class='lbl' for='p-ctx'>Context &amp; use case (optional)</label>"
        "<textarea id='p-ctx' name='context' rows='3' "
        "placeholder='e.g. This is my website biltiq.ai and this is the Assam govt website — "
        "understand their major works and issues (flood, border security, agriculture), then map "
        "our services to an AI-based solution for better governance.'></textarea></div>"
        "<div><label class='lbl' for='p-obj'>First research objective (optional)</label>"
        "<input id='p-obj' name='objective' "
        "placeholder='e.g. Profile us and compare against a competitor'></div>"
        f"<div><button class='btn' type='submit'>{_icon('bolt')} Create project</button></div>"
        "</form>"
        "<div class='note' style='margin-top:8px'>A project is a workspace that groups research tasks. "
        "Add an objective to jump straight into planning your first task; leave it blank to set up the "
        "workspace and add tasks later.</div>"
    )


def _project_form() -> str:
    """Creation form wrapped in a titled card — used for the empty/first-run state."""
    return (
        "<div class='card'><div class='section-h' style='margin-top:0'><h2>New project</h2></div>"
        f"{_project_form_fields()}</div>"
    )


def projects_page(*, projects: list, backend: str, ok: str = "") -> str:
    banner = f"<div class='card banner ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    if not projects:
        empty = ("<div class='card' style='margin-top:16px'><div class='empty'>No projects yet. "
                 "Create one above — a project groups the tasks and results of a research program.</div></div>")
        return shell(active="projects", title="Projects", content=banner + _project_form() + empty,
                     backend=backend)
    rows = ""
    for p in projects:
        site = (f"<a href='{escape(p.website)}' rel='noopener' target='_blank' "
                f"style='color:var(--accent-2)'>{escape(p.website)}</a>") if p.website else "—"
        rows += (
            f"<tr><td><a href='/projects/{escape(p.id)}' style='color:var(--accent-2)'>"
            f"<b>{escape(p.name)}</b></a></td>"
            f"<td>{site}</td>"
            f"<td><span class='badge'>{escape(p.settings.autonomy)}</span></td>"
            f"<td class='mono'>{escape(p.created_at)}</td></tr>"
        )
    header = (
        "<div class='section-h' style='margin-top:0'>"
        f"<h2>Your projects <span class='pill' style='margin-left:8px'>{len(projects)}</span></h2></div>"
    )
    table = (
        "<div class='card' style='padding:6px 8px;margin-top:4px'><table><thead><tr>"
        "<th>Project</th><th>Website</th><th>Autonomy</th><th>Created</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    # List-first: existing projects are what the user came for. The creation form is tucked into a
    # collapsible so it stays one click away without pushing the list below the fold.
    create = (
        "<details class='card' style='margin-top:18px'>"
        "<summary style='cursor:pointer;font-weight:600;color:var(--accent-2);list-style:none'>"
        f"{_icon('bolt')} New project</summary>"
        f"<div style='margin-top:14px'>{_project_form_fields()}</div></details>"
    )
    return shell(active="projects", title="Projects", content=banner + header + table + create,
                 backend=backend)
