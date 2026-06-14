"""render.plan — split from render.py (presentation only)."""

from __future__ import annotations
import json
import re as _re
from html import escape

from .base import _badge, _icon, _project_subnav, shell
from .personas import _persona_label, _persona_tip

def _step_call_kind(capability: str) -> tuple[str, str]:
    """What the agent staffing this step actually *calls* — the public/private boundary made visible.
    Derived from the skill's tool steps (lazy import to keep render decoupled from the agent layer)."""
    from sentinel.agent.modes.spec import SKILL_SPECS

    spec = SKILL_SPECS.get(capability)
    if spec is None:
        return ("synth", "reasoner")                 # a created spec or aggregator: tool-free
    tools = {s.tool for s in spec.steps}
    if "private" in tools:
        return ("mcp", "MCP · private")
    if "search" in tools:
        return ("web", "web search · public")
    return ("synth", "reasoner")


def _calls_chip(capability: str) -> str:
    kind, label = _step_call_kind(capability)
    colour = {"web": "rgba(66,133,244,.14);color:var(--accent-2)",
              "mcp": "rgba(234,88,12,.16);color:#c2410c",
              "synth": "rgba(139,92,246,.16);color:#7c3aed"}[kind]
    return f"<span class='badge' style='background:{colour}'>{escape(label)}</span>"


def _plan_step_row(step) -> str:
    """One DAG step: id, capability, what it CALLS (web/MCP/reasoner — the boundary), deps, the agent
    it's assigned to, and whether that agent is REUSED (seed-*) or NEWLY created (created-*)."""
    reused = (step.agent_spec_id or "").startswith("seed-")
    tag = ("<span class='badge' style='background:rgba(66,133,244,.14);color:var(--accent-2)'>reuse</span>"
           if reused else
           "<span class='badge' style='background:rgba(234,179,8,.16);color:#b78a00'>new</span>")
    deps = ", ".join(escape(d) for d in step.depends_on) or "—"
    return (
        f"<tr><td><code>{escape(step.id)}</code></td><td><b>{escape(step.capability)}</b></td>"
        f"<td>{_calls_chip(step.capability)}</td>"
        f"<td>{deps}</td><td><code style='font-size:.85em'>{escape(step.agent_spec_id or '—')}</code></td>"
        f"<td>{tag}</td></tr>"
    )


def _dag_node(step) -> str:
    """One node in the visual DAG: capability + call boundary + assigned agent, coloured reuse/new."""
    reused = (step.agent_spec_id or "").startswith("seed-")
    border = "var(--accent-2)" if reused else "#b78a00"
    return (
        f"<div class='card' style='padding:10px 12px;border-left:3px solid {border};min-width:172px'>"
        f"<div style='font-size:11px;color:var(--muted)'>{escape(step.id)}</div>"
        f"<b>{escape(step.capability)}</b>"
        f"<div style='margin-top:6px'>{_calls_chip(step.capability)}</div>"
        f"<div style='margin-top:6px;font-size:11px;color:var(--muted);word-break:break-all'>"
        f"{escape(step.agent_spec_id or '—')}</div></div>"
    )


def _dag_graph(plan) -> str:
    """A left-to-right node-graph laid out by dependency depth: roots in the first column, their
    dependents in the next, arrows between columns. Conveys the task→agent flow at a glance (the table
    below keeps the precise depends-on detail)."""
    steps = plan.steps
    by_id = {s.id: s for s in steps}
    depth: dict[str, int] = {}

    def _d(sid: str, seen: tuple = ()) -> int:
        if sid in depth:
            return depth[sid]
        s = by_id.get(sid)
        deps = [p for p in (s.depends_on if s else []) if p in by_id and p not in seen]
        depth[sid] = (1 + max((_d(p, seen + (sid,)) for p in deps), default=-1)) if deps else 0
        return depth[sid]

    for s in steps:
        _d(s.id)
    cols: dict[int, list] = {}
    for s in steps:
        cols.setdefault(depth[s.id], []).append(s)
    columns = [
        "<div style='display:flex;flex-direction:column;gap:12px;justify-content:center'>"
        + "".join(_dag_node(s) for s in cols[lvl]) + "</div>"
        for lvl in sorted(cols)
    ]
    arrow = "<div style='align-self:center;color:var(--muted);font-size:22px'>&rarr;</div>"
    return ("<div class='section-h'><h2>Flow</h2></div>"
            "<div class='card' style='overflow-x:auto'>"
            "<div style='display:flex;gap:14px;align-items:stretch'>" + arrow.join(columns)
            + "</div></div>")


def _execution_log(trace: list[str]) -> str:
    """The run trace as a timeline: each line is a step's outcome (done / skipped / FAILED) — the
    'how the task ran on its agents' story, including fail-soft degradations, stated plainly."""
    if not trace:
        return ""
    rows = []
    for line in trace:
        low = line.lower()
        dot = ("#16a34a" if "done" in low or "cache hit" in low else
               "#dc2626" if "failed" in low else
               "#b78a00" if "skip" in low else "var(--muted)")
        rows.append(
            f"<li style='display:flex;gap:8px;align-items:baseline'>"
            f"<span style='color:{dot};flex:0 0 auto'>&#9679;</span>"
            f"<code style='font-size:.82em;white-space:pre-wrap'>{escape(line)}</code></li>")
    return ("<div class='section-h'><h2>Execution trace</h2></div>"
            "<div class='card'><ul class='find' style='list-style:none;padding-left:0'>"
            + "".join(rows) + "</ul></div>")


def _step_timeline(plan) -> str:
    """Post-run agent execution timeline.

    For each plan step, if the capability maps to a known ResearchModeSpec, we expand the
    sub-steps so users can see the full attack sequence: planner → search queries → synthesis.
    This is the primary transparency surface for non-technical users.
    """
    # Try to load the skill registry — fail-soft if unavailable
    try:
        from sentinel.agent.modes.spec import SKILL_SPECS
    except Exception:
        SKILL_SPECS = {}

    _SUBSTEP_LABELS: dict[str, tuple[str, str]] = {
        "planner":         ("🗺", "Planned search strategy — broke goal into targeted questions"),
        "public_research": ("🔍", "Searched web — Flipkart, Amazon India, review sites (91mobiles, Digit)"),
        "ecom_prices":     ("🛒", "Searched ecommerce — compared live prices across Flipkart & Amazon"),
        "research":        ("🔍", "Searched web — gathered public findings"),
        "synthesizer":     ("🧠", "Synthesised — assembled final structured output from all findings"),
        "extractor":       ("🔬", "Extracted facts — structured raw search results into typed data"),
        "dept_research":   ("🏛",  "Researched department/sector — mapped capabilities to requirements"),
        "synthesis":       ("🧠", "Synthesised proposal — compiled department findings into final plan"),
        "competitor":      ("🔍", "Researched competitor — web search for profile, products, pricing"),
        "compare":         ("⚖",  "Compared entities — side-by-side analysis of gathered profiles"),
        "self_profile":    ("🏢", "Profiled organisation — gathered public identity and product data"),
        "client":          ("👤", "Profiled client/account — gathered contact, deal, and context data"),
    }

    rows = []
    idx = 0
    for step in plan.steps:
        cap = step.capability or step.id
        plan_status = step.status  # top-level plan step status

        # Expand sub-steps from the skill spec so users see the full pipeline
        spec = SKILL_SPECS.get(cap)
        sub_steps = spec.steps if spec else []

        if sub_steps:
            # Render the skill label as a group header
            idx += 1
            rows.append(
                f"<div style='padding:8px 0 4px;border-bottom:1px solid var(--border)'>"
                f"<div style='display:flex;gap:8px;align-items:center'>"
                f"<span style='color:var(--accent-2);font-weight:700;font-size:13px'>#{idx}</span>"
                f"<span style='font-weight:600;font-size:13px'>{escape(cap)}</span>"
                f"<span class='tag' style='color:#5bd07f;font-size:11px'>skill pipeline</span>"
                f"</div></div>"
            )
            for ss in sub_steps:
                sub_key = ss.agent_key.split(".")[-1] if "." in ss.agent_key else ss.agent_key
                icon, label = _SUBSTEP_LABELS.get(sub_key, ("⚙", f"{escape(sub_key)} step"))
                rows.append(
                    f"<div style='display:flex;gap:10px;align-items:flex-start;"
                    f"padding:6px 0 6px 20px;border-bottom:1px solid var(--border)'>"
                    f"<div style='font-size:15px;flex:0 0 auto'>{icon}</div>"
                    f"<div style='flex:1'>"
                    f"<div style='font-size:12px;font-weight:600'>{escape(sub_key)}</div>"
                    f"<div style='font-size:11px;color:var(--text-secondary);margin-top:1px'>{label}</div>"
                    f"</div>"
                    f"<span style='font-size:13px'>✅</span>"
                    f"</div>"
                )
        else:
            # Fallback: show plan step directly
            idx += 1
            label_key = cap if cap in _SUBSTEP_LABELS else (
                step.id.split(".")[-1] if "." in step.id else cap)
            icon, label = _SUBSTEP_LABELS.get(label_key, ("⚙", f"Ran {escape(cap)} step"))
            status_icon = ("✅" if plan_status == "done"
                           else "❌" if plan_status == "failed" else "⏳")
            rows.append(
                f"<div style='display:flex;gap:10px;align-items:flex-start;padding:8px 0;"
                f"border-bottom:1px solid var(--border)'>"
                f"<span style='color:var(--accent-2);font-weight:700;font-size:12px;"
                f"flex:0 0 24px'>#{idx}</span>"
                f"<div style='font-size:15px;flex:0 0 auto'>{icon}</div>"
                f"<div style='flex:1'>"
                f"<div style='font-weight:600;font-size:13px'>{escape(cap)}</div>"
                f"<div style='font-size:12px;color:var(--text-secondary);margin-top:2px'>{label}</div>"
                f"<div style='margin-top:4px'>{_calls_chip(cap)}</div>"
                f"</div>"
                f"<span style='font-size:15px'>{status_icon}</span>"
                f"</div>"
            )

    return (
        "<div style='margin-top:16px'>"
        "<div style='font-weight:600;font-size:13px;margin-bottom:8px;color:var(--text-secondary)'>"
        "How the agent worked</div>"
        "<div style='background:var(--surface-2);border-radius:10px;padding:4px 12px'>"
        + ("".join(rows) if rows else
           "<div class='note' style='padding:8px 0'>No step details available.</div>")
        + "</div></div>"
    )


