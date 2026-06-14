"""render.reports — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import _icon, _project_subnav, shell
from .plan import _prio_badge, _verdict_badge

# --------------------------------------------------------------------------- #
# Project Report page — consulting-grade output compiled from task results
# --------------------------------------------------------------------------- #

def _rpt_section(num: str, title: str, body: str) -> str:
    return (
        f"<div class='card' style='margin-bottom:16px'>"
        f"<div class='card-head'>"
        f"<span class='pill'>{escape(num)}</span>"
        f"<h2>{escape(title)}</h2>"
        f"</div>{body}</div>"
    )


def _rpt_callout(label: str, body: str, variant: str = "") -> str:
    _BADGE = {"green": "ok", "gold": "warn"}
    badge = _BADGE.get(variant, "neutral")
    return (
        f"<div class='card pad-sm' style='margin:16px 0'>"
        f"<div class='inline' style='margin-bottom:8px'>"
        f"<span class='badge {badge}'>{escape(label)}</span></div>"
        f"<div>{body}</div>"
        f"</div>"
    )


def _rpt_metric(val: str, label: str) -> str:
    return (
        f"<div class='kpi'>"
        f"<div class='value'>{escape(val)}</div>"
        f"<div class='label'>{escape(label)}</div>"
        f"</div>"
    )


def _rpt_table(headers: list[str], rows: list[list[str]]) -> str:
    ths = "".join(f"<th>{escape(h)}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        "<div class='table-wrap' style='margin:16px 0'><table class='table'>"
        f"<thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>"
    )


def _src_link(src: dict) -> str:
    """Render a Finding.source dict as a compact linked badge for report tables.

    Only emits an <a href> for http/https URLs — blocks javascript: and data: scheme injection.
    """
    if not src or not isinstance(src, dict):
        return "<span class='muted' style='font-size:11px'>—</span>"
    label = escape(str(src.get("label") or "source"))
    url   = str(src.get("url") or "").strip()
    if url and (url.startswith("https://") or url.startswith("http://")):
        return (f"<a href='{escape(url)}' target='_blank' rel='noopener' "
                f"style='font-size:11px;color:var(--accent-text)'>{label}</a>")
    return f"<span class='muted' style='font-size:11px'>{label}</span>"


def project_report_page(*, project, tasks: list, backend: str) -> str:
    """Research Intelligence Report — compiled dynamically from actual task artifacts."""
    pname = escape(project.name)
    subnav = _project_subnav(project.id, "report", project.name)

    done_tasks = [t for t in tasks if t.get("status") == "done" and t.get("result")]

    cover = (
        "<div class='page-head'><div class='grow'>"
        f"<h1>{pname}</h1>"
        "<p>Consulting-grade report compiled from all task results — "
        "on-premise sovereign AI, zero cloud dependency.</p>"
        "</div>"
        "<span class='pill'>Confidential</span>"
        "<span class='pill'><span class='dot' style='color:var(--ok)'></span>Sovereign On-Premise</span>"
        f"<span class='pill'>{len(done_tasks)} Research Task"
        f"{'s' if len(done_tasks) != 1 else ''} Complete</span>"
        "</div>"
    )

    if not done_tasks:
        return shell(
            active="projects", title=f"{project.name} · Report",
            content=(cover
                     + "<div class='card'><div class='empty'>"
                     f"<div class='ico'>{_icon('doc')}</div>"
                     "No completed research tasks yet — run a task to populate this report."
                     "</div></div>"),
            backend=backend, subnav=subnav, project=project.name,
        )

    _SUB = "font-size:13px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)"
    sections: list[str] = []
    # OD report frame: a per-task results overview table + the first executive
    # summary, rendered above the detailed per-task sections.
    overview_rows: list[list[str]] = []
    exec_summary_text = ""

    for i, task in enumerate(done_tasks, 1):
        result  = task.get("result") or {}
        payload = result.get("dashboard_payload") or {}
        obj_raw = task.get("objective") or ""

        # Support both dashboard_payload shapes produced by the DAG:
        #   shape A (BiltIQ plan):  {"map": profile, "matrix": [cm, …], "strategy": strategy}
        #   shape B (generic plan): {"artifacts": {output_key: artifact, …}}
        if "artifacts" in payload:
            arts = payload["artifacts"] or {}
            self_prof   = next((v for v in arts.values()
                                if isinstance(v, dict) and "products" in v and "org" in v), None)
            comparisons = [v for v in arts.values()
                           if isinstance(v, dict) and "axes" in v and "subject" in v]
            strategy    = next((v for v in arts.values()
                                if isinstance(v, dict) and "action_plan" in v and "assessment" in v), None)
            # New specialist domains
            govt_art    = next((v for v in arts.values()
                                if isinstance(v, dict) and "department_mappings" in v
                                and "executive_summary" in v), None)
            prod_art    = next((v for v in arts.values()
                                if isinstance(v, dict) and "products_found" in v
                                and "winner_rationale" in v), None)
        else:
            self_prof   = payload.get("map") if isinstance(payload.get("map"), dict) else None
            comparisons = [m for m in (payload.get("matrix") or []) if isinstance(m, dict)]
            strategy    = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else None
            govt_art    = None
            prod_art    = None

        citations = result.get("citations") or []

        # ── OD frame: derive a one-line summary + capture exec text ───────────
        if govt_art:
            _depts = [d for d in (govt_art.get("department_mappings") or []) if isinstance(d, dict)]
            _ov_summary = f"{len(_depts)} departments mapped" if _depts else "Govt proposal"
            if not exec_summary_text and govt_art.get("executive_summary"):
                exec_summary_text = str(govt_art["executive_summary"])
        elif prod_art:
            _prods = [p for p in (prod_art.get("products_found") or []) if isinstance(p, dict)]
            _win = str(prod_art.get("winner") or "").strip()
            _ov_summary = (f"{len(_prods)} products" + (f" · winner {_win}" if _win else "")) \
                if _prods else "Product research"
            if not exec_summary_text and prod_art.get("one_line_summary"):
                exec_summary_text = str(prod_art["one_line_summary"])
        else:
            _np = len([p for p in (self_prof.get("products") or []) if isinstance(p, dict)]) \
                if self_prof else 0
            _ov_summary = f"{_np} product(s) · {len(comparisons)} competitor(s)"
            if not exec_summary_text and strategy and strategy.get("assessment"):
                exec_summary_text = str(strategy["assessment"])
        overview_rows.append([
            f"<b>{escape(obj_raw[:70] + ('…' if len(obj_raw) > 70 else ''))}</b>",
            "<span class='badge ok'>done</span>",
            f"<span class='muted'>{escape(_ov_summary)}</span>",
        ])

        obj_trunc_display = obj_raw[:80] + ("…" if len(obj_raw) > 80 else "")
        body = (f"<p class='note' style='margin-bottom:16px'>"
                f"<b>Objective:</b> {escape(obj_trunc_display)}</p>")

        # ── Domain-aware metric row ───────────────────────────────────────────
        if govt_art:
            depts   = [d for d in (govt_art.get("department_mappings") or []) if isinstance(d, dict)]
            client  = escape(str(govt_art.get("client") or "Client"))
            vendor  = escape(str(govt_art.get("vendor") or "Vendor"))
            pilot   = "Defined" if govt_art.get("pilot_plan") else "—"
            body += (
                "<div class='grid cols-3'>"
                + _rpt_metric(str(len(depts)) if depts else "—", "Departments Mapped")
                + _rpt_metric(pilot,                             "Pilot Plan")
                + _rpt_metric(str(len(citations)),               "Sources Cited")
                + "</div>"
                + "<div class='inline' style='margin:12px 0'>"
                + f"<span class='pill'>client: <b>{client}</b></span>"
                + f"<span class='pill'>vendor: <b>{vendor}</b></span>"
                + "</div>"
            )
        elif prod_art:
            prods  = [p for p in (prod_art.get("products_found") or []) if isinstance(p, dict)]
            winner = escape(str(prod_art.get("winner") or "—"))
            body += (
                "<div class='grid cols-3'>"
                + _rpt_metric(str(len(prods)) if prods else "—", "Products Found")
                + _rpt_metric(winner if winner != "—" else "—",   "Recommended")
                + _rpt_metric(str(len(citations)),                 "Sources Cited")
                + "</div>"
            )
        else:
            n_prods = len([p for p in (self_prof.get("products") or []) if isinstance(p, dict)]) \
                      if self_prof else 0
            n_cmps  = len(comparisons)
            body += (
                "<div class='grid cols-3'>"
                + _rpt_metric(str(n_prods) if n_prods else "—", "Products Profiled")
                + _rpt_metric(str(n_cmps),                       "Competitor(s) Compared")
                + _rpt_metric(str(len(citations)),               "Sources Cited")
                + "</div>"
            )

        # ── GovernmentProposal content ────────────────────────────────────────
        if govt_art:
            exec_sum = str(govt_art.get("executive_summary") or "")
            if exec_sum:
                body += _rpt_callout("Executive Summary", escape(exec_sum), "green")

            challenges = [f for f in (govt_art.get("client_challenges") or []) if isinstance(f, dict)]
            if challenges:
                body += f"<h3 style='{_SUB}'>Client Challenges ({len(challenges)})</h3>"
                ch_rows = [
                    [escape(str(f.get("text") or ""))[:160],
                     _src_link(f.get("source") or {})]
                    for f in challenges[:8]
                ]
                body += _rpt_table(["Challenge", "Source"], ch_rows)

            capabilities = [f for f in (govt_art.get("vendor_capabilities") or []) if isinstance(f, dict)]
            if capabilities:
                body += f"<h3 style='{_SUB}'>Vendor Capabilities ({len(capabilities)})</h3>"
                cap_rows = [
                    [escape(str(f.get("text") or ""))[:160],
                     _src_link(f.get("source") or {})]
                    for f in capabilities[:8]
                ]
                body += _rpt_table(["Capability", "Source"], cap_rows)

            depts = [d for d in (govt_art.get("department_mappings") or []) if isinstance(d, dict)]
            if depts:
                body += f"<h3 style='{_SUB}'>Department Mappings ({len(depts)})</h3>"
                dept_rows = [
                    [escape(str(d.get("department") or ""))[:50],
                     escape(str(d.get("challenge") or ""))[:120],
                     escape(str(d.get("solution") or ""))[:120],
                     escape(str(d.get("impact") or ""))[:80]]
                    for d in depts
                ]
                body += _rpt_table(["Department", "Challenge", "BiltIQ Solution", "Impact"], dept_rows)

            comp_adv = str(govt_art.get("competitive_advantage") or "")
            if comp_adv:
                body += _rpt_callout("Competitive Advantage — Sovereign AI", escape(comp_adv), "")

            pilot = str(govt_art.get("pilot_plan") or "")
            if pilot:
                body += _rpt_callout("90-Day Pilot Plan", escape(pilot), "green")

        # ── ProductResearch content ───────────────────────────────────────────
        elif prod_art:
            summary_txt = str(prod_art.get("one_line_summary") or "")
            if summary_txt:
                body += _rpt_callout("Summary", escape(summary_txt), "green")

            winner      = str(prod_art.get("winner") or "")
            winner_why  = str(prod_art.get("winner_rationale") or "")
            if winner:
                body += (
                    f"<h3 style='{_SUB}'>Recommended Product</h3>"
                    "<div class='card pad-sm' style='border-left:3px solid var(--ok)'>"
                    f"<div style='font-size:18px;font-weight:700;color:var(--ok)'>{escape(winner)}</div>"
                    + (f"<div class='muted' style='margin-top:6px;font-size:13px'>"
                       f"{escape(winner_why)}</div>" if winner_why else "")
                    + "</div>"
                )

            prods = [p for p in (prod_art.get("products_found") or []) if isinstance(p, dict)]
            if prods:
                body += f"<h3 style='{_SUB}'>Products Compared ({len(prods)})</h3>"
                prod_rows = [
                    [escape(str(p.get("name") or ""))[:50],
                     escape(str(p.get("brand") or ""))[:30],
                     escape(str(p.get("price") or ""))[:20],
                     escape(str(p.get("processor") or ""))[:40],
                     escape(f"{p.get('ram') or '—'} / {p.get('storage') or '—'}")[:30],
                     escape(str(p.get("score") or "—"))[:10]]
                    for p in prods
                ]
                body += _rpt_table(
                    ["Model", "Brand", "Price", "Processor", "RAM / Storage", "Score"],
                    prod_rows
                )

            ranking = [r for r in (prod_art.get("value_ranking") or []) if r]
            if ranking:
                body += f"<h3 style='{_SUB}'>Value Ranking</h3>"
                rank_html = "".join(
                    f"<li><b>#{j+1}</b> {escape(str(r))}</li>"
                    for j, r in enumerate(ranking[:8])
                )
                body += f"<div class='card pad-sm'><ol style='margin:0;padding-left:20px'>{rank_html}</ol></div>"

        # ── Market / competitor research content ──────────────────────────────
        else:
            if self_prof:
                org   = escape(str(self_prof.get("org") or ""))
                prods = [p for p in (self_prof.get("products") or []) if isinstance(p, dict)]
                body += f"<h3 style='{_SUB}'>Entity Profile: {org}</h3>"
                if prods:
                    rows = [
                        [escape(str(p.get("name") or ""))[:60],
                         escape(str(p.get("category") or ""))[:40],
                         escape(str(p.get("positioning") or ""))[:140],
                         escape(", ".join(str(s) for s in p.get("strengths") or [])[:100])]
                        for p in prods
                    ]
                    body += _rpt_table(["Product / Model", "Category", "Positioning", "Key Strengths"], rows)
                else:
                    gaps     = self_prof.get("gaps") or []
                    gap_note = (" ".join(
                        (g.get("description") or str(g)) if isinstance(g, dict) else str(g)
                        for g in gaps[:2]
                    ))
                    body += (
                        "<div class='card pad-sm'><div class='empty'>"
                        f"No product data extracted for <b>{org}</b>."
                        + (f" ({escape(gap_note)})" if gap_note else "")
                        + " The entity may lack a strong public web presence, or the research queries"
                        " need refinement for this product category."
                        "</div></div>"
                    )

            for cm in comparisons:
                subj  = escape(str(cm.get("subject") or "Us"))
                rival = escape(str(cm.get("rival") or "Rival"))
                axes  = [a for a in (cm.get("axes") or []) if isinstance(a, dict)]
                body += f"<h3 style='{_SUB}'>Head-to-Head: {subj} vs {rival}</h3>"
                if axes:
                    rows = [
                        [escape(str(a.get("axis") or "")),
                         escape(str(a.get("ours") or "—")),
                         escape(str(a.get("theirs") or "—")),
                         _verdict_badge(str(a.get("verdict") or ""))]
                        for a in axes
                    ]
                    body += _rpt_table(["Dimension", subj, rival, "Verdict"], rows)
                    w = sum(1 for a in axes if a.get("verdict") == "win")
                    l = sum(1 for a in axes if a.get("verdict") == "lose")
                    p = sum(1 for a in axes if a.get("verdict") == "parity")
                    clr = "var(--ok)" if w > l else "var(--bad)" if l > w else "var(--warn)"
                    body += (
                        f"<div class='muted' style='font-size:12px;margin:4px 0 8px'>"
                        f"Score vs {rival}: "
                        f"<span style='color:{clr};font-weight:700'>{w}&nbsp;Win / {l}&nbsp;Lose / {p}&nbsp;Parity</span>"
                        "</div>"
                    )
                else:
                    body += "<div class='card pad-sm'><div class='empty'>No comparison dimensions produced.</div></div>"

            if strategy:
                assessment = str(strategy.get("assessment") or "")
                actions    = [a for a in (strategy.get("action_plan") or []) if isinstance(a, dict)]
                if assessment:
                    body += _rpt_callout(
                        "Research Conclusion & Recommendation",
                        f"<strong>{escape(assessment)}</strong>",
                        "green",
                    )
                if actions:
                    act_rows = [
                        [_prio_badge(str(a.get("priority") or "med")),
                         escape(str(a.get("action") or ""))[:120],
                         escape(str(a.get("rationale") or ""))[:120],
                         escape(str(a.get("timeline") or ""))]
                        for a in actions
                    ]
                    body += (
                        f"<h3 style='{_SUB}'>Recommended Actions</h3>"
                        + _rpt_table(["Priority", "Action", "Rationale", "Timeline"], act_rows)
                    )

        # ── Sources (all domains) ─────────────────────────────────────────────
        if citations:
            cites = "".join(
                "<li>"
                + (f"<span class='badge "
                   + ("public" if str(c.get("boundary") or "").lower() == "public" else "private")
                   + f"' style='margin-right:6px'>{escape(str(c.get('boundary') or '?').upper())}</span>"
                   + f"<b>{escape(str(c.get('label') or '—'))}</b>"
                   + (f" · <a href='{escape(str(c['url']))}' target='_blank' rel='noopener' "
                      f"style='color:var(--accent-text)'>{escape(str(c['url']))}</a>"
                      if c.get("url") else "")
                   if isinstance(c, dict) else escape(str(c)))
                + "</li>"
                for c in citations[:20]
            )
            body += (
                f"<h3 style='{_SUB}'>Sources ({len(citations)})</h3>"
                f"<div class='card pad-sm'><ul class='find'>{cites}</ul></div>"
            )

        obj_trunc = obj_raw[:70] + ("…" if len(obj_raw) > 70 else "")
        sections.append(_rpt_section(str(i).zfill(2), f"Task {i}: {obj_trunc}", body))

    # ── OD top frame: exec-summary card + per-task results table ──────────────
    exec_card = ""
    if exec_summary_text:
        exec_card = (
            "<div class='card' style='margin-bottom:16px'>"
            "<p class='eyebrow'>Executive summary</p>"
            f"<p style='margin-top:6px'>{escape(exec_summary_text[:600])}</p></div>"
        )
    overview_card = (
        "<div class='card' style='margin-bottom:16px'>"
        "<div class='card-head'><h2>Per-task results</h2>"
        f"<span class='pill'>{len(done_tasks)} complete</span></div>"
        + _rpt_table(["Task", "Status", "Summary"], overview_rows)
        + "</div>"
    )

    return shell(
        active="projects",
        title=f"{project.name} · Report",
        content=cover + exec_card + overview_card + "".join(sections),
        backend=backend,
        subnav=subnav,
        project=project.name,
    )
