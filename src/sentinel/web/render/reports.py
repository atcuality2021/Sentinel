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


def _project_report_page_LEGACY(*, project, tasks: list, backend: str) -> str:
    """Kept for reference — hardcoded BiltIQ AI consulting report (replaced by dynamic version above)."""
    pid = escape(project.id)
    pname = escape(project.name)
    subnav = _project_subnav(project.id, "report", project.name)

    # ── Cover ──────────────────────────────────────────────────────────────────
    done_count = sum(1 for t in tasks if t.get("status") in ("done", "failed") and t.get("result"))
    cover = (
        "<div class='rpt-cover'>"
        f"<div class='rpt-firm'>Sentinel Intelligence Platform · Sovereign Research Division</div>"
        f"<h1>{pname}<br>Strategic Business Audit &amp;<br>Go-To-Market Blueprint</h1>"
        f"<p class='rpt-sub'>Enterprise Sovereign AI in India — Market Opportunity, "
        f"Competitive Positioning &amp; 90-Day Activation</p>"
        "<div class='rpt-meta'>"
        "<span class='rpt-tag'>Confidential</span>"
        "<span class='rpt-tag gold'>BFSI &amp; Healthcare Focus</span>"
        "<span class='rpt-tag green'>Regulated Enterprise India</span>"
        f"<span class='rpt-tag' style='background:var(--panel-2)'>{done_count} Research Tasks</span>"
        "</div>"
        "</div>"
    )

    # ── S1 Executive Summary ───────────────────────────────────────────────────
    metrics = (
        "<div class='rpt-metrics'>"
        + _rpt_metric("$4.1B", "India Enterprise AI TAM 2026")
        + _rpt_metric("38%", "CAGR 2026–2029")
        + _rpt_metric("10", "Tier-1 Target Accounts")
        + _rpt_metric("90 days", "To First Revenue Signal")
        + "</div>"
    )
    findings_rows = [
        ["<span class='badge' style='background:rgba(234,67,53,.18);color:#ff6b6b;border:0'>Critical</span>",
         "<strong>Regulatory tailwind is structural.</strong> DPDP Act 2023, RBI AI/ML Circular (Apr 2024), "
         "and IRDAI digital guidelines mandate data residency that cloud AI cannot satisfy.",
         "Lead with \"DPDP-compliant by architecture\" — compliance is a product feature."],
        ["<span class='badge' style='background:rgba(234,67,53,.18);color:#ff6b6b;border:0'>Critical</span>",
         "<strong>HDFC Bank is the anchor account.</strong> Publicly committed to \"AI-first in 24 months\" "
         "with 15+ active GenAI programs. RBI governance gap = BiltIQ's immediate entry wedge.",
         "Prioritise HDFC as Pilot #1. One BFSI logo accelerates the entire pipeline."],
        ["<span class='badge' style='background:rgba(251,191,36,.14);color:#fbbf24;border:0'>High</span>",
         "<strong>No sovereign-AI competitor owns India BFSI.</strong> Kore.ai, Yellow.ai, Haptik are "
         "chatbot-first — they lack multi-agent orchestration and governance depth.",
         "18–24 month window to define the \"Sovereign Agentic AI\" category before hyperscalers pivot."],
        ["<span class='badge' style='background:rgba(251,191,36,.14);color:#fbbf24;border:0'>High</span>",
         "<strong>Azure OpenAI is the real competitive threat.</strong> Microsoft pitches Azure India "
         "regions as \"DPDP-ready.\" Counter: \"data never leaves your datacenter.\"",
         "Every sales play must neutralise the \"Azure India region = compliance\" objection."],
        ["<span class='badge' style='background:rgba(52,168,83,.12);color:#5bd07f;border:0'>Opportunity</span>",
         "<strong>Healthcare is the faster sales cycle.</strong> Apollo &amp; Manipal are under NHA/ABDM "
         "pressure and actively buying. BFSI has longer cycles but higher ACV.",
         "Use Healthcare for 60-day quick wins; use those logos to unlock BFSI boardrooms."],
    ]
    s1_body = (
        metrics
        + _rpt_callout(
            "Bottom Line Up Front",
            f"<strong>{pname}</strong> is entering the market at the optimal moment. India's DPDP Act and "
            "RBI/IRDAI mandates are creating <strong>structural demand</strong> for sovereign, on-premise AI "
            "that cloud vendors cannot serve. The competitive window to establish category leadership in "
            "India's regulated enterprise segment is approximately <strong>18–24 months</strong>."
        )
        + _rpt_table(
            ["Priority", "Finding", "Implication"],
            findings_rows,
        )
    )

    # ── S2 Company Profile ─────────────────────────────────────────────────────
    prod_rows = [
        ["<strong>On-Premise Agentic AI Suite</strong>",
         "Multi-agent orchestration deployable on customer infrastructure — bare metal, private cloud, "
         "or air-gapped. Research agents, process-automation agents, decision-support agents.",
         "CTO / CIO", "Zero-egress architecture; local LLM execution (Gemma-4 12B/26B or BYOM)"],
        ["<strong>Custom AI Services</strong>",
         "Domain-specific model fine-tuning, RAG pipeline build, AI governance frameworks, "
         "integration with core banking / HIS / ERP systems.",
         "CDO / Business Unit Heads", "Deep vertical expertise; full source-code delivery"],
        ["<strong>Sovereign Intelligence Platform</strong>",
         "Research orchestration (this Sentinel platform) — market intelligence, competitive analysis, "
         "account briefs — all running on-premise.",
         "Strategy / BD Teams", "Replaces $50K/yr analyst subscriptions; on-premise"],
    ]
    tech_rows = [
        ["Sovereign Embedding", "Qwen3-VL-Embedding-2B (self-hosted)", "No data sent to OpenAI/Cohere; DPDP-safe"],
        ["Hybrid RAG", "BM25 (keyword) + ChromaDB (semantic) + Cross-encoder reranker", "Higher recall on domain jargon (medical, financial)"],
        ["Dual-Tier Inference", "Gemma 12B tool-calling + Gemma 26B reasoning (vLLM)", "Fast responses + deep analysis; zero API dependency"],
        ["A2A Protocol", "Google ADK Agent-to-Agent coordination", "Composable multi-agent systems; interop with existing AI"],
        ["MCP Integration", "Model Context Protocol for persistent memory + tool access", "Agents that read/write institutional memory"],
    ]
    s2_body = (
        _rpt_callout(
            "Recommended Positioning",
            f"\"<strong>{pname}</strong> is the only enterprise AI platform that makes your organisation "
            "AI-first without compromising data sovereignty. Built for India's regulated enterprises — "
            "BFSI, Healthcare, Government, Manufacturing — where the data never leaves your control.\"",
        )
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>Product Portfolio</h3>"
        + _rpt_table(["Product", "Description", "Primary Buyer", "Differentiator"], prod_rows)
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>Technology Differentiators</h3>"
        + _rpt_table(["Capability", "Implementation", "Why It Matters"], tech_rows)
    )

    # ── S3 Market Opportunity ──────────────────────────────────────────────────
    tam_rows = [
        ["<strong>TAM</strong>", "Total India Enterprise AI Market", "$18B", "$48B", "Theoretical ceiling"],
        ["<strong>SAM</strong>", "Regulated verticals (BFSI, Healthcare, Government, Manufacturing)", "$4.1B", "$15B", "High — compliance creates budget"],
        ["<strong>SOM</strong>", "On-premise / sovereign AI deployments specifically", "$320M", "$1.2B", "Direct target — BiltIQ's core"],
    ]
    reg_rows = [
        ["<strong>DPDP Act 2023</strong>", "All regulated", "Data fiduciaries must prevent personal data egress. Cloud AI = liability.", "\"DPDP-compliant by architecture\""],
        ["<strong>RBI AI/ML Circular Apr 2024</strong>", "BFSI", "Full auditability of AI models in credit, fraud, and customer interactions.", "\"You own the weights, logs, audit trail\""],
        ["<strong>IRDAI Digital Guidelines 2024</strong>", "Insurance", "AI for underwriting/claims must demonstrate model governance and explainability.", "\"Explainable AI — satisfies IRDAI governance\""],
        ["<strong>NHA / ABDM Framework</strong>", "Healthcare", "Health data under ABDM must stay within India's health data ecosystem.", "\"Patient data never leaves your facility\""],
    ]
    s3_body = (
        "<div class='rpt-metrics'>"
        + _rpt_metric("$18B", "India AI Market TAM (2026)")
        + _rpt_metric("$4.1B", "Regulated Enterprise AI SAM")
        + _rpt_metric("$320M", "Sovereign/On-Prem AI SOM")
        + _rpt_metric("38%", "Regulated AI CAGR 2026–29")
        + "</div>"
        + _rpt_table(["Tier", "Market", "Size 2026", "2029 Projection", "BiltIQ Addressability"], tam_rows)
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>Regulatory Demand Drivers</h3>"
        + _rpt_table(["Regulation", "Sector", "AI Impact", "BiltIQ Angle"], reg_rows)
        + _rpt_callout(
            "3-Year Revenue Forecast (Conservative)",
            "<strong>2026:</strong> ₹3–5Cr ARR (3–5 paying customers) &nbsp;|&nbsp; "
            "<strong>2027:</strong> ₹15–25Cr ARR (10–15 accounts, BFSI anchors) &nbsp;|&nbsp; "
            "<strong>2028:</strong> ₹50–80Cr ARR (25–35 accounts, government pipeline + SI channel)",
            "green",
        )
    )

    # ── S4 Competitive Landscape ───────────────────────────────────────────────
    def _comp(title: str, badges: list[tuple[str, str]], desc: str, counter: str) -> str:
        badge_html = "".join(
            f"<span class='tag' style='color:{c}'>{escape(t)}</span>"
            for t, c in badges
        )
        return (
            f"<div class='comp-card'>"
            f"<h4>{escape(title)}</h4>"
            f"<div class='cc-tags'>{badge_html}</div>"
            f"<p>{desc}</p>"
            f"<div class='cc-win'>{_icon('bolt')} <strong>Counter:</strong> {counter}</div>"
            f"</div>"
        )

    comp_grid = (
        "<div class='comp-grid'>"
        + _comp("Microsoft Azure OpenAI (India)",
                [("Primary Threat", "#ff6b6b"), ("Cloud", "var(--muted)")],
                "Strong brand trust, Azure India regions, Office 365 integration. "
                "<strong>Gap:</strong> data exits India; DPDP compliance disputed; no model weight customisation.",
                "\"Azure India region ≠ data sovereignty. Microsoft is the data fiduciary. With BiltIQ, <em>you</em> are.\"")
        + _comp("Kore.ai",
                [("Indirect", "var(--muted)"), ("Chatbot-First", "var(--muted)")],
                "Strong in BFSI chatbots, decent India sales team. "
                "<strong>Gap:</strong> cloud-first, chatbot-centric (not agentic), limited governance tooling.",
                "\"Kore.ai answers customer questions. BiltIQ <em>acts</em> on institutional intelligence.\"")
        + _comp("Yellow.ai / Haptik",
                [("Indirect", "var(--muted)"), ("Displaceable", "#5bd07f")],
                "Large India customer base, WhatsApp Business integration. "
                "<strong>Gap:</strong> CX/support focused only; no agentic reasoning; Reliance ownership limits hospital/government sales.",
                "Position as complementary (BiltIQ for intelligence, Yellow for CX) or displace on enterprise AI consolidation deals.")
        + _comp("Google Vertex AI / Gemini Enterprise",
                [("Growing Threat", "#fbbf24"), ("Cloud", "var(--muted)")],
                "Superior multimodal AI, Google Cloud India. "
                "<strong>Gap:</strong> same data-sovereignty issues as Azure; premium pricing.",
                "\"Google's models are exceptional. BiltIQ runs those architectures in <em>your</em> datacenter.\"")
        + _comp("Avaamo",
                [("Niche Overlap", "var(--muted)")],
                "Healthcare/HR focus, decent on-premise option. "
                "<strong>Gap:</strong> US-centric, limited India presence, narrow HR/IT helpdesk use case.",
                "Broader platform, deeper India expertise, stronger governance story for BFSI.")
        + _comp("AWS Bedrock (India)",
                [("Moderate Threat", "#fbbf24"), ("Cloud", "var(--muted)")],
                "AWS India presence, enterprise relationships, broad model marketplace. "
                "<strong>Gap:</strong> \"model marketplace\" ≠ sovereign deployment; complex pricing.",
                "\"AWS Bedrock gives model choice in the cloud. BiltIQ gives model choice <em>in your datacenter</em>.\"")
        + "</div>"
    )
    matrix_rows = [
        ["<strong>Data Sovereignty</strong>", "✅ Full (on-prem)", "⚠️ India region only", "❌ Cloud", "❌ Cloud"],
        ["<strong>DPDP Compliance</strong>", "✅ Architectural", "⚠️ Legal claim only", "❌", "❌"],
        ["<strong>Agentic AI</strong>", "✅ Multi-agent DAG", "⚠️ Basic", "❌ Chatbot", "❌ Chatbot"],
        ["<strong>Customisable Models</strong>", "✅ BYOM + Gemma", "❌ Locked to OpenAI", "⚠️ Limited", "⚠️ Limited"],
        ["<strong>India Regulatory Depth</strong>", "✅ DPDP/RBI/IRDAI", "⚠️ Generic", "⚠️ Partial", "⚠️ Partial"],
    ]
    s4_body = (
        _rpt_callout(
            "Competitive Summary",
            "No dominant sovereign-AI platform exists in India. Cloud hyperscalers (Microsoft, Google, AWS) "
            "lead on mindshare but fail on data sovereignty. Indian conversational AI players (Kore.ai, "
            "Yellow.ai, Haptik) lack the multi-agent orchestration and governance depth regulated enterprises need.",
            "gold",
        )
        + comp_grid
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>Positioning Matrix</h3>"
        + _rpt_table(
            ["Dimension", f"<span style='color:var(--accent-2)'>{pname}</span>", "Azure OpenAI", "Kore.ai", "Yellow.ai"],
            matrix_rows,
        )
    )

    # ── S5 Target Accounts ─────────────────────────────────────────────────────
    def _acc(name: str, vertical: str, tier: str, maturity: str, mat_color: str,
             desc: str, entry: str) -> str:
        return (
            f"<div class='acc-card'>"
            f"<div class='ac-vert'>{escape(vertical)} · {escape(tier)}</div>"
            f"<h4>{escape(name)}</h4>"
            f"<span class='tag' style='color:{mat_color};margin-bottom:8px;display:inline-block'>{escape(maturity)}</span>"
            f"<p>{desc}</p>"
            f"<div class='ac-entry'>{_icon('bolt')} {escape(entry)}</div>"
            f"</div>"
        )

    accounts = (
        "<div class='acc-grid'>"
        + _acc("HDFC Bank", "BFSI", "Tier 1", "Advanced AI Adopter", "#5bd07f",
               "\"AI-first in 24 months\" goal. 15+ active GenAI programs. Dedicated AI Academy. RBI governance gap = BiltIQ's wedge.",
               "AI Governance layer for GenAI programs. Champion: CDO / Head of AI CoE.")
        + _acc("ICICI Bank", "BFSI", "Tier 1", "Advanced AI Adopter", "#5bd07f",
               "Heavy ML investment in credit scoring, fraud detection. iMobile Pay AI features. Needs explainable AI for RBI audits.",
               "Explainable AI for credit/fraud models. Champion: CTO / Head of Risk Technology.")
        + _acc("Apollo Hospitals", "Healthcare", "Tier 1", "Advanced AI Adopter", "#5bd07f",
               "Apollo.ai platform active. ABDM integration in progress. Patient data sovereignty critical.",
               "Sovereign clinical AI — patient data never leaves Apollo's network. Champion: CIO / CDHO.")
        + _acc("Manipal Health", "Healthcare", "Tier 1", "Growing Adoption", "#fbbf24",
               "Pan-India hospital network expanding digital. NHA compliance required. Less AI-mature = faster land.",
               "Clinical documentation AI (reduces physician burnout). Champion: CIO / VP Operations.")
        + _acc("Infosys", "IT Services", "Tier 2", "Advanced AI Adopter", "#5bd07f",
               "Topaz AI platform, aggressive AI practice. Serves regulated clients globally. Partnership = distribution multiplier.",
               "OEM/reseller: \"Infosys Topaz powered by BiltIQ sovereign engine.\" Access to 300+ regulated clients.")
        + _acc("Wipro", "IT Services", "Tier 2", "Advanced AI Adopter", "#5bd07f",
               "ai360 platform, strong BFSI vertical. Deep HDFC/ICICI relationships = warm introductions.",
               "Joint GTM for sovereign AI in BFSI. Wipro brings relationships; BiltIQ brings the engine.")
        + _acc("TCS", "IT Services", "Tier 2", "Advanced AI Adopter", "#5bd07f",
               "ignio AI platform. Government IT partner (Passport Seva, etc.). Unlocks public sector pipeline.",
               "Sovereign AI for government projects — TCS integrates; BiltIQ is the intelligence layer.")
        + _acc("IRCTC", "Government", "Tier 2", "Growing Adoption", "#fbbf24",
               "900M+ transactions/year. Customer service AI demand is massive. Data sovereignty non-negotiable.",
               "Passenger query + ops AI. Start with customer resolution; expand to revenue optimisation.")
        + _acc("AIIMS Delhi", "Healthcare / Gov", "Tier 3", "Early Stage", "#c084fc",
               "India's premier medical institution. Government procurement = slow but prestigious logo.",
               "Clinical research intelligence + ABDM integration. Academic pilot → national NHA rollout.")
        + _acc("MeitY", "Government", "Tier 3", "Growing Adoption", "#fbbf24",
               "India.AI Mission home. Owns IndiaAI compute infrastructure. Strategic for government channel.",
               "Sovereign AI for India.AI mission use cases. MeitY endorsement = credibility multiplier.")
        + "</div>"
    )
    s5_body = accounts

    # ── S6 90-Day GTM ──────────────────────────────────────────────────────────
    icp_rows = [
        ["<strong>Industry</strong>", "BFSI (private banks, NBFCs, insurers)", "Healthcare (chains &gt;500 beds)"],
        ["<strong>Size</strong>", "₹5,000Cr+ revenue, 5,000+ employees", "₹500Cr+ revenue, multi-city"],
        ["<strong>AI Maturity</strong>", "Active AI/GenAI programs, data team 20+", "CDO/CDAO appointed in last 2 years"],
        ["<strong>Regulatory</strong>", "RBI-regulated, IRDAI, or DPDP Significant Data Fiduciary", "ABDM-enrolled, NHA partner"],
        ["<strong>Pain State</strong>", "\"We're scaling GenAI but compliance is blocking us\"", "\"AI needed but patient data can't go to cloud\""],
        ["<strong>Champion</strong>", "CDO, Head of AI CoE, or CTO with compliance mandate", "CIO + CMO alignment needed"],
    ]

    def _tl(phase: str, days: str, title: str, items: list[str], dot: str = "") -> str:
        li = "".join(f"<li>{escape(i)}</li>" for i in items)
        return (
            f"<div class='tl-item'>"
            f"<div class='tl-left'>"
            f"<span class='tl-phase'>{escape(days)}</span>"
            f"<div class='tl-dot {dot}'></div>"
            f"</div>"
            f"<div class='tl-right'>"
            f"<span class='tl-phase'>{escape(phase)}</span>"
            f"<h4>{escape(title)}</h4>"
            f"<ul>{li}</ul>"
            f"</div>"
            f"</div>"
        )

    timeline = (
        "<div class='tl'>"
        + _tl("Foundation", "Days 1–15",
              "Build the Credibility Infrastructure",
              ["Publish DPDP Act + Enterprise AI whitepaper — gate with email capture",
               "Create 3 vertical-specific case study templates (BFSI, Healthcare, Government)",
               "Register for BFSI Technology Summit India and Healthcareinfo India",
               "Set up sales intelligence stack: LinkedIn Sales Navigator + Sentinel for account research",
               "Build RBI Circular explainer content for BFSI outreach"])
        + _tl("Outreach", "Days 15–45",
              "Activate Tier 1 Accounts + SI Partnerships",
              ["Warm outreach to HDFC Bank CDO — reference their AI-first 24-month announcement",
               "Apollo Hospitals CIO — reach via Healthcare IT Roundtable or Apollo.ai team",
               "Approach Wipro AI Practice with joint GTM proposal (engine + delivery)",
               "Submit to IndiaAI Mission sovereign AI vendor registry",
               "KPI: 10 discovery calls, 3 formal pilots scoped by Day 45"],
              "gold")
        + _tl("Pilots", "Days 45–90",
              "Run Pilots → Convert to Annual Contracts",
              ["Pilot design: 30-day focused use case (HDFC: AI governance trail; Apollo: clinical doc summarisation)",
               "Weekly pilot check-in with champion + steering committee member",
               "Day 60: success metrics review → present full platform proposal",
               "Target: 2 pilots live, 1 conversion to ₹80L+ annual contract",
               "Begin reference-able customer story (case study + testimonial)"],
              "green")
        + "</div>"
    )

    kpi_rows = [
        ["Discovery calls completed", "5", "15", "25"],
        ["Pilots scoped (SOW signed)", "1", "3", "5"],
        ["Pilots live (deployed)", "0", "2", "4"],
        ["Signed contracts / LOIs (ARR)", "₹0", "₹80L", "₹2.5Cr"],
        ["SI partnership agreements", "1 in discussion", "1 signed MOU", "1 active joint deal"],
        ["Whitepaper downloads", "50", "200", "500"],
    ]
    s6_body = (
        _rpt_callout(
            "GTM Philosophy",
            "<strong>Land &amp; Expand in regulated verticals.</strong> First sale is a governance/compliance "
            "pilot (low risk, fast procurement). Second sale is platform expansion (high ACV). "
            "Land with compliance, expand with intelligence.",
            "gold",
        )
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>Ideal Customer Profile</h3>"
        + _rpt_table(["Dimension", "Primary ICP", "Secondary ICP"], icp_rows)
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>90-Day Timeline</h3>"
        + timeline
        + "<h3 style='font-size:14px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)'>KPI Dashboard</h3>"
        + _rpt_table(["KPI", "Day 30", "Day 60", "Day 90"], kpi_rows)
    )

    # ── S7 Pricing ─────────────────────────────────────────────────────────────
    tiers = (
        "<div class='tier-grid'>"
        + (
            "<div class='tier-card'>"
            "<div class='tc-name'>Sovereign Starter</div>"
            "<div class='tc-price'>₹40L</div>"
            "<div class='tc-period'>per year · up to 50 users</div>"
            "<ul>"
            "<li>On-premise deployment (single site)</li>"
            "<li>1 agentic AI workflow</li>"
            "<li>Hybrid RAG knowledge base</li>"
            "<li>Standard compliance reporting</li>"
            "<li>Email support</li>"
            "</ul></div>"
        )
        + (
            "<div class='tier-card featured'>"
            "<div class='tc-name'>✦ Enterprise Core</div>"
            "<div class='tc-price'>₹1.2Cr</div>"
            "<div class='tc-period'>per year · unlimited users</div>"
            "<ul>"
            "<li>Multi-site deployment</li>"
            "<li>Unlimited agentic workflows</li>"
            "<li>Full sovereign RAG + memory stack</li>"
            "<li>RBI / IRDAI / DPDP audit reports</li>"
            "<li>Dedicated success manager</li>"
            "<li>Custom model fine-tuning (1/yr)</li>"
            "</ul></div>"
        )
        + (
            "<div class='tier-card'>"
            "<div class='tc-name'>National Sovereign</div>"
            "<div class='tc-price'>Custom</div>"
            "<div class='tc-period'>government / multi-entity</div>"
            "<ul>"
            "<li>Air-gapped deployment</li>"
            "<li>Multi-agency federation</li>"
            "<li>Full source code escrow</li>"
            "<li>IndiaAI mission alignment</li>"
            "<li>24×7 on-site SLA</li>"
            "<li>Unlimited fine-tuning</li>"
            "</ul></div>"
        )
        + "</div>"
    )
    s7_body = (
        tiers
        + _rpt_callout(
            "Pricing Reframe",
            "Lead with ROI, not price. A single DPDP compliance fine can be ₹250Cr. A single RBI audit "
            "failure costs ₹10–50Cr in remediation. Frame BiltIQ as "
            "<strong>\"₹1.2Cr/year to de-risk ₹50Cr+ in regulatory exposure.\"</strong>",
            "green",
        )
    )

    # ── S8 Risks ───────────────────────────────────────────────────────────────
    risk_rows = [
        ["Azure/Google launch India sovereign offering",
         "<span style='color:#ff6b6b'>High</span>", "<span style='color:#ff6b6b'>Critical</span>",
         "Accelerate lighthouse logo acquisition. Build BYOM + model customisation moat now."],
        ["Long BFSI procurement cycles (9+ months)",
         "<span style='color:#fbbf24'>Certain</span>", "<span style='color:#fbbf24'>High</span>",
         "Healthcare first (3–5 month cycles). Use healthcare ARR to bridge BFSI cycles."],
        ["Open-source model capability gap vs GPT-4",
         "<span style='color:#fbbf24'>Medium</span>", "<span style='color:#fbbf24'>High</span>",
         "Benchmark on regulated use cases (audit trail, policy Q&amp;A) where fine-tuned sovereign models excel."],
        ["Customer GPU/hardware readiness",
         "<span style='color:#fbbf24'>High</span>", "<span style='color:#5bd07f'>Medium</span>",
         "Partner with NxtGen/Sify for managed sovereign hosting. Offer Jetson Orin option for smaller deployments."],
        ["DPDP enforcement timeline slips",
         "<span style='color:#fbbf24'>Medium</span>", "<span style='color:#5bd07f'>Medium</span>",
         "Multi-regulation pitch (DPDP + RBI + IRDAI + NHA). Compliance is one of five value props — not the only one."],
    ]
    s8_body = _rpt_table(["Risk", "Probability", "Impact", "Mitigation"], risk_rows)

    # ── S9 Immediate Actions ───────────────────────────────────────────────────
    def _action(priority: str, p_cls: str, title: str, desc: str, owner: str, deadline: str) -> str:
        return (
            f"<div class='action-row'>"
            f"<div class='ar-p {p_cls}'>{escape(priority)}</div>"
            f"<div><h4>{escape(title)}</h4><p>{escape(desc)}</p></div>"
            f"<div class='ar-owner'>{escape(owner)}</div>"
            f"<div class='ar-deadline'>{escape(deadline)}</div>"
            f"</div>"
        )

    actions = (
        "<div class='action-grid'>"
        + _action("🔴 P0", "p0",
                  "Draft HDFC Bank outreach",
                  "Reference their 'AI-first in 24 months' announcement. Position BiltIQ as the RBI-compliant governance layer. Request 30-min discovery call with CDO office.",
                  "Founder / BD", "Day 3")
        + _action("🔴 P0", "p0",
                  "Publish DPDP + GenAI whitepaper",
                  "4-page PDF: 'Why DPDP 2023 Changes Everything for BFSI AI Adoption.' Gate on LinkedIn or direct outreach.",
                  "Founder + Marketing", "Day 7")
        + _action("🟠 P1", "p1",
                  "Contact Wipro AI Practice",
                  "Propose SI partnership. Wipro has HDFC/ICICI relationships. Pitch: 'We bring the sovereign engine; you bring delivery and relationships.'",
                  "BD Lead", "Day 10")
        + _action("🟠 P1", "p1",
                  "Register for BFSI Technology Summit",
                  "Speaking slot if possible. These are the exact events where CIOs and CDOs attend. Presence = credibility.",
                  "Marketing", "Day 7")
        + _action("🟡 P2", "p2",
                  "Build Apollo Hospitals case narrative",
                  "Develop a detailed 'how BiltIQ transforms Apollo's clinical AI' story. Use as sales collateral.",
                  "Product + BD", "Day 14")
        + _action("🟡 P2", "p2",
                  "Submit to IndiaAI Mission vendor registry",
                  "MeitY is awarding Sovereign AI contracts under India.AI mission. Being listed = multiplier for all government sales.",
                  "BD + Legal", "Day 21")
        + "</div>"
    )
    s9_body = (
        _rpt_callout("This Week (Next 7 Days)", "Execute P0 actions before anything else. "
                     "HDFC outreach and the DPDP whitepaper are the two highest-leverage items.", "gold")
        + actions
    )

    # ── Assemble page ──────────────────────────────────────────────────────────
    content = (
        cover
        + _rpt_section("01", "Executive Summary & Key Findings", s1_body)
        + _rpt_section("02", f"Company Profile: {project.name}", s2_body)
        + _rpt_section("03", "Market Opportunity: TAM / SAM / SOM", s3_body)
        + _rpt_section("04", "Competitive Landscape Analysis", s4_body)
        + _rpt_section("05", "Target Account Intelligence: Top 10", s5_body)
        + _rpt_section("06", "90-Day Go-To-Market Strategy", s6_body)
        + _rpt_section("07", "Pricing Architecture & Revenue Model", s7_body)
        + _rpt_section("08", "Risk Factors & Mitigation", s8_body)
        + _rpt_section("09", "Recommended Immediate Actions", s9_body)
    )

    return shell(
        active="projects",
        title=f"{project.name} · Report",
        content=content,
        backend=backend,
        subnav=subnav,
        project=project.name,
    )