def _provenance_bar(public: int, private: int) -> str:
    """A compact public/private split — the signature provenance view (boundary made visible)."""
    total = public + private
    if total == 0:
        return "<span class='pill'>no cited sources</span>"
    pub_pct = round(100 * public / total)
    return (
        "<div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap'>"
        f"<span class='pill'>Public <b>{public}</b></span>"
        f"<span class='pill'>Private <b>{private}</b></span>"
        "<span style='flex:1 1 160px;height:10px;border-radius:6px;overflow:hidden;"
        "display:flex;min-width:120px;border:1px solid var(--line)'>"
        f"<span style='width:{pub_pct}%;background:var(--accent-2)'></span>"
        f"<span style='width:{100-pub_pct}%;background:#c2410c'></span></span></div>"
    )


def _created_spec_card(spec) -> str:
    bounds = ", ".join(b.value for b in spec.boundaries)
    return (
        "<div class='card' style='padding:10px 12px'>"
        f"<div style='display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap'>"
        f"<b>{escape(spec.name)}</b><span class='badge'>{escape(spec.role)}</span></div>"
        f"<div style='margin-top:6px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span class='pill'>capability: <b>{escape(spec.capability)}</b></span>"
        f"<span class='pill'>schema: <b>{escape(spec.output_schema_ref)}</b></span>"
        f"<span class='pill'>boundaries: <b>{escape(bounds)}</b></span>"
        f"<span class='pill'>tools: <b>{escape(', '.join(spec.tools) or 'none')}</b></span></div></div>"
    )


def _verdict_badge(v: str) -> str:
    c = {"win": "rgba(22,163,74,.16);color:#16a34a", "lose": "rgba(220,38,38,.16);color:#dc2626",
         "parity": "rgba(234,179,8,.16);color:#b78a00"}.get(v, "transparent;color:var(--muted)")
    return f"<span class='badge' style='background:{c}'>{escape(v or '—')}</span>"


def _prio_badge(p: str) -> str:
    c = {"high": "rgba(220,38,38,.16);color:#dc2626", "med": "rgba(234,179,8,.16);color:#b78a00",
         "low": "transparent;color:var(--muted)"}.get(p, "transparent;color:var(--muted)")
    return f"<span class='badge' style='background:{c}'>{escape(p or '—')}</span>"


def _art_wrap(title: str, body: str) -> str:
    return (f"<div class='card'><div class='section-h' style='margin-top:0'><h3>{escape(title)}</h3></div>"
            f"{body}</div>")


def _findings_block(title: str, items: list) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{escape(_clean_text(f.get('text', '') if isinstance(f, dict) else str(f)))}</li>" for f in items)
    return f"<div style='margin-top:8px'><b>{escape(title)}</b><ul class='find'>{lis}</ul></div>"


def _clean_text(s: str) -> str:
    """Decode literal \\uXXXX sequences that LLMs sometimes emit in text fields."""
    if not s:
        return ""
    import re as _ure
    return _ure.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)


def _text_paras(s: str) -> str:
    """Render a long text field as HTML paragraphs with unicode + newline cleanup."""
    s = _clean_text(s or "")
    parts = [p.strip() for p in s.replace("\\n", "\n").split("\n\n") if p.strip()]
    if not parts:
        return ""
    if len(parts) == 1:
        return f"<div class='note' style='white-space:pre-wrap'>{escape(parts[0])}</div>"
    return "".join(f"<p class='note' style='margin:4px 0 6px'>{escape(p)}</p>" for p in parts)


# Leading discriminator field of each domain brief (the field its render branch keys on).
# Their presence means the artifact is a specific brief, NOT the generic ProgramStrategy
# aggregator — used to stop ProgramStrategy greedily shadowing a brief that also carries
# action_plan + assessment.
_DOMAIN_BRIEF_DISCRIMINATORS = frozenset({
    "tech_stack",            # SoftwareBrief
    "topic_overview",        # AcademicBrief
    "financial_summary",     # FinancialProfile
    "evidence_quality",      # NutritionBrief
    "destination_overview",  # TravelBrief
})


