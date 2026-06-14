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
        "<form method='post' action='/projects'>"
        "<div class='grid cols-2'>"
        "<div class='field'><label for='p-name'>Name</label>"
        "<input class='input' id='p-name' name='name' placeholder='e.g. BiltIQ market-capture' required></div>"
        "<div class='field'><label for='p-website'>Website <span class='hint'>optional</span></label>"
        "<input class='input' id='p-website' name='website' placeholder='https://biltiq.ai'></div>"
        "</div>"
        "<div class='field'><label for='p-client'>Target / client website <span class='hint'>optional</span></label>"
        "<input class='input' id='p-client' name='client_url' placeholder='https://assam.gov.in'></div>"
        "<div class='field'><label for='p-ctx'>Context &amp; use case <span class='hint'>optional</span></label>"
        "<textarea id='p-ctx' name='context' rows='3' "
        "placeholder='e.g. This is my website biltiq.ai and this is the Assam govt website — "
        "understand their major works and issues (flood, border security, agriculture), then map "
        "our services to an AI-based solution for better governance.'></textarea></div>"
        "<div class='field'><label for='p-obj'>First research objective <span class='hint'>optional</span></label>"
        "<input class='input' id='p-obj' name='objective' "
        "placeholder='e.g. Profile us and compare against a competitor'></div>"
        "<div class='row-between'>"
        "<span class='hint'>A project groups research tasks. Add an objective to jump straight into "
        "planning your first task; leave it blank to set up the workspace and add tasks later.</span>"
        f"<button class='btn' type='submit'>{_icon('bolt')} Create project</button></div>"
        "</form>"
    )


def _project_form() -> str:
    """Creation form wrapped in a titled card — used for the empty/first-run state."""
    return (
        "<div class='card' id='new'><div class='card-head'><h2>New project</h2></div>"
        f"{_project_form_fields()}</div>"
    )


def projects_page(*, projects: list, backend: str, ok: str = "") -> str:
    banner = f"<div class='card pad-sm ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    intro = ("<div class='grow'><h1>Projects</h1>"
             "<p>Each project scopes its own knowledge base, tasks, and memory.</p></div>")
    if not projects:
        # Empty state: the page-head carries the jump-to-form CTA since the form sits right below.
        head = f"<div class='page-head'>{intro}<a class='btn' href='#new'>{_icon('bolt')} Create</a></div>"
        empty = ("<div class='card' style='margin-top:16px'><div class='empty'>"
                 f"<div class='ico'>{_icon('folder')}</div>No projects yet. "
                 "Create one above — a project groups the tasks and results of a research program.</div></div>")
        return shell(active="projects", title="Projects", content=banner + head + _project_form() + empty,
                     backend=backend)
    # List-first: no head CTA — the collapsed <details> below carries the "New project" affordance,
    # which keeps that label after the project list (the list is what the operator came for).
    head = f"<div class='page-head'>{intro}</div>"
    cards = ""
    for p in projects:
        site = (f"<div class='muted' style='font-size:12.5px;margin:4px 0 14px'>"
                f"{escape(p.website)}</div>") if p.website else (
                "<div class='muted' style='font-size:12.5px;margin:4px 0 14px'>—</div>")
        cards += (
            f"<a class='card' href='/projects/{escape(p.id)}' style='display:block'>"
            f"<div class='row-between'><b style='font-size:15px'>{escape(p.name)}</b>"
            f"<span class='badge neutral'>{escape(p.settings.autonomy)}</span></div>"
            f"{site}"
            f"<div class='inline'><span class='pill mono'>{escape(p.created_at)}</span></div></a>"
        )
    header = (
        "<div class='card-head' style='margin-top:0'>"
        f"<h2>Your projects</h2><span class='pill'>{len(projects)}</span></div>"
    )
    grid = f"<div class='grid cols-3' style='margin-bottom:24px'>{cards}</div>"
    # List-first: existing projects are what the user came for. The creation form is tucked into a
    # collapsible so it stays one click away without pushing the list below the fold.
    create = (
        "<details class='card' id='new' style='margin-top:18px'>"
        "<summary style='cursor:pointer;font-weight:600;list-style:none'>"
        f"{_icon('bolt')} New project</summary>"
        f"<div style='margin-top:14px'>{_project_form_fields()}</div></details>"
    )
    return shell(active="projects", title="Projects", content=banner + head + header + grid + create,
                 backend=backend)
