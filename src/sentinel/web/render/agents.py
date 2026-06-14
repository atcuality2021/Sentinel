"""render.agents — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .base import _icon, shell

# --------------------------------------------------------------------------- #
# Agents — the live agent roster + pipeline flow graph (Google Agent Platform style).
# The data is introspected from the real specs + config in app.py and passed in, so this
# page documents exactly what would run, including the dark (flagged-off) stages.
# --------------------------------------------------------------------------- #
_NODE_ICON = {
    "planner": "plan", "public_research": "globe", "private_research": "lock",
    "extractor": "merge", "synthesizer": "doc", "strategist": "spark",
}
_CHEVRON = (
    "<svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
    "stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'><path d='M9 6l6 6-6 6'/></svg>"
)


def _flow_node(n: dict) -> str:
    kindcls = {"tool": "", "reason": "reason", "private": "private"}.get(n["kind"], "")
    dark = " dark" if n["dark"] else ""
    ico = _NODE_ICON.get(n["role"], "agent")
    flag = (f"<div class='n-meta'><span class='pv dark'>{escape(n['flag'])} · off</span></div>"
            if n["dark"] and n.get("flag") else "")
    return (
        f"<div class='node {kindcls}{dark}'><div class='n-top'>"
        f"<span class='n-ico'>{_icon(ico)}</span>"
        f"<div><div class='n-name'>{escape(n['name'])}</div>"
        f"<div class='n-role'>{escape(n['role'])}</div></div></div>"
        f"<div class='n-meta'>{escape(n['tier'])}</div>"
        f"<div class='n-meta'>{escape(n['desc'])}</div>"
        f"<div class='n-out'>→ {escape(n['out'])}</div>{flag}</div>"
    )


_ROLE_COLOR = {
    "planner":          "#4285f4",
    "public_research":  "#34a853",
    "private_research": "#ea8600",
    "extractor":        "#fa7b17",
    "synthesizer":      "#c08cf7",
    "strategist":       "#e8453c",
    "coordinator":      "#00bcd4",
}
_ALL_ROLES = [
    "planner", "public_research", "private_research",
    "extractor", "synthesizer", "strategist", "coordinator",
]


def _agent_card(key: str, ac, *, is_default: bool) -> str:
    """One agent card with inline edit form."""
    role  = getattr(ac, "role", "synthesizer")
    model = getattr(ac, "model", None) or "—"
    enabled = getattr(ac, "enabled", True)
    color = _ROLE_COLOR.get(role, "#9aa0a6")
    gen   = getattr(ac, "generation", None)

    status_dot = (
        "<span style='color:#34a853;font-size:10px'>●</span> on"
        if enabled else
        "<span style='color:#ea4335;font-size:10px'>●</span> off"
    )
    role_badge = (
        f"<span style='background:{color};color:#fff;padding:2px 8px;"
        f"border-radius:10px;font-size:11px;font-weight:600'>{escape(role)}</span>"
    )

    role_opts = "".join(
        f"<option value='{r}'{' selected' if r == role else ''}>{r}</option>"
        for r in _ALL_ROLES
    )
    temp_val = str(gen.temperature) if gen and gen.temperature is not None else ""
    tok_val  = str(gen.max_output_tokens) if gen and gen.max_output_tokens is not None else ""

    delete_btn = "" if is_default else (
        f"<form method='post' action='/agents/{escape(key)}/delete' style='display:inline' "
        f"onsubmit=\"return confirm('Delete agent ' + {escape(json.dumps(key), quote=True)} + '?')\">"
        f"<button class='btn-sm warn' type='submit'>Delete</button></form>"
    )

    edit_form = (
        f"<form method='post' action='/agents/{escape(key)}' style='margin-top:12px'>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>"
        f"<div><label class='lbl'>Model override</label>"
        f"<input name='model' value='{escape(model if model != '—' else '')}' "
        f"placeholder='leave blank = backend default' style='font-size:12px'></div>"
        f"<div><label class='lbl'>Role</label>"
        f"<select name='role' style='font-size:12px'>{role_opts}</select></div>"
        f"<div><label class='lbl'>Temperature</label>"
        f"<input name='temperature' value='{escape(temp_val)}' placeholder='e.g. 0.7' style='font-size:12px'></div>"
        f"<div><label class='lbl'>Max tokens</label>"
        f"<input name='max_output_tokens' value='{escape(tok_val)}' placeholder='e.g. 4096' style='font-size:12px'></div>"
        f"</div>"
        f"<div style='margin-top:8px;display:flex;gap:8px;align-items:center'>"
        f"<label style='font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer'>"
        f"<input type='checkbox' name='enabled' value='1'{' checked' if enabled else ''}> Enabled</label>"
        f"<label style='font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer'>"
        f"<input type='checkbox' name='pin_gemini' value='1'{' checked' if getattr(ac,'pin_gemini',False) else ''}> Pin Gemini</label>"
        f"<button class='btn-sm' type='submit' style='margin-left:auto'>Save</button>"
        f"{delete_btn}"
        f"</div></form>"
    )

    return (
        f"<div class='card' style='padding:14px 16px'>"
        f"<div style='display:flex;align-items:flex-start;justify-content:space-between'>"
        f"<div>"
        f"<div style='font-family:monospace;font-weight:700;font-size:14px;margin-bottom:6px'>"
        f"{escape(key)}</div>"
        f"<div style='display:flex;gap:6px;align-items:center;flex-wrap:wrap'>"
        f"{role_badge}"
        f"<span class='pv' style='font-size:11px'>{escape(model)}</span>"
        f"<span style='font-size:11px;color:var(--muted)'>{status_dot}</span>"
        f"</div></div>"
        f"<details style='width:100%'><summary style='cursor:pointer;font-size:12px;"
        f"color:var(--accent-2);margin-top:8px;list-style:none'>Edit ›</summary>"
        f"{edit_form}</details>"
        f"</div></div>"
    )


def _agent_row(key: str, ac, *, is_default: bool) -> str:
    """Compact table row + expandable inline edit form for one agent."""
    role    = getattr(ac, "role", "synthesizer")
    model   = getattr(ac, "model", None) or ""
    enabled = getattr(ac, "enabled", True)
    gen     = getattr(ac, "generation", None)
    color   = _ROLE_COLOR.get(role, "#9aa0a6")
    suffix  = key.split(".", 1)[-1] if "." in key else key
    uid     = key.replace(".", "-").replace("_", "-")

    role_badge = (
        f"<span style='background:{color};color:#fff;padding:1px 8px;"
        f"border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap'>"
        f"{escape(role)}</span>"
    )
    dot = ("<span style='color:#34a853;font-size:9px'>●</span>"
           if enabled else "<span style='color:#ea4335;font-size:9px'>●</span>")

    role_opts = "".join(
        f"<option value='{r}'{' selected' if r == role else ''}>{r}</option>"
        for r in _ALL_ROLES
    )
    temp_val = str(gen.temperature) if gen and gen.temperature is not None else ""
    tok_val  = str(gen.max_output_tokens) if gen and gen.max_output_tokens is not None else ""

    # Flat model dropdown — backend is implicit in the model choice
    _ALL_MODELS = [
        ("", "default (from Settings)"),
        ("gemini-2.5-flash",      "Gemini · 2.5 Flash"),
        ("gemini-2.0-flash-lite", "Gemini · 2.0 Flash Lite"),
        ("gemma-4-12b-it",        "vLLM · Gemma 12B (Tools)"),
        ("gemma-4-27b-it",        "vLLM · Gemma 26B (Reasoning)"),
    ]
    model_opts = "".join(
        f"<option value='{m}'{' selected' if m == model else ''}>{label}</option>"
        for m, label in _ALL_MODELS
    )

    # Row model label
    _MODEL_LABELS = {m: label for m, label in _ALL_MODELS if m}
    if model in _MODEL_LABELS:
        model_label = _MODEL_LABELS[model]
    elif model:
        model_label = escape(model)
    else:
        model_label = "<span style='color:var(--muted)'>default</span>"

    delete_btn = "" if is_default else (
        f"<form method='post' action='/agents/{escape(key)}/delete' style='display:inline;margin-left:6px' "
        f"onsubmit=\"return confirm('Delete agent ' + {escape(json.dumps(key), quote=True)} + '?')\">"
        f"<button class='btn-sm warn' type='submit' style='font-size:11px'>Delete</button></form>"
    )

    edit_form = (
        f"<div id='edit-{uid}' style='display:none;background:var(--surface2);"
        f"padding:12px 16px;border-top:1px solid var(--line)'>"
        f"<form method='post' action='/agents/{escape(key)}'>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;align-items:end'>"
        # Model dropdown
        f"<div><label class='lbl' style='font-size:11px'>Model</label>"
        f"<select name='model' style='font-size:12px'>{model_opts}</select></div>"
        # Role
        f"<div><label class='lbl' style='font-size:11px'>Role</label>"
        f"<select name='role' style='font-size:12px'>{role_opts}</select></div>"
        # Temperature
        f"<div><label class='lbl' style='font-size:11px'>Temperature</label>"
        f"<input name='temperature' value='{escape(temp_val)}' placeholder='0.7' style='font-size:12px'></div>"
        # Max tokens
        f"<div><label class='lbl' style='font-size:11px'>Max tokens</label>"
        f"<input name='max_output_tokens' value='{escape(tok_val)}' placeholder='4096' style='font-size:12px'></div>"
        f"</div>"
        # Row 2: enabled + save + delete
        f"<div style='display:flex;gap:12px;align-items:center;margin-top:8px'>"
        f"<label style='font-size:12px;cursor:pointer'>"
        f"<input type='checkbox' name='enabled' value='1'{' checked' if enabled else ''}> Enabled</label>"
        f"<button class='btn-sm' type='submit' style='margin-left:auto;font-size:12px'>Save</button>"
        f"{delete_btn}"
        f"</div></form></div>"
    )

    row = (
        f"<div style='display:grid;grid-template-columns:2fr 1fr 1fr 60px;"
        f"align-items:center;padding:8px 16px;border-bottom:1px solid var(--line);gap:8px'>"
        f"<span style='font-family:monospace;font-size:13px'>{escape(suffix)}</span>"
        f"{role_badge}"
        f"<span style='font-size:12px'>{model_label}</span>"
        f"<div style='display:flex;align-items:center;gap:6px;justify-content:flex-end'>"
        f"{dot}"
        f"<button type='button' onclick=\"var d=document.getElementById('edit-{uid}');"
        f"d.style.display=d.style.display==='none'?'block':'none'\""
        f" style='background:none;border:none;color:var(--accent-2);font-size:12px;"
        f"cursor:pointer;padding:2px 6px'>Edit</button>"
        f"</div></div>"
        f"{edit_form}"
    )
    return row


def agents_page(*, modes: list[dict], flags: dict, backend: str,
                agents_cfg: dict | None = None, ok: str = "", err: str = "") -> str:
    """Agents page: grouped accordion tables + CRUD + collapsible pipeline view."""
    agents_cfg = agents_cfg or {}

    banner = ""
    if ok:
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner err' style='margin-bottom:16px'>{escape(err)}</div>"

    # ── flag chips ───────────────────────────────────────────────────────────
    def chip(label: str, on: bool, warn: bool = False) -> str:
        c = ("#ea8600" if warn else "#34a853") if on else "#9aa0a6"
        return (f"<span style='background:{c}22;color:{c};border:1px solid {c}44;"
                f"padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600'>"
                f"{escape(label)}: {'on' if on else 'off'}</span>")

    flagline = (
        "<div style='display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px'>"
        + chip("two-tier extractor", flags.get("two_tier", False))
        + chip("strategy overlay", flags.get("strategy", False))
        + chip("coordinator", flags.get("coordinator", False))
        + chip("private boundary", flags.get("private", False), warn=True)
        + "</div>"
    )

    # ── create form ──────────────────────────────────────────────────────────
    role_opts_new = "".join(f"<option value='{r}'>{r}</option>" for r in _ALL_ROLES)
    create_form = (
        "<details style='margin-bottom:16px'>"
        "<summary style='cursor:pointer;font-size:13px;font-weight:600;"
        "color:var(--accent-2);padding:9px 14px;background:var(--surface2);"
        "border-radius:8px;list-style:none;user-select:none'>＋ Add custom agent</summary>"
        "<div class='card' style='margin-top:4px;padding:14px 16px;border-top:none;border-radius:0 0 8px 8px'>"
        "<form method='post' action='/agents'>"
        "<div style='display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px;align-items:end'>"
        "<div><label class='lbl'>Key</label>"
        "<input name='key' placeholder='domain.role  e.g. custom.planner' required></div>"
        f"<div><label class='lbl'>Role</label><select name='role'>{role_opts_new}</select></div>"
        "<div><label class='lbl'>Model</label>"
        "<select name='model'>"
        "<option value=''>default (from Settings)</option>"
        "<option value='gemini-2.5-flash'>Gemini · 2.5 Flash</option>"
        "<option value='gemini-2.0-flash-lite'>Gemini · 2.0 Flash Lite</option>"
        "<option value='gemma-4-12b-it'>vLLM · Gemma 12B (Tools)</option>"
        "<option value='gemma-4-27b-it'>vLLM · Gemma 26B (Reasoning)</option>"
        "</select></div>"
        "</div>"
        "<div style='margin-top:10px'><button class='btn' type='submit'>Create</button></div>"
        "</form></div></details>"
    )

    # ── determine built-in keys ──────────────────────────────────────────────
    try:
        from sentinel.config import load_config as _lc
        default_keys = set(_lc().agents.keys())
    except Exception:
        default_keys = set(agents_cfg.keys())

    # ── group agents by prefix ───────────────────────────────────────────────
    from collections import defaultdict as _dd
    groups: dict[str, list[str]] = _dd(list)
    for key in sorted(agents_cfg.keys()):
        prefix = key.split(".", 1)[0]
        groups[prefix].append(key)

    # group header colours by category
    _GRP_COLOR = {
        "competitor": "#4285f4", "client": "#34a853", "software": "#00bcd4",
        "finance": "#ff9800",    "academic": "#9c27b0", "nutrition": "#e91e63",
        "travel": "#009688",     "govt_proposal": "#795548", "govt_dept_research": "#795548",
        "govt_synthesis": "#795548", "product_research": "#ff5722",
        "self_profile": "#607d8b", "compare": "#607d8b", "program": "#607d8b",
        "persona": "#9aa0a6",    "eval": "#9aa0a6", "orchestrator": "#9aa0a6",
        "coordinator": "#00bcd4",
    }

    group_sections = ""
    for grp, keys in sorted(groups.items()):
        gc = _GRP_COLOR.get(grp, "#9aa0a6")
        rows_html = (
            "<div style='font-size:11px;color:var(--muted);display:grid;"
            "grid-template-columns:2fr 1fr 1fr 60px;padding:6px 16px 4px;"
            "border-bottom:1px solid var(--line);gap:8px'>"
            "<span>Agent</span><span>Role</span><span>Model</span><span></span></div>"
        )
        for key in keys:
            ac = agents_cfg.get(key)
            if ac is not None:
                rows_html += _agent_row(key, ac, is_default=(key in default_keys))

        group_sections += (
            f"<details style='margin-bottom:8px' open>"
            f"<summary style='cursor:pointer;list-style:none;user-select:none;"
            f"padding:9px 14px;background:var(--surface2);border-radius:8px;"
            f"display:flex;align-items:center;gap:8px'>"
            f"<span style='width:10px;height:10px;border-radius:50%;"
            f"background:{gc};display:inline-block;flex-shrink:0'></span>"
            f"<span style='font-weight:600;font-size:13px'>{escape(grp)}</span>"
            f"<span style='color:var(--muted);font-size:12px'>{len(keys)} agent{'s' if len(keys)!=1 else ''}</span>"
            f"</summary>"
            f"<div class='card' style='padding:0;margin-top:4px;overflow:hidden'>"
            f"{rows_html}</div></details>"
        )

    # ── collapsible pipeline view ────────────────────────────────────────────
    lanes = ""
    for m in modes:
        flow = (
            "<div class='flowwrap'><div class='flow'>"
            + ("<div class='arrow'>" + _CHEVRON + "</div>").join(_flow_node(n) for n in m["nodes"])
            + "</div></div>"
        )
        lanes += (
            "<div class='lane-h'>"
            f"<span class='n-ico'>{_icon('agent')}</span>"
            f"<h2>{escape(m['title'])}</h2><span class='pv'>{escape(m['mode'])}</span>"
            f"<span class='mut'>writes <b style='color:var(--ink)'>{escape(m['artifact'])}</b></span>"
            "</div>" + flow
        )

    topo = "A2A coordinator" if flags.get("coordinator") else "Sequential pipeline"
    rail_steps = [
        ("recall",   "Memory recall",        "boundary-filtered, injected as context"),
        ("merge",    "Merge overlays",        "strategy + extraction gaps → artifact"),
        ("persist",  "Persist run",           "memory + run record (sources, run_seq)"),
        ("priority", "Recompute priority",    "deterministic 0–100 score — no LLM"),
    ]
    rail = "".join(
        f"<span class='step'>{_icon('merge')} <b>{escape(t)}</b> · {escape(d)}</span>"
        for _k, t, d in rail_steps
    )
    coord_card = (
        "<div class='card' style='margin-top:18px'>"
        f"<div class='gc-t'>Execution topology <span class='pv'>{escape(topo)}</span></div>"
        "<p class='gc-d'>A <b>SequentialAgent</b> runs stages in order, each writing its "
        "<span class='agent-key'>output_key</span> into shared session state. "
        "With <b>coordinator.enabled</b> an <b>LlmAgent</b> delegates via "
        "<span class='agent-key'>AgentTool</span>.</p>"
        "<div class='rail'>" + rail + "</div></div>"
    )
    pipeline_section = (
        "<details style='margin-top:20px'>"
        "<summary style='cursor:pointer;list-style:none;user-select:none;"
        "font-size:13px;font-weight:600;color:var(--muted);"
        "padding:9px 14px;background:var(--surface2);border-radius:8px'>"
        "Pipeline topology view</summary>"
        f"<div style='margin-top:6px'>{lanes}{coord_card}</div>"
        "</details>"
    )

    hero = (
        "<div class='hero left' style='margin-bottom:4px'><h1>Agents</h1>"
        "<p style='margin:0'>Configure the agents Sentinel runs — grouped by domain. "
        "Click Edit on any row to change model, role, or generation settings.</p></div>"
    )

    content = hero + flagline + banner + create_form + group_sections + pipeline_section
    return shell(active="agents", title="Agents", content=content, backend=backend)