def _artifact_html(key: str, art) -> str:
    """Render a produced artifact as readable HTML (cards/tables/badges) by recognising its shape —
    not a raw JSON dump. Falls back to pretty JSON only for an unknown shape."""
    if not isinstance(art, dict):
        return _art_wrap(key, f"<pre style='white-space:pre-wrap'>{escape(str(art))}</pre>")

    if "products" in art and "org" in art:                       # SelfProfile
        prods = "".join(
            f"<div class='card' style='padding:10px 12px'><b>{escape(p.get('name', ''))}</b>"
            f"<span class='pill' style='margin-left:8px'>{escape(p.get('category', ''))}</span>"
            f"<div class='note' style='margin-top:6px'>{escape(p.get('positioning', ''))}</div>"
            + ("<div style='margin-top:6px;display:flex;gap:6px;flex-wrap:wrap'>"
               + "".join(f"<span class='pill'>{escape(s)}</span>" for s in p.get('strengths', []))
               + "</div>" if p.get('strengths') else "")
            + "</div>" for p in art.get("products", []))
        body = (f"<div style='margin-bottom:8px'>Organisation: <b>{escape(art.get('org', ''))}</b></div>"
                + (f"<div style='display:grid;gap:8px'>{prods}</div>" if prods
                   else "<div class='empty'>No products extracted (research was thin).</div>"))
        return _art_wrap("Self profile", body)

    if "axes" in art and "subject" in art:                       # ComparisonMatrix
        rows = "".join(
            f"<tr><td><b>{escape(a.get('axis', ''))}</b></td><td>{escape(a.get('ours', ''))}</td>"
            f"<td>{escape(a.get('theirs', ''))}</td><td>{_verdict_badge(a.get('verdict', ''))}</td></tr>"
            for a in art.get("axes", []))
        head = f"<b>{escape(art.get('subject', ''))}</b> vs <b>{escape(art.get('rival', ''))}</b>"
        body = head + (f"<table style='margin-top:8px'><thead><tr><th>Axis</th><th>Ours</th>"
                       f"<th>Theirs</th><th>Verdict</th></tr></thead><tbody>{rows}</tbody></table>"
                       if rows else "<div class='empty'>No comparison axes produced.</div>")
        return _art_wrap("Comparison matrix", body)

    if "tech_stack" in art and "community_health" in art:        # SoftwareBrief (must precede ProgramStrategy — shares action_plan+assessment)
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + (f"<div style='margin:6px 0'><span class='pill'>category: "
                   f"<b>{escape(art.get('category', '') or '—')}</b></span>"
                   + (f"<span class='pill' style='margin-left:6px'>pricing: "
                      f"<b>{escape(', '.join(art.get('pricing_model', [{}])[0].get('text', '—')[:40] if art.get('pricing_model') else ['—']))}</b></span>"
                      if art.get("pricing_model") else "")
                   + "</div>")
                + _findings_block("Tech stack", art.get("tech_stack", []))
                + _findings_block("API quality / DX", art.get("api_quality", []))
                + _findings_block("Community health", art.get("community_health", []))
                + _findings_block("Maintenance activity", art.get("maintenance_activity", []))
                + _findings_block("Integration support", art.get("integration_support", []))
                + (f"<div style='margin-top:8px'><b>Alternatives</b>"
                   f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-top:4px'>"
                   + "".join(f"<span class='pill'>{escape(a)}</span>" for a in art.get("alternatives", []))
                   + "</div></div>" if art.get("alternatives") else "")
                + (f"<div class='note' style='margin-top:8px'>{escape(art.get('assessment', ''))}</div>"
                   if art.get("assessment") else ""))
        return _art_wrap(f"Software brief — {escape(art.get('target', '') or key)}", body)

    # ProgramStrategy is the GENERIC program-level aggregator — its only fields (assessment,
    # action_plan, ran_on_partial_data) are a SUBSET of every domain brief, so it must never
    # shadow one. Require the absence of each brief's leading discriminator field; without this
    # guard a brief whose LLM emitted both action_plan AND assessment mis-renders as a
    # "Market-capture strategy" (regression 2026-06-12, found by the doc-grounded e2e matrix).
    if ("action_plan" in art and "assessment" in art
            and "products_found" not in art and "department_mappings" not in art
            and not any(d in art for d in _DOMAIN_BRIEF_DISCRIMINATORS)):  # ProgramStrategy
        def _action_row(a):
            if isinstance(a, dict):
                return (f"<tr><td>{_prio_badge(a.get('priority', ''))}</td>"
                        f"<td><b>{escape(a.get('action', ''))}</b>"
                        f"<div class='note'>{escape(a.get('rationale', ''))}</div></td>"
                        f"<td>{escape(a.get('timeline', ''))}</td></tr>")
            return f"<tr><td></td><td>{escape(str(a))}</td><td></td></tr>"
        rows = "".join(_action_row(a) for a in art.get("action_plan", []))
        body = (f"<div class='note'>{escape(art.get('assessment', ''))}</div>"
                + (f"<table style='margin-top:8px'><thead><tr><th>Priority</th><th>Action</th>"
                   f"<th>Timeline</th></tr></thead><tbody>{rows}</tbody></table>" if rows else ""))
        return _art_wrap("Market-capture strategy", body)

    if "financial_summary" in art and "key_metrics" in art:      # FinancialProfile
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + f"<div class='note' style='margin-top:6px'>{escape(art.get('financial_summary', ''))}</div>"
                + _findings_block("Key metrics", art.get("key_metrics", []))
                + _findings_block("Market position", art.get("market_position", []))
                + _findings_block("Risk signals", art.get("risk_signals", []))
                + _findings_block("Recent developments", art.get("recent_developments", []))
                + (f"<div class='note' style='margin-top:8px'><b>Investment thesis:</b> "
                   f"{escape(art.get('investment_thesis', ''))}</div>"
                   if art.get("investment_thesis") else "")
                + (f"<div class='note' style='margin-top:6px'>{escape(art.get('assessment', ''))}</div>"
                   if art.get("assessment") else ""))
        return _art_wrap(f"Financial profile — {escape(art.get('target', '') or key)}", body)

    if "topic_overview" in art and "key_findings" in art:        # AcademicBrief
        researchers = art.get("notable_researchers", [])
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + f"<div class='note' style='margin-top:6px'>{escape(art.get('topic_overview', ''))}</div>"
                + _findings_block("Key findings", art.get("key_findings", []))
                + _findings_block("Research gaps", art.get("research_gaps", []))
                + (f"<div style='margin-top:8px'><b>Notable researchers</b>"
                   f"<div style='display:flex;gap:6px;flex-wrap:wrap;margin-top:4px'>"
                   + "".join(f"<span class='pill'>{escape(r)}</span>" for r in researchers)
                   + "</div></div>" if researchers else "")
                + _findings_block("Methodology notes", [{"text": m} for m in art.get("methodology_notes", [])]))
        return _art_wrap(f"Academic brief — {escape(art.get('topic', '') or key)}", body)

    if "evidence_quality" in art and "key_claims" in art:        # NutritionBrief
        disclaimer = art.get("disclaimer", "")
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + f"<div style='margin:6px 0'><span class='pill'>evidence: "
                f"<b>{escape(art.get('evidence_quality', '') or '—')}</b></span></div>"
                + _findings_block("Key claims", art.get("key_claims", []))
                + _findings_block("Practical guidance",
                                  [{"text": g} for g in art.get("practical_guidance", [])])
                + _findings_block("Contraindications",
                                  [{"text": c} for c in art.get("contraindications", [])])
                + (f"<div class='note' style='margin-top:8px;font-size:.8em;opacity:.7'>"
                   f"{escape(disclaimer)}</div>" if disclaimer else ""))
        return _art_wrap(f"Nutrition brief — {escape(art.get('topic', '') or key)}", body)

    if "destination_overview" in art and "highlights" in art:    # TravelBrief
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + f"<div class='note' style='margin-top:6px'>{escape(art.get('destination_overview', ''))}</div>"
                + (f"<div style='margin:6px 0;display:flex;gap:6px;flex-wrap:wrap'>"
                   + (f"<span class='pill'>best time: <b>{escape(art.get('best_time', ''))}</b></span>"
                      if art.get("best_time") else "")
                   + (f"<span class='pill'>budget: <b>{escape(art.get('budget_range', ''))}</b></span>"
                      if art.get("budget_range") else "")
                   + "</div>")
                + _findings_block("Highlights", art.get("highlights", []))
                + _findings_block("Practical info", art.get("practical_info", []))
                + _findings_block("Safety notes", art.get("safety_notes", [])))
        return _art_wrap(f"Travel brief — {escape(art.get('destination', '') or key)}", body)

    if "department_mappings" in art and "executive_summary" in art:              # GovernmentProposal
        dept_maps = [dm for dm in (art.get("department_mappings") or []) if isinstance(dm, dict)]

        # Derive client_challenges from dept_mappings when model left them blank
        client_challenges = art.get("client_challenges") or []
        if not client_challenges and dept_maps:
            client_challenges = [
                {"text": f"{dm.get('department', 'Dept')}: {dm.get('challenge', '')}"}
                for dm in dept_maps if dm.get("challenge")
            ]

        # Derive vendor_capabilities from dept_mappings solutions when blank
        vendor_capabilities = art.get("vendor_capabilities") or []
        if not vendor_capabilities and dept_maps:
            vendor_capabilities = [
                {"text": f"{dm.get('department', 'Dept')}: {dm.get('solution', '')} → {dm.get('impact', '')}"}
                for dm in dept_maps if dm.get("solution")
            ]

        def _dept_row(dm):
            if not isinstance(dm, dict):
                return ""
            impact = dm.get("impact", "")
            impact_cell = (f"<span style='color:#5bd07f'>{escape(impact)}</span>"
                           if impact else "—")
            return (f"<tr>"
                    f"<td><b>{escape(dm.get('department', ''))}</b></td>"
                    f"<td>{escape(dm.get('challenge', ''))}</td>"
                    f"<td style='color:var(--accent-2)'>{escape(dm.get('solution', ''))}</td>"
                    f"<td>{impact_cell}</td>"
                    f"</tr>")

        dept_rows = "".join(_dept_row(dm) for dm in dept_maps)
        body = (
            f"<div class='note'>{escape(_clean_text(art.get('one_line_summary', '')))}</div>"
            + f"<div style='margin:8px 0 4px;display:flex;gap:8px;flex-wrap:wrap'>"
              f"<span class='pill'>🏛 Client: <b>{escape(art.get('client', ''))}</b></span>"
              f"<span class='pill'>🏢 Vendor: <b>{escape(art.get('vendor', ''))}</b></span>"
              f"<span class='pill' style='color:#5bd07f'>✓ {len(dept_maps)} departments mapped</span>"
              f"</div>"
            + (f"<div class='card' style='margin:8px 0;padding:12px 14px'>"
               f"<div style='font-weight:600;margin-bottom:6px'>📄 Executive Summary</div>"
               + _text_paras(art.get("executive_summary", ""))
               + "</div>" if art.get("executive_summary") else "")
            + (f"<div style='margin-top:14px'>"
               f"<div style='font-weight:600;margin-bottom:8px'>Department Mappings — Challenge → Solution → Impact</div>"
               f"<div style='overflow-x:auto'>"
               f"<table style='margin-top:4px;min-width:700px'><thead><tr>"
               f"<th>Department</th><th>Challenge</th><th>AI Solution</th><th>Expected Impact</th>"
               f"</tr></thead><tbody>{dept_rows}</tbody></table></div></div>"
               if dept_rows else "")
            + _findings_block("Client challenges", client_challenges)
            + _findings_block("Vendor capabilities", vendor_capabilities)
            + (f"<div class='card' style='margin-top:10px;padding:12px 14px;"
               f"border-left:3px solid var(--accent-2)'>"
               f"<div style='font-weight:600;margin-bottom:6px'>🏆 Competitive Advantage</div>"
               + _text_paras(art.get("competitive_advantage", ""))
               + "</div>" if art.get("competitive_advantage") else "")
            + (f"<div class='card' style='margin-top:10px;padding:12px 14px;"
               f"border-left:3px solid #5bd07f'>"
               f"<div style='font-weight:600;margin-bottom:6px'>🗓 90-Day Pilot Plan</div>"
               + _text_paras(art.get("pilot_plan", ""))
               + "</div>" if art.get("pilot_plan") else "")
        )
        return _art_wrap(f"Government proposal — {escape(art.get('client', '') or key)}", body)

    if "products_found" in art and "winner_rationale" in art:                    # ProductResearch
        def _prod_row(p):
            if not isinstance(p, dict):
                return ""
            score = p.get("score", "")
            # Score may be "9.2/10" or 9.2 — normalise to float for sorting
            try:
                score_f = float(str(score).split("/")[0])
            except (ValueError, TypeError):
                score_f = 0.0
            score_str = f"{score}" if score else "—"
            pros = "; ".join(p.get("pros", [])) if p.get("pros") else "—"
            cons = "; ".join(p.get("cons", [])) if p.get("cons") else "—"
            src = p.get("source_url", "")
            name_cell = (f"<a href='{escape(src)}' rel='noopener' target='_blank' "
                         f"style='color:var(--accent-2)'>{escape(p.get('name', ''))}</a>"
                         if src else escape(p.get("name", "")))
            return (score_f, f"<tr>"
                    f"<td><b>{name_cell}</b><br><span style='opacity:.7;font-size:.85em'>"
                    f"{escape(p.get('brand', ''))}</span></td>"
                    f"<td style='white-space:nowrap'>{escape(str(p.get('price', '—')))}</td>"
                    f"<td style='font-size:.85em'>{escape(p.get('processor', '—'))}</td>"
                    f"<td style='white-space:nowrap'>{escape(str(p.get('ram', '—')))} / "
                    f"{escape(str(p.get('storage', '—')))}</td>"
                    f"<td style='text-align:center'><b>{escape(score_str)}</b></td>"
                    f"<td style='font-size:.82em'><span style='color:#16a34a'>{escape(pros)}</span></td>"
                    f"<td style='font-size:.82em'><span style='color:#dc2626'>{escape(cons)}</span></td>"
                    f"</tr>")
        products = [p for p in art.get("products_found", []) if isinstance(p, dict)]
        # Sort by score descending so highest-scored product is first
        scored = sorted([_prod_row(p) for p in products], key=lambda x: x[0], reverse=True)
        prod_rows = "".join(r for _, r in scored)
        winner = art.get("winner", "")
        winner_rationale = art.get("winner_rationale", "")
        # Derive winner from highest-scored product when model left it blank
        if not winner and products:
            best = max(products, key=lambda p: (
                float(str(p.get("score", 0)).split("/")[0]) if p.get("score") else 0
            ), default=None)
            if best:
                winner = best.get("name", "")
                score_val = best.get("score", "")
                pros_list = best.get("pros") or []
                winner_rationale = (winner_rationale or
                    f"Highest overall score ({score_val}). " +
                    (f"Key strengths: {pros_list[0]}" if pros_list else ""))
        value_ranking = art.get("value_ranking", [])
        body = (
            f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
            + (f"<div style='margin:6px 0'><span class='pill'>Criteria: "
               f"<b>{escape(art.get('criteria', '—'))}</b></span></div>"
               if art.get("criteria") else "")
            + (f"<div class='card' style='margin:8px 0;padding:10px 12px;"
               f"border-left:4px solid #16a34a'>"
               f"<b>🏆 Winner: {escape(winner)}</b>"
               f"<div class='note' style='margin-top:6px'>{escape(winner_rationale)}</div>"
               f"</div>" if winner else "")
            + (f"<div style='margin-top:12px'><b>All qualifying products</b>"
               f"<div style='overflow-x:auto'>"
               f"<table style='margin-top:6px;min-width:700px'><thead><tr>"
               f"<th>Product</th><th>Price</th><th>Processor</th><th>RAM/Storage</th>"
               f"<th>Score</th><th>Pros</th><th>Cons</th>"
               f"</tr></thead><tbody>{prod_rows}</tbody></table></div></div>"
               if prod_rows else "<div class='empty'>No qualifying products found.</div>")
            + (f"<div style='margin-top:10px'><b>Value ranking</b>"
               f"<ol style='margin:4px 0 0 18px;padding:0'>"
               + "".join(f"<li>{escape(v)}</li>" for v in value_ranking)
               + f"</ol></div>" if value_ranking else "")
            + (f"<div class='note' style='margin-top:8px'>{escape(art.get('assessment', ''))}</div>"
               if art.get("assessment") else "")
        )
        return _art_wrap(f"Product research — {escape(art.get('criteria', '') or key)}", body)

    if "one_line_summary" in art or ("strengths" in art and "weaknesses" in art):   # Battlecard
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + _findings_block("Strengths", art.get("strengths", []))
                + _findings_block("Weaknesses", art.get("weaknesses", []))
                + _findings_block("Pricing signals", art.get("pricing_signals", []))
                + _findings_block("Recent developments", art.get("recent_developments", [])))
        return _art_wrap(f"Battlecard — {escape(art.get('target', '') or key)}", body)

    # DeptResearchOutput — per-department findings block from govt_proposal parallel steps
    if "department" in art and "findings" in art and "gaps" in art:
        dept_name = (_clean_text(art.get("department", ""))
                     or key.replace("research_dept_", "").replace("_", " ").title())
        sources = [s for s in (art.get("sources") or []) if s and isinstance(s, str)]
        gaps = [g for g in (art.get("gaps") or []) if g and isinstance(g, str)]
        body = (
            _text_paras(art.get("findings", ""))
            + (f"<div style='margin-top:10px;display:flex;gap:6px;flex-wrap:wrap'>"
               + "".join(
                   f"<span class='pill' style='font-size:11px'>📎 {escape(_clean_text(s)[:80])}</span>"
                   for s in sources[:6])
               + "</div>" if sources else "")
            + (f"<details style='margin-top:8px'>"
               f"<summary style='font-size:12px;cursor:pointer;color:var(--muted);"
               f"user-select:none'>Research gaps ({len(gaps)})</summary>"
               f"<ul class='find' style='margin-top:4px'>"
               + "".join(f"<li style='color:var(--muted);font-size:12px'>"
                         f"{escape(_clean_text(g))}</li>" for g in gaps)
               + "</ul></details>" if gaps else "")
        )
        return _art_wrap(f"🏛 {dept_name}", body)

    # Generic unknown shape — pretty JSON (last resort, should rarely fire)
    return _art_wrap(key, "<pre style='white-space:pre-wrap;overflow:auto;font-size:.82em'>"
                     f"{escape(json.dumps(art, indent=2, default=str))}</pre>")


