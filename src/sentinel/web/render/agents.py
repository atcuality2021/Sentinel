"""render.agents — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .base import shell

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
    # New design-system DAG node: .node (.dashed when flagged-off) wrapping .cap + .nm.
    dashed = " dashed" if n["dark"] else ""
    cap = escape(n["role"])
    if n["dark"] and n.get("flag"):
        cap = f"{cap} · {escape(n['flag'])} off"
    return (
        f"<div class='node{dashed}'>"
        f"<div class='cap'>{cap}</div>"
        f"<div class='nm'>{escape(n['name'])}</div></div>"
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
    """One roster table row + an expandable inline edit-form row for one agent."""
    role    = getattr(ac, "role", "synthesizer")
    model   = getattr(ac, "model", None) or ""
    enabled = getattr(ac, "enabled", True)
    gen     = getattr(ac, "generation", None)
    suffix  = key.split(".", 1)[-1] if "." in key else key
    uid     = key.replace(".", "-").replace("_", "-")

    # Role colour as a left-edge accent on a neutral badge (keeps the role palette).
    color = _ROLE_COLOR.get(role, "#9aa0a6")
    role_badge = (
        f"<span class='badge neutral' style='border-left:3px solid {color}'>"
        f"{escape(role)}</span>"
    )
    enabled_toggle = f"<div class='toggle{' on' if enabled else ''}'></div>"

    role_opts = "".join(
        f"<option value='{r}'{' selected' if r == role else ''}>{r}</option>"
        for r in _ALL_ROLES
    )
    temp_val = str(gen.temperature) if gen and gen.temperature is not None else ""
    tok_val  = str(gen.max_output_tokens) if gen and gen.max_output_tokens is not None else ""
    temp_label = temp_val if temp_val else "—"

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
        model_label = "<span class='mono'>default</span>"

    delete_btn = "" if is_default else (
        f"<form method='post' action='/agents/{escape(key)}/delete' style='display:inline;margin-left:6px' "
        f"onsubmit=\"return confirm('Delete agent ' + {escape(json.dumps(key), quote=True)} + '?')\">"
        f"<button class='btn sm danger' type='submit'>Delete</button></form>"
    )

    edit_form = (
        f"<tr id='edit-{uid}' style='display:none'>"
        f"<td colspan='6' style='background:var(--surface-2)'>"
        f"<form method='post' action='/agents/{escape(key)}'>"
        f"<div class='grid cols-4'>"
        # Model dropdown
        f"<div class='field'><label>Model</label>"
        f"<select name='model'>{model_opts}</select></div>"
        # Role
        f"<div class='field'><label>Role</label>"
        f"<select name='role'>{role_opts}</select></div>"
        # Temperature
        f"<div class='field'><label>Temperature</label>"
        f"<input class='input' name='temperature' value='{escape(temp_val)}' placeholder='0.7'></div>"
        # Max tokens
        f"<div class='field'><label>Max tokens</label>"
        f"<input class='input' name='max_output_tokens' value='{escape(tok_val)}' placeholder='4096'></div>"
        f"</div>"
        # Row 2: enabled + save + delete
        f"<div class='inline'>"
        f"<label style='font-size:12.5px;cursor:pointer'>"
        f"<input type='checkbox' name='enabled' value='1'{' checked' if enabled else ''}> Enabled</label>"
        f"<button class='btn sm' type='submit' style='margin-left:auto'>Save</button>"
        f"{delete_btn}"
        f"</div></form></td></tr>"
    )

    row = (
        f"<tr>"
        f"<td><b class='mono'>{escape(suffix)}</b></td>"
        f"<td>{role_badge}</td>"
        f"<td class='mono'>{model_label}</td>"
        f"<td class='num'>{escape(temp_label)}</td>"
        f"<td>{enabled_toggle}</td>"
        f"<td><button type='button' class='btn sm ghost'"
        f" onclick=\"var d=document.getElementById('edit-{uid}');"
        f"d.style.display=d.style.display==='none'?'table-row':'none'\">Edit</button></td>"
        f"</tr>"
        f"{edit_form}"
    )
    return row


def agents_page(*, modes: list[dict], flags: dict, backend: str,
                agents_cfg: dict | None = None, ok: str = "", err: str = "") -> str:
    """Agents page: grouped accordion tables + CRUD + collapsible pipeline view."""
    agents_cfg = agents_cfg or {}

    banner = ""
    if ok:
        banner = f"<div class='card pad-sm badge ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card pad-sm badge bad' style='margin-bottom:16px'>{escape(err)}</div>"

    # ── feature flags ─────────────────────────────────────────────────────────
    def flag_row(label: str, on: bool) -> str:
        badge = "<span class='badge ok'>on</span>" if on else "<span class='badge neutral'>off</span>"
        return f"<div class='row-between'><span>{escape(label)}</span>{badge}</div>"

    flags_card = (
        "<div class='card' style='margin-bottom:24px'>"
        "<div class='card-head'><h2>Feature flags</h2></div>"
        "<div class='grid cols-4'>"
        + flag_row("Two-tier extractor", flags.get("two_tier", False))
        + flag_row("Strategy overlay", flags.get("strategy", False))
        + flag_row("Private boundary", flags.get("private", False))
        + flag_row("Coordinator", flags.get("coordinator", False))
        + "</div></div>"
    )

    # ── create form ──────────────────────────────────────────────────────────
    role_opts_new = "".join(f"<option value='{r}'>{r}</option>" for r in _ALL_ROLES)
    create_form = (
        "<details style='margin-bottom:16px'>"
        "<summary style='cursor:pointer;font-size:13px;font-weight:600;"
        "color:var(--accent-text);padding:9px 14px;background:var(--surface-2);"
        "border-radius:8px;list-style:none;user-select:none'>＋ Add custom agent</summary>"
        "<div class='card' style='margin-top:4px;border-radius:0 0 8px 8px'>"
        "<form method='post' action='/agents'>"
        "<div class='grid cols-3'>"
        "<div class='field'><label>Key</label>"
        "<input class='input' name='key' placeholder='domain.role  e.g. custom.planner' required></div>"
        f"<div class='field'><label>Role</label><select name='role'>{role_opts_new}</select></div>"
        "<div class='field'><label>Model</label>"
        "<select name='model'>"
        "<option value=''>default (from Settings)</option>"
        "<option value='gemini-2.5-flash'>Gemini · 2.5 Flash</option>"
        "<option value='gemini-2.0-flash-lite'>Gemini · 2.0 Flash Lite</option>"
        "<option value='gemma-4-12b-it'>vLLM · Gemma 12B (Tools)</option>"
        "<option value='gemma-4-27b-it'>vLLM · Gemma 26B (Reasoning)</option>"
        "</select></div>"
        "</div>"
        "<button class='btn' type='submit'>Create</button>"
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
        rows_html = ""
        for key in keys:
            ac = agents_cfg.get(key)
            if ac is not None:
                rows_html += _agent_row(key, ac, is_default=(key in default_keys))

        table_html = (
            "<div class='table-wrap'><table class='table'>"
            "<thead><tr><th>Agent</th><th>Role</th><th>Model</th>"
            "<th class='num'>Temp</th><th>Enabled</th><th></th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )

        group_sections += (
            f"<details style='margin-bottom:8px' open>"
            f"<summary style='cursor:pointer;list-style:none;user-select:none;"
            f"padding:9px 14px;background:var(--surface-2);border-radius:8px;"
            f"display:flex;align-items:center;gap:8px'>"
            f"<span class='dot' style='background:{gc};flex-shrink:0'></span>"
            f"<span style='font-weight:600;font-size:13px'>{escape(grp)}</span>"
            f"<span style='color:var(--muted);font-size:12px'>{len(keys)} agent{'s' if len(keys)!=1 else ''}</span>"
            f"</summary>"
            f"<div class='card' style='padding:0;margin-top:4px;overflow:hidden'>"
            f"{table_html}</div></details>"
        )
    roster_card = (
        "<div class='card' style='margin-bottom:24px'>"
        "<div class='card-head'><h2>Roster</h2></div>"
        f"{group_sections}</div>"
    )

    # ── collapsible pipeline view ────────────────────────────────────────────
    lanes = ""
    for m in modes:
        flow = (
            "<div class='dag'>"
            + "<span class='arrow'>→</span>".join(_flow_node(n) for n in m["nodes"])
            + "</div>"
        )
        lanes += (
            "<div class='card-head' style='margin-top:18px'>"
            f"<h2>{escape(m['title'])}</h2><span class='pill'>{escape(m['mode'])}</span>"
            f"<span class='pill'>writes <b>{escape(m['artifact'])}</b></span>"
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
        f"<div class='row-between'><span><b>{escape(t)}</b></span>"
        f"<span style='color:var(--muted);font-size:12px'>{escape(d)}</span></div>"
        for _k, t, d in rail_steps
    )
    coord_card = (
        "<div class='card' style='margin-top:18px'>"
        f"<div class='card-head'><h2>Execution topology</h2><span class='pill'>{escape(topo)}</span></div>"
        "<p style='color:var(--muted);margin:0 0 12px'>A <b>SequentialAgent</b> runs stages in order, "
        "each writing its <span class='mono'>output_key</span> into shared session state. "
        "With <b>coordinator.enabled</b> an <b>LlmAgent</b> delegates via "
        "<span class='mono'>AgentTool</span>.</p>"
        "<div class='stack'>" + rail + "</div></div>"
    )
    pipeline_section = (
        "<details style='margin-top:20px'>"
        "<summary style='cursor:pointer;list-style:none;user-select:none;"
        "font-size:13px;font-weight:600;color:var(--muted);"
        "padding:9px 14px;background:var(--surface-2);border-radius:8px'>"
        "Pipeline topology view</summary>"
        f"<div style='margin-top:6px'>{lanes}{coord_card}</div>"
        "</details>"
    )

    page_head = (
        "<div class='page-head'><div class='grow'><h1>Agents</h1>"
        "<p>Configure the agents Sentinel runs — grouped by domain. "
        "Click Edit on any row to change model, role, or generation settings.</p></div></div>"
    )

    content = (page_head + banner + flags_card + create_form
               + roster_card + pipeline_section)
    return shell(active="agents", title="Agents", content=content, backend=backend)
