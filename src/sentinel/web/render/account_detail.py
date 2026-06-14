"""render.account_detail — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .accounts import _account_href, _fmt_when
from .artifacts import _run_sources
from .base import _badge, _icon, shell


def _mem_row(e) -> str:
    """One memory entry: boundary badge + escaped content + a read-only strength hint."""
    hint = (f"<span class='muted' style='font-size:12px'>· strength "
            f"{e.strength:.1f} · seen {e.access_count}×</span>")
    return (f"<div class='row-between' style='gap:10px'>"
            f"<span>{_badge(e.boundary)} {escape(e.content)} {hint}</span></div>"
            "<div class='divider'></div>")


def _mem_section(title: str, entries: list) -> str:
    """A labeled memory section. Renders nothing when empty (AC-4: an entity with only public
    memory shows no private section)."""
    if not entries:
        return ""
    is_private = "private" in title.lower()
    accent = "var(--private)" if is_private else "var(--public)"
    border = " style='border-color:var(--private)'" if is_private else ""
    rows = "".join(_mem_row(e) for e in entries)
    # Trim the trailing divider for a clean card edge.
    if rows.endswith("<div class='divider'></div>"):
        rows = rows[: -len("<div class='divider'></div>")]
    return (
        f"<div class='card'{border}><div class='card-head'>"
        f"<h2 style='color:{accent}'>{escape(title)}</h2></div>"
        f"<div class='stack' style='font-size:13px'>{rows}</div></div>"
    )


def _account_donut(public: int, private: int) -> tuple[str, str]:
    """Cumulative provenance donut for the account header (CSS conic-gradient — no JS)."""
    total = public + private
    pub_pct = (public / total * 100) if total else 0
    gradient = (
        f"conic-gradient(var(--public) 0 {pub_pct:.1f}%,"
        f"var(--private) {pub_pct:.1f}% 100%)"
    )
    card = (
        "<div class='card'><div class='card-head'><h2>Cumulative provenance</h2></div>"
        "<div class='inline' style='gap:22px;align-items:center'>"
        f"<div class='donut' style='background:{gradient}'>"
        f"<div class='center'><b>{total}</b><span>facts</span></div></div>"
        "<div class='legend'>"
        "<div class='row'><span class='sw' style='background:var(--public)'></span>"
        f"Public: <b>{public}</b></div>"
        "<div class='row'><span class='sw' style='background:var(--private)'></span>"
        f"Private: <b>{private}</b></div>"
        "</div></div></div>"
    )
    return card, ""


def _danger_zone(entity: str, *, confirm: bool) -> str:
    """Purge control. Default = a link to reveal confirm; confirm = the actual POST + cancel.
    Deletion is never reachable by a safe method (AC-8)."""
    href = _account_href(entity)
    if confirm:
        body = (
            "<p class='muted'>This permanently deletes <b>all memory and run history</b> for this "
            "account. It cannot be undone.</p>"
            f"<div class='inline' style='margin-top:12px'><form method='post' action='{href}/purge'>"
            "<button class='btn danger' type='submit'>"
            "Yes, purge this account</button></form>"
            f"<a class='btn ghost' href='{href}'>Cancel</a></div>"
        )
    else:
        body = (
            "<p class='muted'>Remove this account's memory and run history (data-subject "
            "right-to-deletion).</p>"
            f"<div class='inline' style='margin-top:12px'><a class='btn ghost' "
            f"href='{href}?confirm=purge'>Purge account…</a></div>"
        )
    return (f"<div class='card' style='margin-top:18px;border-color:var(--bad)'>"
            f"<div class='card-head'><h2 style='color:var(--bad)'>Danger zone</h2></div>{body}</div>")


def account_detail_page(*, summary, runs: list, public_mem: list, private_mem: list,
                        backend: str, confirm: bool = False, ok: str = "") -> str:
    """One account: header + provenance donut + run timeline + boundary-separated memory."""
    banner = f"<div class='card pad-sm ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    modes = ", ".join(summary.modes) or "—"
    subtitle = (f"{summary.runs} runs · last {_fmt_when(summary.last_run_at)} · {escape(modes)}")
    head = (
        "<div class='page-head'><div class='grow'>"
        f"<h1>{escape(summary.display_name)}</h1><p>{subtitle}</p></div></div>"
    )

    kpis = (
        "<div class='grid cols-3' style='margin-bottom:24px'>"
        + _kpi_local("run", "Runs", summary.runs, "search")
        + _kpi_local("pub", "Public facts", summary.public, "globe")
        + _kpi_local("priv", "Private facts", summary.private, "lock")
        + "</div>"
    )

    donut, js = _account_donut(summary.public, summary.private)

    trows = ""
    for r in runs:
        # run_seq is 1-based per entity; 0 is the pre-008 sentinel (never sequenced) → neutral dash.
        seq = f"#{r.run_seq}" if getattr(r, "run_seq", 0) else "—"
        trows += (
            f"<tr><td class='mono'>{escape(seq)}</td>"
            f"<td>{escape(r.mode)}</td>"
            f"<td class='mono'>{escape(r.backend)}</td>"
            f"<td><span class='badge public'>{r.public}</span> "
            f"<span class='badge private'>{r.private}</span> "
            f"<span class='muted'>{r.gaps} gaps</span></td>"
            f"<td class='mono'>{escape(r.reference)}</td>"
            f"<td class='muted mono'>{escape(_fmt_when(r.created_at))}</td>"
            f"<td>{_run_sources(getattr(r, 'sources', []) or [])}</td></tr>"
        )
    timeline = (
        "<div class='card'><div class='card-head'><h2>Run timeline</h2></div>"
        "<div class='table-wrap'><table class='table'><thead><tr>"
        "<th>#</th><th>Mode</th><th>Backend</th><th>Public / Private / Gaps</th>"
        "<th>Saved to</th><th>When</th><th>Sources</th></tr></thead>"
        f"<tbody>{trows}</tbody></table></div></div>"
    )

    memory = _mem_section("Public signal", public_mem) + _mem_section("Private signal", private_mem)
    if not memory:
        memory = ("<div class='card'><div class='card-head'><h2>Accumulated memory</h2></div>"
                  "<div class='empty'>"
                  f"<div class='ico'>{_icon('brain')}</div>No memory retained for this account "
                  "(entity memory may be off, or findings have decayed).</div></div>")

    right = donut + f"<div class='stack' style='margin-top:18px'>{memory}</div>"
    left = timeline + _danger_zone(summary.entity, confirm=confirm)
    content = (
        banner
        + head
        + "<div style='margin-bottom:16px'><a href='/accounts' class='muted'>"
        "← All accounts</a></div>"
        + kpis
        + f"<div class='split' style='align-items:start'><div class='stack'>{left}</div>"
        f"<div class='stack'>{right}</div></div>"
    )
    return shell(active="accounts", title=summary.display_name, content=content,
                 backend=backend, body_scripts=js)


def _kpi_local(cls: str, label: str, value, icon: str) -> str:
    """Account KPI tile. (Local helper — value is an int that needs no escaping.)"""
    return (
        f"<div class='card kpi {cls}'><div class='kpi-icon'>{_icon(icon)}</div>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{value}</div></div>"
    )


def not_found_page(*, what: str, backend: str) -> str:
    """Clean not-found card (AC-9) — a GET of an unknown account is a 200 page, never a 500."""
    content = (
        "<div class='card'><div class='empty'>"
        f"<div class='ico'>{_icon('users')}</div>"
        f"No such account: <b>{escape(what)}</b>.<br>"
        "It may have been purged, or never researched. "
        "<a href='/accounts'>Back to Accounts</a>."
        "</div></div>"
    )
    return shell(active="accounts", title="Not found", content=content, backend=backend)