_FIND_UL_RE = _re.compile(r"<ul class='find'>.*?</ul>", _re.DOTALL)


def _findings_to_table(html: str) -> str:
    """Convert every <ul class='find'>…</ul> block to a compact <table> — preferred_format='table'."""
    def _ul_to_table(m: _re.Match) -> str:
        items = _re.findall(r"<li>(.*?)</li>", m.group(0), _re.DOTALL)
        if not items:
            return m.group(0)
        rows = "".join(f"<tr><td style='padding:3px 6px;border-bottom:1px solid var(--border)'>"
                       f"{item}</td></tr>" for item in items)
        return (f"<table style='width:100%;border-collapse:collapse;margin-top:4px'>"
                f"<tbody>{rows}</tbody></table>")
    return _FIND_UL_RE.sub(_ul_to_table, html)


def _findings_to_prose(html: str) -> str:
    """Convert every <ul class='find'>…</ul> block to a paragraph — preferred_format='prose'."""
    def _ul_to_p(m: _re.Match) -> str:
        items = _re.findall(r"<li>(.*?)</li>", m.group(0), _re.DOTALL)
        if not items:
            return m.group(0)
        return f"<p class='note' style='margin-top:4px'>{' '.join(items)}</p>"
    return _FIND_UL_RE.sub(_ul_to_p, html)


