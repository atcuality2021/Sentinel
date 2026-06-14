"""render.account_detail — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .accounts import _account_href, _fmt_when
from .artifacts import _run_sources
from .base import _CHARTJS, _badge, shell

def _mem_row(e) -> str:
    """One memory entry: boundary badge + escaped content + a read-only strength hint."""
    hint = (f"<span class='src'>· strength {e.strength:.1f} · seen {e.access_count}×</span>")
    return f"<li>{_badge(e.boundary)}{escape(e.content)} {hint}</li>"


def _mem_section(title: str, entries: list) -> str:
    """A labeled memory section. Renders nothing when empty (AC-4: an entity with only public
    memory shows no private section)."""
    if not entries:
        return ""
    rows = "".join(_mem_row(e) for e in entries)
    return f"<h2 class='sec'>{escape(title)}</h2><ul class='find'>{rows}</ul>"


def _account_donut(public: int, private: int) -> tuple[str, str]:
    """Cumulative provenance donut for the account header (reuses the artifact donut pattern)."""
    data = json.dumps({"pub": public, "priv": private})
    js = (
        "<script src='" + _CHARTJS + "'></script><script>"
        "var a=__DATA__,_C=getComputedStyle(document.documentElement),"
        "MUT=(_C.getPropertyValue('--muted')||'#8b97a8').trim(),"
        "PANEL=(_C.getPropertyValue('--panel')||'#0e1420').trim();"
        "new Chart(document.getElementById('cAcc'),{type:'doughnut',"
        "data:{labels:['Public','Private'],datasets:[{data:[a.pub,a.priv],"
        "backgroundColor:['#4ea1ff','#ffb24d'],borderColor:PANEL,borderWidth:2}]},"
        "options:{cutout:'62%',plugins:{legend:{position:'bottom',labels:{color:MUT,"
        "boxWidth:12,font:{size:11}}}}}});</script>"
    ).replace("__DATA__", data)
    card = (
        "<div class='card'><h3 class='ch'>Cumulative provenance</h3>"
        "<div class='chart-wrap' style='height:180px'><canvas id='cAcc'></canvas></div>"
        "<div style='margin-top:14px;display:flex;flex-direction:column;gap:8px'>"
        f"<span class='pill'><span class='dotmark g'></span>Public: <b>{public}</b></span>"
        f"<span class='pill'><span class='dotmark v'></span>Private: <b>{private}</b></span>"
        "</div></div>"
    )
    return card, js


def _danger_zone(entity: str, *, confirm: bool) -> str:
    """Purge control. Default = a link to reveal confirm; confirm = the actual POST + cancel.
    Deletion is never reachable by a safe method (AC-8)."""
    href = _account_href(entity)
    if confirm:
        body = (
            "<p class='note'>This permanently deletes <b>all memory and run history</b> for this "
            "account. It cannot be undone.</p>"
            f"<div class='set-actions'><form method='post' action='{href}/purge'>"
            "<button class='btn' style='background:var(--bad)' type='submit'>"
            "Yes, purge this account</button></form>"
            f"<a class='btn ghost' href='{href}'>Cancel</a></div>"
        )
    else:
        body = (
            "<p class='note'>Remove this account's memory and run history (data-subject "
            "right-to-deletion).</p>"
            f"<div class='set-actions'><a class='btn ghost' href='{href}?confirm=purge'>"
            "Purge account…</a></div>"
        )
    return (f"<div class='card err' style='margin-top:18px'>"
            f"<h2 class='sec' style='color:var(--bad);margin-top:0'>Danger zone</h2>{body}</div>")


def account_detail_page(*, summary, runs: list, public_mem: list, private_mem: list,
                        backend: str, confirm: bool = False, ok: str = "") -> str:
    """One account: header + provenance donut + run timeline + boundary-separated memory."""
    banner = f"<div class='card banner ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    pills = "".join(
        f"<span class='pill'>{escape(label)}: <b>{escape(val)}</b></span>"
        for label, val in (
            ("Modes", ", ".join(summary.modes) or "—"),
            ("Kinds", ", ".join(summary.kinds) or "—"),
            ("Runs", str(summary.runs)),
            ("Last run", _fmt_when(summary.last_run_at)),
        )
    )
    donut, js = _account_donut(summary.public, summary.private)
    header = (
        "<div class='card'>"
        f"<h2 style='font-size:24px;margin:0 0 10px'>{escape(summary.display_name)}</h2>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap'>{pills}</div></div>"
    )

    trows = ""
    for r in runs:
        # run_seq is 1-based per entity; 0 is the pre-008 sentinel (never sequenced) → neutral dash.
        seq = f"#{r.run_seq}" if getattr(r, "run_seq", 0) else "—"
        trows += (
            f"<tr><td class='mono'>{escape(seq)}</td>"
            f"<td>{escape(r.mode)}</td>"
            f"<td><span class='dotmark {'v' if r.backend=='vllm' else 'g'}'></span> "
            f"<span class='mono'>{escape(r.backend)}</span></td>"
            f"<td><span class='badge public'>{r.public}</span>"
            f"<span class='badge private'>{r.private}</span>"
            f"<span class='gap'>{r.gaps} gaps</span></td>"
            f"<td class='mono'>{escape(r.reference)}</td>"
            f"<td class='mono'>{escape(_fmt_when(r.created_at))}</td>"
            f"<td>{_run_sources(getattr(r, 'sources', []) or [])}</td></tr>"
        )
    timeline = (
        "<h2 class='sec'>Run timeline</h2>"
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>#</th><th>Mode</th><th>Backend</th><th>Public / Private / Gaps</th>"
        "<th>Saved to</th><th>When</th><th>Sources</th></tr></thead>"
        f"<tbody>{trows}</tbody></table></div>"
    )

    memory = _mem_section("Public signal", public_mem) + _mem_section("Private signal", private_mem)
    if not memory:
        memory = ("<h2 class='sec'>Accumulated memory</h2>"
                  "<div class='card'><div class='empty'>No memory retained for this account "
                  "(entity memory may be off, or findings have decayed).</div></div>")

    left = header + timeline + memory + _danger_zone(summary.entity, confirm=confirm)
    content = (
        banner
        + "<div style='margin-bottom:16px'><a href='/accounts' style='color:var(--muted)'>"
        "← All accounts</a></div>"
        + f"<div class='two-col'><div>{left}</div>{donut}</div>"
    )
    return shell(active="accounts", title=summary.display_name, content=content,
                 backend=backend, body_scripts=js)


def not_found_page(*, what: str, backend: str) -> str:
    """Clean not-found card (AC-9) — a GET of an unknown account is a 200 page, never a 500."""
    content = (
        "<div class='card'><div class='empty'>"
        f"No such account: <b>{escape(what)}</b>.<br>"
        "It may have been purged, or never researched. "
        "<a href='/accounts' style='color:var(--accent-2)'>Back to Accounts</a>."
        "</div></div>"
    )
    return shell(active="accounts", title="Not found", content=content, backend=backend)
