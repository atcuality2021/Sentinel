"""render.personas — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .base import _icon, shell

_DOMAINS = ["market", "account", "software", "finance", "academic", "nutrition", "travel",
            "govt_proposal", "product_research"]
# Persona = who the output is for (reading level / tone / format). The orchestrated run renders the
# deliverable for this persona without changing the facts (SENTINEL-012 AC-8/17).
_PERSONAS = ["enterprise", "developer", "consumer", "student", "doctor", "nurse", "custom"]

# Persona() field defaults, repeated here so the form's placeholder map can show the effective
# profile for every option (incl. "custom", which starts from defaults) without instantiating models.
_PERSONA_FIELD_DEFAULTS = {"reading_level": "professional", "tone": "neutral",
                           "format": "brief", "source_policy": ""}


def _persona_profile_map_json(saved: dict[str, dict[str, str]] | None = None) -> str:
    """JSON map persona-name → effective full profile (registry over defaults) for the task form's
    placeholder prefill. Single source of truth stays PERSONA_PROFILES (artifacts/schemas.py);
    ``saved`` adds library personas (name → profile dict) and "auto" gets explainer placeholders."""
    from sentinel.artifacts.schemas import PERSONA_PROFILES

    out = {p: {**_PERSONA_FIELD_DEFAULTS, **PERSONA_PROFILES.get(p, {})} for p in _PERSONAS}
    for name, profile in (saved or {}).items():
        out[name] = {**_PERSONA_FIELD_DEFAULTS, **{k: v for k, v in profile.items() if v}}
    auto_hint = "(agent picks by domain)"
    out["auto"] = {"reading_level": auto_hint, "tone": auto_hint,
                   "format": auto_hint, "source_policy": auto_hint}
    # Saved names/fields are user input embedded inside a <script> tag: a literal "</script>"
    # (or "<!--") in a value would terminate the block early (stored XSS). The \\u003c escape
    # decodes to the same string after JSON.parse but is inert as HTML — the block cannot
    # close early.
    return json.dumps(out).replace("<", "\\u003c")


def _persona_label(persona) -> str:
    """Pill text for a task persona — flags agent-selected ones so 'why student?' is answerable
    at a glance ('auto' resolved by DOMAIN_DEFAULT_PERSONA, not picked by the user)."""
    name = escape(persona.name)
    return f"{name} <span style='color:var(--muted)'>(auto)</span>" \
        if getattr(persona, "auto_selected", False) else name


def _persona_tip(persona) -> str:
    """Tooltip text exposing the FULL audience profile behind a persona pill (the name alone hides
    the reading-level/tone/format/source-policy that actually shaped the rendered output)."""
    bits = [f"reading level: {persona.reading_level}", f"tone: {persona.tone}",
            f"format: {persona.format}"]
    if persona.source_policy:
        bits.append(f"sources: {persona.source_policy}")
    return " · ".join(bits)


def _task_form(project_id: str, *, default_backend: str = "gemini",
               vllm_model: str = "gemma-4-12b-it", sovereign: bool = False,
               project_context: str = "", saved_personas: list | None = None) -> str:
    """The objective → plan entry point (SENTINEL-012): a GET form that hands the objective, domain,
    persona, and reasoning backend to the planner route. The backend toggle mirrors the New Run form
    so users with both Gemini and vLLM can choose per-task."""
    domains = "".join(f"<option value='{d}'>{d}</option>" for d in _DOMAINS)
    # Option order = resolution story: auto (agent picks by domain, the default) → built-in
    # registry names → saved library personas (/personas) → custom (override fields only).
    builtins = [p for p in _PERSONAS if p != "custom"]
    _builtins_lower = {p.lower() for p in builtins}
    # A saved persona that OVERRIDES a built-in (same name) must not show as a second option —
    # the built-in option already covers it; its edited profile flows via the profile map below.
    saved_names = [p.name for p in (saved_personas or [])
                   if p.name.strip().lower() not in _builtins_lower]
    personas = "<option value='auto' selected>auto — let the agent pick</option>" + "".join(
        f"<option value='{escape(p)}'>{escape(p)}</option>"
        for p in builtins + saved_names + ["custom"])
    # All saved profiles (incl. built-in overrides) go into the map so the form prefill and the
    # override both take effect — _persona_profile_map_json applies them over the code defaults.
    saved_profiles = {p.name: {"reading_level": p.reading_level, "tone": p.tone,
                               "format": p.format, "source_policy": p.source_policy or ""}
                      for p in (saved_personas or [])}
    gemini_checked = "" if (default_backend == "vllm" or sovereign) else "checked"
    vllm_checked = "checked" if (default_backend == "vllm" or sovereign) else ""
    gemini_disabled = "disabled" if sovereign else ""
    sovereign_note = (
        "<div class='note' style='margin-top:6px;color:var(--accent-2)'>Governance: "
        "<b>on_prem_required</b> — cloud blocked; tasks run on-prem only.</div>"
        if sovereign else ""
    )
    return (
        "<div class='section-h'><h2>New task</h2></div>"
        "<div class='card'>"
        f"<form class='run' method='get' action='/projects/{escape(project_id)}/plan'>"
        "<div><label class='lbl' for='t-obj'>Objective</label>"
        "<input id='t-obj' name='objective' required "
        "placeholder='e.g. Research Assam government departments and map BiltIQ capabilities'></div>"
        "<div><label class='lbl' for='t-ctx'>Research context <span style='font-weight:400;"
        "color:var(--muted)'>(optional — background injected into every agent)</span></label>"
        "<textarea id='t-ctx' name='context' rows='3' "
        "style='width:100%;padding:8px;background:var(--panel-2);border:1px solid var(--accent-line);"
        "border-radius:6px;color:var(--ink);font-size:13px;resize:vertical' "
        "placeholder='e.g. Vendor is BiltIQ AI — sovereign on-premise AI platform; "
        "buyer needs 16GB RAM + 1TB SSD under ₹1 lakh; target government is Assam state …'>"
        f"{escape(project_context)}</textarea>"
        + ("<div class='note' style='margin-top:4px'>Inherited from the project — edit to "
           "override for this task.</div>" if project_context else "")
        + "</div>"
        # Client/partner URL — crawled into KB before agents run
        "<div id='client-url-row'>"
        "<label class='lbl' for='t-curl'>Client / research website "
        "<span style='font-weight:400;color:var(--muted)'>(optional — crawled into KB before agents run)</span>"
        "</label>"
        "<input id='t-curl' name='client_url' type='url' "
        "style='width:100%;padding:8px;background:var(--panel-2);border:1px solid var(--accent-line);"
        "border-radius:6px;color:var(--ink);font-size:13px' "
        "placeholder='https://assam.gov.in  or  https://client-site.com'></div>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
        "<div><label class='lbl' for='t-dom'>Domain</label>"
        f"<select id='t-dom' name='domain' onchange=\""
        "var d=this.value;"
        "var r=document.getElementById('client-url-row');"
        "var i=document.getElementById('t-curl');"
        "if(d==='govt_proposal'){r.style.borderLeft='3px solid var(--accent-2)';r.style.paddingLeft='8px';"
        "if(!i.value)i.placeholder='https://assam.gov.in — client site will be indexed into KB';}"
        "else{r.style.borderLeft='';r.style.paddingLeft='';}"
        f"\">{domains}</select></div>"
        "<div><label class='lbl' for='t-per'>Persona</label>"
        f"<select id='t-per' name='persona'>{personas}</select></div>"
        "</div>"
        # Customise-persona: the full audience profile (reading level / tone / format / source
        # policy) behind the selected name, editable per task. Blank = the registry profile;
        # filled = override (the "custom" persona is exactly this with no named base).
        "<details id='t-pcust' style='margin-top:2px'>"
        "<summary class='note' style='cursor:pointer'>Customise persona — reading level, tone, "
        "format, source policy <span style='color:var(--muted)'>(optional)</span></summary>"
        "<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:8px'>"
        "<div><label class='lbl' for='t-rl'>Reading level</label>"
        "<input id='t-rl' name='reading_level'></div>"
        "<div><label class='lbl' for='t-tone'>Tone</label>"
        "<input id='t-tone' name='tone'></div>"
        "<div><label class='lbl' for='t-fmt'>Output format</label>"
        "<input id='t-fmt' name='format'></div>"
        "<div><label class='lbl' for='t-sp'>Source policy</label>"
        "<input id='t-sp' name='source_policy'></div>"
        "</div>"
        "<div class='note' style='margin-top:4px'>Blank fields use the selected persona's profile "
        "(shown as placeholder); filled fields override it for this task. Facts and citations never "
        "change — persona shapes presentation only.</div>"
        "</details>"
        f"<script type='application/json' id='t-pmap'>{_persona_profile_map_json(saved_profiles)}</script>"
        "<script>(function(){"
        "var s=document.getElementById('t-per');"
        "var m=JSON.parse(document.getElementById('t-pmap').textContent);"
        "function f(){var p=m[s.value]||m['enterprise'];"
        "document.getElementById('t-rl').placeholder=p.reading_level;"
        "document.getElementById('t-tone').placeholder=p.tone;"
        "document.getElementById('t-fmt').placeholder=p.format;"
        "document.getElementById('t-sp').placeholder=p.source_policy||'(none)';"
        "if(s.value==='custom'){document.getElementById('t-pcust').open=true;}}"
        "s.addEventListener('change',f);f();})();</script>"
        "<div><label class='lbl'>Reasoning backend</label>"
        "<div class='seg'>"
        f"<input class='cloud' type='radio' id='tb-gemini' name='backend' value='gemini' "
        f"{gemini_checked} {gemini_disabled}>"
        "<label class='l-cloud' for='tb-gemini'>☁ Cloud · Gemini"
        "<span class='sub'>managed API</span></label>"
        f"<input class='onprem' type='radio' id='tb-vllm' name='backend' value='vllm' {vllm_checked}>"
        f"<label class='l-onprem' for='tb-vllm'>🔒 On-prem · Gemma"
        f"<span class='sub'>{escape(vllm_model)} · vLLM</span></label>"
        "</div></div>"
        f"{sovereign_note}"
        f"<div><button class='btn' type='submit'>{_icon('bolt')} Plan task</button></div>"
        "</form>"
        "</div>"
    )


def personas_page(saved: list, *, backend: str, ok: str = "", err: str = "",
                  gen: dict | None = None, builtin_overrides: dict | None = None) -> str:
    """Persona library (/personas): built-in audience profiles (editable via override), saved
    personas (full CRUD), and an LLM generator that drafts a full profile from a plain-English
    audience description. Generated values arrive via gen_* query params (PRG) and prefill the
    create form — the same mechanism powers a built-in's "Edit". ``builtin_overrides`` maps a
    built-in name → its override SavedPersona (so the card shows the edited profile + Reset)."""
    from sentinel.artifacts.schemas import PERSONA_PROFILES

    g = gen or {}
    banner = ""
    if ok:
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad' style='margin-bottom:16px'>{escape(err)}</div>"

    # --- generator card -----------------------------------------------------
    generator = (
        "<div class='card' style='margin-bottom:20px'>"
        "<h2 class='sec' style='margin-top:0'>Generate a persona</h2>"
        "<div class='note' style='margin-bottom:10px'>Describe the audience in plain words — "
        f"the {escape(backend)} model drafts the full profile, which lands in the form below "
        "for review before saving.</div>"
        "<form method='post' action='/personas/generate' class='set-grid'>"
        "<div><label class='lbl' for='gen-desc'>Audience description</label>"
        "<textarea id='gen-desc' name='description' rows='2' required "
        "placeholder='e.g. A hospital procurement officer comparing medical-device vendors "
        "under strict budget rules'></textarea></div>"
        "<div class='row2'>"
        "<div><label class='lbl' for='gen-name'>Persona name <span class='note'>(optional — "
        "carried into the form)</span></label>"
        "<input id='gen-name' name='name' placeholder='e.g. procurement officer'></div>"
        "<div style='align-self:end'><button class='btn' type='submit'>Generate profile</button></div>"
        "</div></form></div>"
    )

    # --- create form (prefilled from gen_* when present) ----------------------
    def _val(key: str) -> str:
        return f" value='{escape(g.get(key, ''))}'" if g.get(key) else ""

    create_form = (
        "<div class='card' style='margin-bottom:24px' id='create'>"
        "<h2 class='sec' style='margin-top:0'>New persona</h2>"
        "<form method='post' action='/personas/create' class='set-grid'>"
        "<div class='row2'>"
        "<div><label class='lbl' for='p-name'>Name</label>"
        f"<input id='p-name' name='name' required placeholder='e.g. CFO brief'{_val('name')}></div>"
        "<div><label class='lbl' for='p-desc'>Description</label>"
        f"<input id='p-desc' name='description' placeholder='who this audience is'{_val('desc')}></div>"
        "</div>"
        "<div class='row2'>"
        "<div><label class='lbl' for='p-rl'>Reading level</label>"
        f"<input id='p-rl' name='reading_level' placeholder='professional'{_val('rl')}></div>"
        "<div><label class='lbl' for='p-tone'>Tone</label>"
        f"<input id='p-tone' name='tone' placeholder='neutral'{_val('tone')}></div>"
        "</div>"
        "<div class='row2'>"
        "<div><label class='lbl' for='p-fmt'>Output format</label>"
        f"<input id='p-fmt' name='format' placeholder='brief'{_val('fmt')}></div>"
        "<div><label class='lbl' for='p-sp'>Source policy</label>"
        f"<input id='p-sp' name='source_policy' placeholder='(none)'{_val('sp')}></div>"
        "</div>"
        "<div class='set-actions'><button class='btn' type='submit'>Save persona</button>"
        "<span class='note' style='align-self:center;margin-left:8px'>Saved personas appear in "
        "every task form's persona dropdown.</span></div>"
        "</form></div>"
    )

    # --- saved persona cards --------------------------------------------------
    def _profile_rows(rl: str, tone: str, fmt: str, sp: str) -> str:
        rows = [("reading level", rl), ("tone", tone), ("format", fmt)]
        if sp:
            rows.append(("sources", sp))
        return "".join(
            f"<div style='display:flex;gap:8px;font-size:12px;margin-top:4px'>"
            f"<span style='color:var(--muted);min-width:92px'>{label}</span>"
            f"<span>{escape(value)}</span></div>"
            for label, value in rows)

    # A saved persona whose name matches a built-in is an OVERRIDE — it shows on the built-in
    # card (as "overridden"), not here, so it isn't listed twice.
    library = [p for p in saved if p.name.strip().lower() not in PERSONA_PROFILES]
    if library:
        saved_cards = "".join(
            "<div class='card' style='margin-bottom:10px'>"
            "<div style='display:flex;align-items:center;justify-content:space-between;gap:10px'>"
            f"<div><b>{escape(p.name)}</b>"
            + (f" <span class='note'>— {escape(p.description)}</span>" if p.description else "")
            + f"{_profile_rows(p.reading_level, p.tone, p.format, p.source_policy or '')}</div>"
            f"<form method='post' action='/personas/{escape(p.id)}/delete' "
            "onsubmit=\"return confirm('Delete this persona? Existing tasks keep their copy.')\">"
            "<button class='btn ghost' type='submit' style='font-size:12px;color:#ff6b6b'>Delete</button>"
            "</form></div></div>"
            for p in library)
    else:
        saved_cards = ("<div class='card'><div class='empty'>No saved personas yet — "
                       "create one above or generate from a description.</div></div>")

    # --- built-in cards (editable via override; enterprise stays read-only) ---
    from urllib.parse import quote as _qp
    ov = {k.strip().lower(): v for k, v in (builtin_overrides or {}).items()}

    def _builtin_card(name: str, profile: dict) -> str:
        o = ov.get(name)
        if o is not None:  # an override edits the built-in's effective profile
            rl, tone, fmt, sp = o.reading_level, o.tone, o.format, (o.source_policy or "")
        else:
            rl = profile.get("reading_level", "professional")
            tone = profile.get("tone", "neutral")
            fmt = profile.get("format", "brief")
            sp = profile.get("source_policy", "")
        # enterprise must stay == Persona() (dag skip-pass invariant) → not editable.
        editable = name != "enterprise"
        tag = ("<span class='note' style='color:var(--accent-2)'>— overridden</span>"
               if o is not None else "<span class='note'>— built-in</span>")
        controls = ""
        if editable:
            edit_url = "/personas?" + "&".join([
                f"gen_name={_qp(name)}", f"gen_rl={_qp(rl)}", f"gen_tone={_qp(tone)}",
                f"gen_fmt={_qp(fmt)}", f"gen_sp={_qp(sp)}"]) + "#create"
            controls += (f"<a class='btn ghost' style='font-size:12px' href='{edit_url}'>Edit</a>")
            if o is not None:
                controls += (
                    f"<form method='post' action='/personas/{escape(o.id)}/delete' style='display:inline'"
                    " onsubmit=\"return confirm('Reset this persona to its built-in default?')\">"
                    "<button class='btn ghost' type='submit' "
                    "style='font-size:12px;color:#d4a017'>Reset to default</button></form>")
        body = (f"<div><b>{escape(name)}</b> {tag}"
                + _profile_rows(rl, tone, fmt, sp)
                + ("<div class='note' style='margin-top:6px'>Default audience — tasks with this "
                   "persona skip the extra render pass (kept read-only).</div>"
                   if name == "enterprise" else "")
                + "</div>")
        return ("<div class='card' style='margin-bottom:10px'>"
                "<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:10px'>"
                + body
                + (f"<div style='display:flex;gap:6px;flex-shrink:0'>{controls}</div>" if controls else "")
                + "</div></div>")

    builtin_cards = "".join(_builtin_card(name, profile) for name, profile in PERSONA_PROFILES.items())

    content = (
        banner + generator + create_form
        + f"<div class='section-h'><h2>Saved personas <span class='note'>{len(library)}</span></h2></div>"
        + saved_cards
        + "<div class='section-h' style='margin-top:24px'><h2>Built-in personas</h2></div>"
        + "<div class='note' style='margin-bottom:10px'><b>Edit</b> tweaks a built-in for every "
        "task (saved as an override); <b>Reset to default</b> restores the code profile. "
        "<b>enterprise</b> stays read-only. Pick <b>auto</b> in the task form to let the agent "
        "choose one by domain.</div>"
        + builtin_cards)
    return shell(active="personas", title="Personas", content=content, backend=backend)