def _result_card(result, *, task_id: str = "", project_id: str = "") -> str:
    """Render an orchestrated Result inline (the deliverable): summary + honesty flags, each produced
    artifact, the cited sources by boundary, and any persona-adapted prose / model grade. This is what
    makes 'the run produced something' visible instead of a dead link."""
    deg = ("<span class='badge' style='background:rgba(234,179,8,.16);color:#b78a00'>partial</span>"
           if result.degraded else
           "<span class='badge' style='background:rgba(22,163,74,.16);color:#16a34a'>complete</span>")
    pub = sum(1 for c in result.citations if getattr(c.boundary, "value", c.boundary) == "public")
    prv = len(result.citations) - pub
    if task_id and project_id:
        _exp = f"/projects/{project_id}/tasks/{task_id}/export.html"
        export_btns = (
            "<div style='display:flex;gap:8px;margin-top:10px'>"
            f"<button class='btn ghost' style='font-size:12px;padding:4px 12px' "
            f"onclick=\"var w=window.open('{_exp}','_blank');"
            f"w.addEventListener('load',function(){{w.print();}})\">"
            "⬇ Export PDF</button>"
            f"<a class='btn ghost' href='{_exp}' download style='font-size:12px;padding:4px 12px'>"
            "⬇ Export HTML</a>"
            "</div>"
        )
    else:
        export_btns = ""
    head = (f"<div class='card'><div class='section-h' style='margin-top:0'><h2>Result</h2>{deg}</div>"
            f"<div class='note' style='margin:6px 0 10px'>{escape(result.summary)}</div>"
            f"{_provenance_bar(pub, prv)}{export_btns}</div>")

    arts = (result.dashboard_payload or {}).get("artifacts", {}) or {}
    _fmt = getattr(result, "preferred_format", None) or "bullets"
    if arts:
        raw_html = "".join(_artifact_html(key, art) for key, art in arts.items())
        if _fmt == "table":
            raw_html = _findings_to_table(raw_html)
        elif _fmt == "prose":
            raw_html = _findings_to_prose(raw_html)
        arts_html = (
            "<details open style='margin-top:8px'>"
            "<summary style='font-weight:700;font-size:14px;padding:6px 0 4px;"
            "cursor:pointer;user-select:none'>Deliverables</summary>"
            f"<div id='sentinel-deliverables' style='display:grid;gap:10px;margin-top:6px;"
            f"max-height:520px;overflow-y:auto;padding-right:4px'>{raw_html}</div>"
            "</details>"
        )
    else:
        arts_html = ("<div class='section-h'><h2>Artifacts</h2></div>"
                     "<div class='card'><div class='empty'>No artifact content produced (the run "
                     "degraded — see the missing steps above).</div></div>")

    # Build citation list: primary = result.citations (model-produced);
    # fallback = mine URL-bearing sub-fields from artifact data (for runs where
    # the 26B model left sources:[] empty but did fill e.g. products_found[].source_url)
    _cite_list = list(result.citations or [])
    if not _cite_list:
        _seen_urls: set[str] = set()
        for _art in arts.values():
            if not isinstance(_art, dict):
                continue
            # ProductResearch: per-product source_url
            for p in (_art.get("products_found") or []):
                if isinstance(p, dict):
                    url = (p.get("source_url") or "").strip()
                    if url.startswith("http") and url not in _seen_urls:
                        _seen_urls.add(url)
                        _cite_list.append(type("_S", (), {
                            "boundary": "public",
                            "label": f"{p.get('name','Product')} — {p.get('brand','')}".strip(" —"),
                            "url": url,
                        })())
            # GovernmentProposal: dept_mappings don't carry URLs, but check action_plan
            for a in (_art.get("action_plan") or []):
                if isinstance(a, dict):
                    url = (a.get("url") or a.get("source_url") or "").strip()
                    if url.startswith("http") and url not in _seen_urls:
                        _seen_urls.add(url)
                        _cite_list.append(type("_S", (), {
                            "boundary": "public",
                            "label": a.get("action", "Reference"),
                            "url": url,
                        })())

    if _cite_list:
        cites = "".join(
            f"<li>{_badge(c.boundary)}{escape(c.label or '—')}"
            + (f" · <a href='{escape(c.url)}' rel='noopener' target='_blank' "
               f"style='color:var(--accent-2)'>{escape(c.url)}</a>" if c.url else "")
            + "</li>" for c in _cite_list)
        cites_html = (
            f"<details style='margin-top:8px'>"
            f"<summary style='font-weight:700;font-size:14px;padding:6px 0 4px;"
            f"cursor:pointer;user-select:none'>Citations ({len(_cite_list)})</summary>"
            f"<div class='card' style='margin-top:6px'><ul class='find'>{cites}</ul></div>"
            f"</details>"
        )
    else:
        cites_html = ""

    extra = ""
    _pr = getattr(result, "persona_rendered", None) or ""
    _pr_broken = (not _pr or "<<" in _pr or ">>" in _pr
                  or _pr.lower().startswith("please provide")
                  or _pr.lower().startswith("i will adapt")
                  or _pr.lower().startswith("once you provide")
                  or "established findings" in _pr.lower())
    if _pr and not _pr_broken:
        extra += ("<div class='section-h'><h2>Persona view</h2></div>"
                  f"<div class='card'><div class='note'>{escape(_pr)}</div></div>")
    if getattr(result, "grade", None) is not None:
        g = result.grade
        verdict = "pass" if getattr(g, "passed", False) else "review"
        extra += ("<div class='section-h'><h2>Quality grade</h2></div>"
                  f"<div class='card'><span class='pill'>score: <b>{getattr(g,'score',0):.2f}</b></span> "
                  f"<span class='badge'>{escape(verdict)}</span></div>")

    return (head + "<div style='margin-top:16px'></div>" + arts_html
            + "<div style='margin-top:16px'></div>" + cites_html + extra)


