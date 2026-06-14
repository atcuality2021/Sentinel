"""UX / mobile-friendliness regression tests.

Pins the responsive-shell contract added after the 2026-06-12 mobile audit: on a phone the
fixed 248px sidebar used to eat 64% of the screen. The fix turns the sidebar into an off-canvas
drawer (CSS) driven by a topbar hamburger + scrim (markup + JS), adds a phone breakpoint, and
makes /projects list-first. These assert the load-bearing hooks survive future edits.
"""
from __future__ import annotations

from types import SimpleNamespace

from sentinel.web.render import CSS, projects_page, shell


def _shell() -> str:
    return shell(active="home", title="Dashboard", content="<p>hi</p>", backend="gemini")


# ── off-canvas drawer: markup + JS hooks ──────────────────────────────────────

def test_shell_renders_mobile_hamburger_and_scrim():
    html = _shell()
    assert "id='mobileNavToggle'" in html      # topbar hamburger (hidden on desktop via CSS)
    assert "icon-btn mobile-only" in html       # redesign: hamburger is an icon-btn shown only on mobile
    assert "id='navScrim'" in html             # backdrop tap-to-close target
    assert "class='scrim'" in html


def test_shell_wires_mobile_nav_js():
    html = _shell()
    # the drawer toggles `.mobile-open` on the shell and the scrim/links close it
    assert "mobile-open" in html
    assert "mobileNavToggle" in html
    assert "navScrim" in html


# ── responsive CSS contract ───────────────────────────────────────────────────

def test_css_has_mobile_drawer_breakpoint():
    assert "@media(max-width:768px)" in CSS
    # the sidebar leaves the grid flow and slides in/out
    assert "transform:translateX(-100%)" in CSS
    assert ".shell.mobile-open .sidebar{transform:translateX(0)" in CSS
    # the grid collapses to a single column on a phone
    assert ".shell,.shell.collapsed{grid-template-columns:1fr}" in CSS


def test_css_has_phone_breakpoint():
    assert "@media(max-width:480px)" in CSS


def test_css_makes_tables_scroll_on_mobile():
    # wide tables scroll instead of crushing columns
    assert ".content table{display:block;overflow-x:auto" in CSS


# ── /projects list-first ──────────────────────────────────────────────────────

def _fake_project(name: str):
    return SimpleNamespace(
        id="a" * 32, name=name, website="https://example.com",
        settings=SimpleNamespace(autonomy="suggest"), created_at="2026-06-12T00:00:00Z",
    )


def test_projects_empty_state_is_creation_first():
    html = projects_page(projects=[], backend="gemini")
    assert "New project" in html
    # empty state keeps the form inline (a titled card), not tucked away
    assert "<details" not in html.split("New project")[0][-400:]


def test_projects_with_items_is_list_first():
    html = projects_page(projects=[_fake_project("Acme Corp")], backend="gemini")
    # the list (and its header) comes before the collapsed creation form
    assert "Your projects" in html
    assert html.index("Acme Corp") < html.index("New project")
    # creation form is now collapsed into a <details>, not pushing the list down
    assert "<details" in html
    assert "Your projects" in html.split("<details")[0]