def _feedback_bar(task) -> str:
    """Thumbs-up / thumbs-down feedback widget for a completed task result.

    Posts to /projects/{pid}/tasks/{tid}/feedback via fetch (no page reload).
    XSS-safe: task ids are escaped; user-facing labels are literals.
    The widget disables both buttons once a signal is recorded so it can't be
    double-submitted — no server-side dedup needed.
    """
    pid = escape(str(task.project_id))
    tid = escape(str(task.id))
    url = f"/projects/{pid}/tasks/{tid}/feedback"
    # Inline JS: DOM-only, no innerHTML, validated form data. The fetch uses a
    # URLSearchParams body so CSRF surface matches any other same-origin POST.
    js = (
        "async function sendFb(sig){"
        f"var r=await fetch('{url}',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},"
        "body:new URLSearchParams({signal:sig})});"
        "var d=await r.json();"
        "if(d.ok){"
        "document.getElementById('fb-up').disabled=true;"
        "document.getElementById('fb-dn').disabled=true;"
        "document.getElementById('fb-msg').textContent='Feedback saved — thank you';}}"
    )
    return (
        f"<script>{js}</script>"
        "<div class='card' style='display:flex;align-items:center;gap:12px;padding:10px 14px'>"
        "<span style='font-size:13px;color:var(--text-2)'>Was this result useful?</span>"
        "<button id='fb-up' class='btn ghost' onclick='sendFb(1)' style='padding:4px 12px'>"
        "&#128077; Helpful</button>"
        "<button id='fb-dn' class='btn ghost' onclick='sendFb(-1)' style='padding:4px 12px'>"
        "&#128078; Not useful</button>"
        "<span id='fb-msg' style='font-size:12px;color:var(--text-2)'></span>"
        "</div>"
    )


def _task_context_pill(task) -> str:
    """Render a pill showing the task's research context, or empty string if none set."""
    ctx = getattr(task, "context", None) or ""
    if not ctx:
        return ""
    short = ctx[:60] + ("…" if len(ctx) > 60 else "")
    return (
        f"<span class='pill' title='{escape(ctx)}' "
        "style='max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>"
        f"context: <b>{escape(short)}</b></span>"
    )


def _chat_panel(task) -> str:
    """Conversational refinement panel — shown after a task has run (Claude.ai-style follow-up).

    Renders the persisted chat history plus a JS-powered input that posts to
    /projects/{pid}/tasks/{tid}/chat without a full page reload.
    """
    pid = escape(getattr(task, "project_id", "") or "")
    tid = escape(task.id)
    history = list(getattr(task, "chat", []) or [])

    msgs_html = ""
    for msg in history:
        role = str(msg.get("role", "user"))
        content = escape(str(msg.get("content", "")))
        align = "flex-end" if role == "user" else "flex-start"
        bg = "var(--accent-line)" if role == "user" else "var(--card)"
        border = "2px solid var(--accent-2)" if role == "user" else "1px solid var(--line)"
        label = "You" if role == "user" else "Sentinel"
        msgs_html += (
            f"<div style='display:flex;justify-content:{align};margin-bottom:10px'>"
            f"<div style='max-width:80%;padding:10px 14px;border-radius:10px;"
            f"background:{bg};border:{border};font-size:13px'>"
            f"<div style='font-size:11px;color:var(--muted);margin-bottom:4px'>{label}</div>"
            f"<div style='white-space:pre-wrap'>{content}</div></div></div>"
        )

    chat_js = f"""
<script>
(function(){{
  var form = document.getElementById('sentinel-chat-form-{tid}');
  var msgs = document.getElementById('sentinel-chat-msgs-{tid}');
  var input = document.getElementById('sentinel-chat-input-{tid}');
  var btn = document.getElementById('sentinel-chat-btn-{tid}');
  if (!form) return;
  form.addEventListener('submit', function(e) {{
    e.preventDefault();
    var msg = input.value.trim();
    if (!msg) return;
    btn.disabled = true; btn.textContent = 'Thinking…';
    var userDiv = document.createElement('div');
    userDiv.style.cssText = 'display:flex;justify-content:flex-end;margin-bottom:10px';
    userDiv.innerHTML = '<div style="max-width:80%;padding:10px 14px;border-radius:10px;background:var(--accent-line);border:2px solid var(--accent-2);font-size:13px"><div style="font-size:11px;color:var(--muted);margin-bottom:4px">You</div><div style="white-space:pre-wrap">' + msg.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></div>';
    msgs.appendChild(userDiv);
    msgs.scrollTop = msgs.scrollHeight;
    input.value = '';
    var fd = new FormData();
    fd.append('message', msg);
    fetch('/projects/{pid}/tasks/{tid}/chat', {{method:'POST', body:fd}})
      .then(function(r){{ return r.json(); }})
      .then(function(d){{
        btn.disabled = false; btn.textContent = 'Send';
        var reply = d.reply || d.error || '(no reply)';
        var botDiv = document.createElement('div');
        botDiv.style.cssText = 'display:flex;justify-content:flex-start;margin-bottom:10px';
        botDiv.innerHTML = '<div style="max-width:80%;padding:10px 14px;border-radius:10px;background:var(--card);border:1px solid var(--line);font-size:13px"><div style="font-size:11px;color:var(--muted);margin-bottom:4px">Sentinel</div><div style="white-space:pre-wrap">' + reply.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></div>';
        msgs.appendChild(botDiv);
        msgs.scrollTop = msgs.scrollHeight;
      }})
      .catch(function(err){{ btn.disabled=false; btn.textContent='Send'; console.error(err); }});
  }});
}})();
</script>"""

    empty_note = "" if history else (
        "<div class='empty' style='text-align:center;padding:20px 0'>Ask a question about these findings, request a deeper dive on any section, or ask for next steps.</div>"
    )
    return (
        "<div id='sentinel-chat-section' style='margin-top:16px'></div>"
        "<div class='section-h'><h2>Refine &amp; Ask</h2>"
        "<span class='badge' style='background:rgba(66,133,244,.12);color:var(--accent-2)'>AI chat on results</span></div>"
        "<div class='card' style='padding:0;overflow:hidden'>"
        f"<div id='sentinel-chat-msgs-{tid}' style='padding:16px;max-height:360px;overflow-y:auto;min-height:80px'>"
        f"{empty_note}{msgs_html}</div>"
        "<div style='border-top:1px solid var(--line);padding:12px 16px'>"
        f"<form id='sentinel-chat-form-{tid}' style='display:flex;gap:8px'>"
        f"<input id='sentinel-chat-input-{tid}' type='text' style='flex:1;background:var(--rail);"
        "border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:inherit;font-size:13px' "
        "placeholder='Ask about the findings, request follow-up research, explore next steps…'>"
        f"<button id='sentinel-chat-btn-{tid}' type='submit' class='btn' style='padding:8px 18px'>Send</button>"
        "</form></div></div>"
        + chat_js
    )


def task_running_page(*, task, plan, backend: str, step_models: dict[str, str] | None = None) -> str:
    """Live run view (replaces the blocking popup overlay): a per-step timeline that polls
    ``status.json`` every 2s, spins the in-flight step(s), ticks completed ones, and reloads
    into the persisted Result when the run lands. The page is the loader — no popup.

    ``step_models`` (step id → model label, from app's ``_step_models``) feeds the active-agent
    banner: which agent is working, on which model, with an animated hand-over when one agent
    passes the baton to the next."""
    pid, tid = escape(task.project_id), escape(task.id)
    obj = escape(task.objective[:110] + ("…" if len(task.objective) > 110 else ""))
    models = step_models or {}

    rows = ""
    for s in plan.steps:
        status = s.status if s.status != "pending" else ("running" if s.started_at else "pending")
        model = models.get(s.id, "")
        model_html = f" · <span class='tl-model'>{escape(model)}</span>" if model else ""
        rows += (
            f"<div class='tl-step' data-step='{escape(s.id)}' data-status='{escape(status)}'>"
            f"<div class='tl-dot'></div>"
            f"<div><div class='tl-cap'>{escape(s.capability)}</div>"
            f"<div class='tl-meta mono'>{escape(s.id)} · agent {escape(s.agent_spec_id or '—')}"
            f"{model_html}</div></div>"
            f"<div class='tl-state'>{escape(status)}</div></div>"
        )

    content = (
        # timeline styles — dot states drive the whole visual (pending ring / running spinner /
        # done tick / failed cross), so the poller only flips data-status.
        "<style>"
        ".tl-step{display:grid;grid-template-columns:28px 1fr auto;gap:12px;align-items:center;"
        "padding:13px 6px;border-bottom:1px solid var(--line);position:relative}"
        ".tl-step:last-child{border-bottom:0}"
        ".tl-step:not(:last-child):before{content:'';position:absolute;left:19px;top:40px;bottom:-14px;"
        "width:2px;background:var(--line)}"
        ".tl-dot{width:26px;height:26px;border-radius:50%;border:2px solid var(--line);"
        "display:flex;align-items:center;justify-content:center;font-size:13px;background:var(--panel-2)}"
        "@keyframes tlspin{to{transform:rotate(360deg)}}"
        "[data-status=running] .tl-dot{border-color:transparent;border-top-color:#4285f4;"
        "border-right-color:#4285f4;animation:tlspin .8s linear infinite}"
        "[data-status=running] .tl-state{color:#8ab4f8}"
        "[data-status=done] .tl-dot,[data-status=cached] .tl-dot{border-color:#34a853;color:#34a853}"
        "[data-status=done] .tl-dot:after,[data-status=cached] .tl-dot:after{content:'✓'}"
        "[data-status=done] .tl-state,[data-status=cached] .tl-state{color:#5bd07f}"
        "[data-status=failed] .tl-dot{border-color:#ea4335;color:#ea4335}"
        "[data-status=failed] .tl-dot:after{content:'✕'}"
        "[data-status=failed] .tl-state{color:#ff6b6b}"
        "[data-status=skipped] .tl-state{color:var(--muted)}"
        ".tl-cap{font-weight:600;font-size:14px}"
        ".tl-meta{font-size:11.5px;color:var(--muted);margin-top:2px}"
        ".tl-model{color:#8ab4f8}"
        ".tl-state{font-size:11.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}"
        "@keyframes tlpulse{0%,100%{opacity:1}50%{opacity:.45}}"
        # active-agent banner: who's working, on which model — slides in on every hand-over.
        ".tl-agentbar{display:flex;align-items:center;gap:14px;margin-top:14px}"
        ".tl-bot{font-size:26px;animation:tlpulse 2s ease-in-out infinite}"
        "@keyframes tlslide{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:none}}"
        "#tl-agent{font-weight:600;font-size:14.5px}"
        "#tl-agent.swap,#tl-amodel.swap{animation:tlslide .45s ease}"
        "#tl-amodel{font-size:12px;color:#8ab4f8;margin-top:2px}"
        # hand-over flash: "agent A → agent B", fades itself out.
        "@keyframes tlhand{0%{opacity:0;transform:translateX(-8px)}12%{opacity:1;transform:none}"
        "78%{opacity:1}100%{opacity:0}}"
        "#tl-handover{margin-left:auto;font-size:12px;color:var(--muted);opacity:0;"
        "white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46%}"
        "#tl-handover.show{animation:tlhand 3.2s ease forwards}"
        "</style>"
        # header
        "<div class='card'><div class='section-h' style='margin-top:0'>"
        "<h2 style='animation:tlpulse 2s ease-in-out infinite'>Agents running…</h2>"
        f"<span class='badge' id='tl-count'>0/{len(plan.steps)} steps</span></div>"
        f"<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span class='pill' title='{escape(task.objective)}'>objective: <b>{obj}</b></span>"
        f"<span class='pill'>domain: <b>{escape(task.domain.name)}</b></span></div>"
        "<div class='note' style='margin-top:10px'>The plan is executing on the engine — each step "
        "ticks as its agent finishes. This page refreshes itself; the result replaces it when the "
        "run lands.</div></div>"
        # active-agent banner — the poller swaps in whoever is working + their model, and flashes
        # the hand-over ("agent A → agent B") whenever the baton passes.
        "<div class='card tl-agentbar'><span class='tl-bot'>🤖</span>"
        "<div><div id='tl-agent'>Warming up the engine…</div>"
        "<div id='tl-amodel' class='mono'></div></div>"
        "<span id='tl-handover' class='mono'></span></div>"
        # the timeline
        f"<div class='card' style='margin-top:14px'>{rows}</div>"
        # poller
        "<script>(function(){"
        f"var URL='/projects/{pid}/tasks/{tid}/status.json';"
        "var done=['done','cached','failed','skipped'];var cur=null,curAgent=null;"
        "function swap(el,txt){if(!el)return;el.classList.remove('swap');void el.offsetWidth;"
        "el.textContent=txt;el.classList.add('swap');}"
        "function tick(){fetch(URL).then(function(r){return r.json()}).then(function(d){"
        "if(d.state!=='running'){location.reload();return}"
        "var n=0,run=null;(d.steps||[]).forEach(function(s){"
        "var el=document.querySelector('[data-step=\"'+s.id+'\"]');"
        "if(el){el.dataset.status=s.status;var st=el.querySelector('.tl-state');"
        "if(st)st.textContent=s.status;}"
        "if(done.indexOf(s.status)>-1)n++;"
        "if(s.status==='running'&&!run)run=s;});"
        "var c=document.getElementById('tl-count');"
        "if(c)c.textContent=n+'/'+(d.steps||[]).length+' steps';"
        # hand-over: the running step changed → animate the banner + flash "prev → next".
        "if(run&&run.id!==cur){"
        "swap(document.getElementById('tl-agent'),(run.agent||run.id)+' is working\\u2026');"
        "swap(document.getElementById('tl-amodel'),run.model||'');"
        "if(curAgent){var h=document.getElementById('tl-handover');"
        "if(h){h.textContent=curAgent+' \\u2192 '+(run.agent||run.id);"
        "h.classList.remove('show');void h.offsetWidth;h.classList.add('show');}}"
        "cur=run.id;curAgent=run.agent||run.id;}"
        "setTimeout(tick,2000);}).catch(function(){setTimeout(tick,4000)});}"
        "setTimeout(tick,2000);})();</script>"
    )
    return shell(active="projects", title="Running…", content=content, backend=backend,
                 subnav=_project_subnav(task.project_id, "tasks"))


def plan_review_page(*, task, proposal, autonomy: str, backend: str, ran: bool = False,
                     result=None, trace: list[str] | None = None,
                     selected_backend: str = "", kb_sources: list | None = None) -> str:
    """The plan-review screen (SENTINEL-012 Step 16, AC-13): the proposed DAG + each step's assigned
    agent and what it calls (web/MCP), any new agents to create, the explicit run/approval control, and
    — once run — the execution trace + the typed/cited/persona-adapted Result. In ``propose`` mode a
    banner states plainly that **nothing has executed** and the human must approve."""
    plan = proposal.plan
    created = proposal.created_specs

    banner = (
        "<div class='card' style='border-left:3px solid var(--accent-2)'>"
        "<b>Proposed — nothing has run.</b> Review the plan, the assigned agents and what they call "
        "below, then approve to execute. (Autonomy: <b>propose</b>, the safe default.)</div>"
        if not ran and autonomy == "propose" else
        "<div class='card' style='border-left:3px solid #16a34a'><b>Run complete.</b> "
        "The plan executed on the two-pass sovereign engine; the cited result is below.</div>"
        if ran else
        "<div class='card'><b>Plan ready.</b></div>"
    )

    be_label = selected_backend or backend
    be_pill = (
        f"<span class='pill'><span class='dotmark {'v' if be_label == 'vllm' else 'g'}'></span>"
        f"backend: <b>{escape(be_label)}</b></span>"
        if be_label else ""
    )
    header = (
        "<div class='card'><div class='section-h' style='margin-top:0'><h2>Plan review</h2>"
        f"<span class='badge'>autonomy: {escape(autonomy)}</span></div>"
        f"<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span class='pill' title='{escape(task.objective)}'>objective: <b>{escape(task.objective[:72] + ('…' if len(task.objective) > 72 else ''))}</b></span>"
        f"<span class='pill'>domain: <b>{escape(task.domain.name)}</b></span>"
        f"<span class='pill' title='{escape(_persona_tip(task.persona))}'>persona: "
        f"<b>{_persona_label(task.persona)}</b></span>"
        f"<span class='pill'>steps: <b>{len(plan.steps)}</b></span>"
        f"<span class='pill'>new agents: <b>{len(created)}</b></span>"
        f"{be_pill}"
        + _task_context_pill(task)
        + "</div></div>"
    )

    # ── KB context panel ─────────────────────────────────────────────────────
    kb_panel = ""
    _sources = kb_sources or []
    if _sources:
        _STATUS_STYLE = {
            "indexed":  ("var(--good,#16a34a)", "✓ indexed"),
            "pending":  ("var(--warn,#ca8a04)", "⏳ indexing…"),
            "crawling": ("var(--warn,#ca8a04)", "⏳ crawling…"),
            "failed":   ("var(--bad,#dc2626)",  "✗ failed"),
        }
        _any_loading = any(s.get("status") in ("pending", "crawling") for s in _sources)
        _auto_reload = (
            "<script>setTimeout(function(){location.reload()},6000)</script>"
            if _any_loading and not ran else ""
        )
        _rows = ""
        for _s in _sources:
            _status = _s.get("status", "pending")
            _color, _label = _STATUS_STYLE.get(_status, ("var(--fg-2)", _status))
            _url_disp = (_s.get("url") or "")[:64]
            _type_pill = f"<span class='pill' style='font-size:11px'>{escape(_s.get('source_type','web'))}</span>"
            _chunks = _s.get("chunk_count") or 0
            _chunk_note = f" · {_chunks} chunks" if _chunks else ""
            _rows += (
                f"<tr>"
                f"<td>{_type_pill}</td>"
                f"<td style='font-size:12px;font-family:var(--mono);color:var(--fg-2)'>{escape(_url_disp)}</td>"
                f"<td style='color:{_color};font-weight:500;white-space:nowrap'>{_label}{_chunk_note}</td>"
                f"</tr>"
            )
        _loading_note = (
            "<p class='note' style='margin:6px 0 0'>KB crawls running in background — "
            "page auto-refreshes every 6 s until complete.</p>" if _any_loading else ""
        )
        kb_panel = (
            "<div class='section-h' style='margin-top:0'>"
            "<h2>KB context</h2>"
            "<span class='badge' style='background:rgba(66,133,244,.12);color:var(--accent-2)'>"
            f"{len(_sources)} source(s)</span></div>"
            "<div class='card' style='padding:6px 8px;margin-bottom:0'>"
            "<table><tbody>" + _rows + "</tbody></table>"
            + _loading_note + "</div>"
            + _auto_reload
        )

    graph_html = _dag_graph(plan)
    rows = "".join(_plan_step_row(s) for s in plan.steps)
    dag_html = (
        graph_html + "<div style='margin-top:16px'></div>"
        "<div class='section-h'><h2>Step DAG — task → assigned agents</h2></div>"
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>Step</th><th>Capability</th><th>Calls</th><th>Depends on</th>"
        "<th>Assigned agent</th><th></th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )

    if created:
        cards = "".join(_created_spec_card(s) for s in created)
        created_html = (
            "<div class='section-h'><h2>Proposed new agents</h2></div>"
            "<div style='display:grid;gap:10px'>" + cards + "</div>"
        )
    else:
        created_html = (
            "<div class='section-h'><h2>Proposed new agents</h2></div>"
            "<div class='card'><div class='empty'>None — every step reuses an existing specialist."
            "</div></div>"
        )

    proj_id = getattr(task, "project_id", "") or ""

    if not ran:
        # ── Pre-run: show full plan for approval ──────────────────────────────
        be_hidden = (f"<input type='hidden' name='backend' value='{escape(selected_backend)}'>"
                     if selected_backend else "")
        approve_btn = (
            f"<form method='post' action='/projects/{escape(task.project_id)}/tasks/{escape(task.id)}/run' "
            "style='margin-top:16px'>"
            f"{be_hidden}"
            "<button class='btn' type='submit'>" + _icon("bolt") + " Approve &amp; run</button></form>"
        )
        kb_block = ("<div style='margin-top:16px'></div>" + kb_panel) if kb_panel else ""
        content = (banner + "<div style='margin-top:16px'></div>" + header
                   + kb_block
                   + "<div style='margin-top:16px'></div>" + dag_html
                   + "<div style='margin-top:16px'></div>" + created_html + approve_btn)
        return shell(active="projects", title="Plan review", content=content, backend=backend,
                     subnav=_project_subnav(proj_id, "tasks") if proj_id else "")

    # ── Post-run: result-first layout ─────────────────────────────────────────
    _obj_short = escape(task.objective[:80] + ("…" if len(task.objective) > 80 else ""))
    deg_badge = (
        "<span class='badge' style='background:rgba(234,179,8,.16);color:#d4a017'>partial</span>"
        if (result and getattr(result, "degraded", False)) else
        "<span class='badge' style='background:rgba(22,163,74,.16);color:#16a34a'>complete</span>"
    )
    status_bar = (
        f"<div class='card' style='margin-bottom:12px'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px'>"
        f"<div>"
        f"<div style='font-weight:700;font-size:15px;margin-bottom:6px'>{_obj_short}</div>"
        f"<div style='display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span class='pill'>domain: <b>{escape(task.domain.name)}</b></span>"
        f"<span class='pill' title='{escape(_persona_tip(task.persona))}'>persona: "
        f"<b>{_persona_label(task.persona)}</b></span>"
        f"{be_pill}{deg_badge}"
        + _task_context_pill(task)
        + f"</div></div>"
        f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap'>"
        f"<a class='btn ghost' href='/projects/{escape(proj_id)}' style='font-size:12px'>← Project</a>"
        f"<a class='btn ghost' href='/projects/{escape(proj_id)}/artifacts' style='font-size:12px'>Artifacts</a>"
        f"<a class='btn' href='#sentinel-chat-section' style='font-size:12px'>💬 Ask AI</a>"
        f"<a class='btn ghost' href='/projects/{escape(proj_id)}/tasks/{escape(task.id)}/export.html' "
        f"style='font-size:12px'>📄 Download Report</a>"
        f"</div></div></div>"
    )

    result_html = _result_card(result, task_id=task.id, project_id=proj_id) if result else ""
    fb_html = ("<div style='margin-top:10px'></div>" + _feedback_bar(task)) if result else ""
    chat_html = _chat_panel(task) if result else ""
    exec_html = ("<div style='margin-top:16px'></div>" + _execution_log(trace)) if trace else ""

    # Step timeline — visible immediately so users can see what the agent did
    timeline_html = _step_timeline(plan)

    # Full DAG behind a toggle (for debugging / power users)
    plan_toggle = (
        "<div style='margin-top:16px'>"
        "<button type='button' class='btn ghost' style='font-size:12px' "
        "onclick=\"var p=document.getElementById('plan-detail-panel');"
        "p.style.display=p.style.display==='none'?'block':'none'\">▸ View full plan &amp; agent assignments</button>"
        "<div id='plan-detail-panel' style='display:none;margin-top:12px'>"
        + dag_html + "</div></div>"
    )

    _details_style = ("style='font-weight:700;font-size:14px;padding:6px 0 4px;"
                      "cursor:pointer;user-select:none'")
    kb_post = (
        "<details style='margin-top:12px'>"
        f"<summary {_details_style}>KB context used</summary>"
        "<div style='margin-top:6px'>" + kb_panel + "</div></details>"
    ) if kb_panel else ""
    timeline_details = (
        "<details style='margin-top:12px'>"
        f"<summary {_details_style}>Agent timeline</summary>"
        "<div style='margin-top:6px'>" + timeline_html + "</div></details>"
    )
    content = (status_bar + result_html + fb_html + chat_html
               + timeline_details + kb_post + exec_html + plan_toggle)
    return shell(active="projects", title=task.objective[:60], content=content, backend=backend,
                 subnav=_project_subnav(proj_id, "tasks") if proj_id else "")
