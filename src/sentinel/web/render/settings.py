"""render.settings — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from sentinel.strategy import discover_playbooks

from .base import shell, _icon

# --------------------------------------------------------------------------- #
# Settings (SENTINEL-003)
# --------------------------------------------------------------------------- #
def _num(name: str, label: str, value, *, step: str = "any", mn: str = "", mx: str = "") -> str:
    v = "" if value is None else escape(str(value))
    mn_a = f" min='{mn}'" if mn != "" else ""
    mx_a = f" max='{mx}'" if mx != "" else ""
    return (
        f"<div class='field'><label for='{name}'>{escape(label)}</label>"
        f"<input class='input' type='number' step='{step}'{mn_a}{mx_a} id='{name}' name='{name}' value='{v}'></div>"
    )


def _gen_row(gen) -> str:
    """Four generation inputs (temperature/max_output_tokens/top_p/top_k)."""
    return (
        "<div class='grid cols-2'>"
        + _num("temperature", "Temperature", gen.temperature, step="0.05", mn="0", mx="2")
        + _num("max_output_tokens", "Max tokens", gen.max_output_tokens, step="1", mn="1", mx="32768")
        + _num("top_p", "top_p", gen.top_p, step="0.01", mn="0", mx="1")
        + _num("top_k", "top_k", gen.top_k, step="1", mn="1")
        + "</div>"
    )


def _chk(name: str, label: str, checked: bool) -> str:
    c = "checked" if checked else ""
    return (
        f"<label class='chk'><input type='checkbox' name='{name}' value='1' {c}>"
        f"{escape(label)}</label>"
    )


def _sel(name: str, label: str, value: str, options: list[tuple[str, str]]) -> str:
    """A labelled <select>. ``options`` are (value, human-label) pairs; ``value`` is preselected."""
    opts = "".join(
        f"<option value='{escape(v)}'{' selected' if v == value else ''}>{escape(lbl)}</option>"
        for v, lbl in options
    )
    return (
        f"<div class='field'><label for='{name}'>{escape(label)}</label>"
        f"<select id='{name}' name='{name}'>{opts}</select></div>"
    )


def _settings_agent_card(key: str, a) -> str:
    return (
        "<div class='card'>"
        f"<form method='post' action='/settings/agents/{escape(key)}' class='set-grid'>"
        "<div class='row-between'>"
        f"<span class='agent-key'>{escape(key)}</span>"
        f"<div class='inline'>{_chk('enabled','enabled',a.enabled)}"
        f"{_chk('pin_gemini','pin to Gemini',a.pin_gemini)}</div></div>"
        "<div class='field'><label for='model-" + escape(key) + "'>Model "
        "(blank ⇒ backend default)</label>"
        f"<input class='input' id='model-{escape(key)}' name='model' value='{escape(a.model or '')}' "
        "placeholder='inherit backend default'></div>"
        f"{_gen_row(a.generation)}"
        f"<div class='set-actions'><button class='btn' type='submit'>Save agent</button></div>"
        "</form></div>"
    )


def _prompt_card(key: str, p) -> str:
    vars_hint = (
        f"<p class='varsHint'>allowed vars: {escape(', '.join('{' + v + '}' for v in p.variables))}"
        "</p>" if p.variables else "<p class='varsHint'>no required vars</p>"
    )
    return (
        "<details class='card' style='margin-bottom:12px'>"
        f"<summary><span class='agent-key'>{escape(key)}</span></summary>"
        "<div style='margin-top:12px'>"
        f"<form method='post' action='/settings/prompts/{escape(key)}' class='set-grid'>"
        f"<div class='field'><textarea name='template' rows='7'>{escape(p.template)}</textarea></div>"
        f"{vars_hint}"
        "<div class='set-actions'><button class='btn' type='submit'>Save prompt</button></div>"
        "</form>"
        f"<form method='post' action='/settings/prompts/{escape(key)}/reset' "
        "style='margin-top:8px'>"
        "<button class='btn ghost' type='submit'>Reset to shipped default</button>"
        "</form></div></details>"
    )


# Per-role model tiering (SENTINEL-011): role → tier label. The endpoint *placeholder* shown for
# an unset role comes from the deployment's own config (settings_page derives it from the flat
# vLLM api_base) — hardcoding one org's hosts here leaked them into every deployment's UI.
_ROLE_TIERS = [
    ("coordinator", "tool-caller · 12B"),
    ("planner", "tool-caller · 12B"),
    ("public_research", "tool-caller · 12B"),
    ("private_research", "tool-caller · 12B"),
    ("extractor", "tool-caller · 12B"),
    ("synthesizer", "reasoner · 26B (no tools)"),
    ("strategist", "reasoner · 26B (no tools)"),
]


def settings_page(cfg, *, backend: str, gemini_key_set: bool, ok: str = "", err: str = "",
                  vllm_key_set: bool = False, brave_key_set: bool = False,
                  serpapi_key_set: bool = False, atcuality_key_set: bool = False,
                  google_cse_id_set: bool = False, mcp_rows: list[dict] | None = None,
                  password_ok: str = "", password_err: str = "") -> str:
    banner = ""
    if ok:
        banner = f"<div class='card banner ok'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad'>{escape(err)}</div>"

    def _key_pill(name: str, ok_: bool) -> str:
        return (f"<span class='pill'><span class='dot' style='color:"
                f"{'var(--ok)' if ok_ else 'var(--bad)'}'></span>"
                f"{escape(name)}: <b>{'set' if ok_ else 'not set'}</b></span>")

    key_pill = _key_pill("GOOGLE_API_KEY", gemini_key_set) + _key_pill("VLLM_API_KEY", vllm_key_set)
    g_checked = "checked" if backend != "vllm" else ""
    v_checked = "checked" if backend == "vllm" else ""

    backends = (
        "<div class='card'><div class='card-head'><h2>Backends</h2></div>"
        "<form method='post' action='/settings/backends' class='set-grid'>"
        "<div class='field'><label>Default reasoning backend</label><div class='seg'>"
        f"<input class='cloud' type='radio' id='sb-gemini' name='default' value='gemini' {g_checked}>"
        "<label class='l-cloud' for='sb-gemini'>☁ Cloud · Gemini</label>"
        f"<input class='onprem' type='radio' id='sb-vllm' name='default' value='vllm' {v_checked}>"
        "<label class='l-onprem' for='sb-vllm'>🔒 On-prem · Gemma</label></div></div>"
        "<div class='grid cols-2'>"
        f"<div class='field'><label for='gemini_model'>Gemini model</label>"
        f"<input class='input' id='gemini_model' name='gemini_model' value='{escape(cfg.backend.gemini.model)}'></div>"
        f"<div class='field'><label for='vllm_model'>vLLM tool-caller model <span class='hint'>(12B — planners, extractors)</span></label>"
        f"<input class='input' id='vllm_model' name='vllm_model' value='{escape(cfg.backend.vllm.model)}'></div>"
        "</div>"
        f"<div class='field'><label for='vllm_api_base'>vLLM API base (tool-caller)</label>"
        f"<input class='input mono' id='vllm_api_base' name='vllm_api_base' "
        f"value='{escape(cfg.backend.vllm.api_base or '')}'></div>"
        + (lambda _r, _ra: (
            f"<div class='grid cols-2'>"
            f"<div class='field'><label for='vllm_reasoning_model'>vLLM reasoning model <span class='hint'>(26B — synthesizers, strategists)</span></label>"
            f"<input class='input' id='vllm_reasoning_model' name='vllm_reasoning_model' value='{escape(_r)}'></div>"
            f"<div class='field'><label for='vllm_reasoning_api_base'>vLLM API base (reasoning)</label>"
            f"<input class='input mono' id='vllm_reasoning_api_base' name='vllm_reasoning_api_base' value='{escape(_ra)}'></div>"
            f"</div>"
        ))(
            (cfg.backend.roles or {}).get("synthesizer", cfg.backend.vllm).model,
            (cfg.backend.roles or {}).get("synthesizer", cfg.backend.vllm).api_base or "",
        )
        + f"<div class='set-actions'>{key_pill}"
        "<span style='flex:1'></span><button class='btn' type='submit'>Save backends</button></div>"
        "<p class='note'><b>One source of truth:</b> API keys live in <span class='mono'>.env</span> "
        "(shown here only as set / not-set, never the value); models, endpoints and the default "
        "backend live here and are saved to <span class='mono'>sentinel.config.yaml</span>. The "
        "topbar pill and every run read this same saved default — no env override. "
        "Leave the reasoning model blank to use the same model for all roles.</p>"
        "</form></div>"
    )

    generation = (
        "<div class='card'><div class='card-head'><h2>Generation defaults</h2></div>"
        "<form method='post' action='/settings/generation' class='set-grid'>"
        f"{_gen_row(cfg.generation)}"
        "<div class='set-actions'><button class='btn' type='submit'>Save generation</button></div>"
        "<p class='note'>Global defaults. A per-agent field left blank inherits these.</p>"
        "</form></div>"
    )

    memory = (
        "<div class='card'><div class='card-head'><h2>Memory</h2></div>"
        "<form method='post' action='/settings/memory' class='set-grid'>"
        f"<div class='inline' style='gap:20px'>"
        f"{_chk('entity_memory','entity memory enabled',cfg.memory.entity_memory)}"
        f"{_chk('inject_org_prefs','inject org preferences',cfg.memory.inject_org_prefs)}"
        f"{_chk('episodic_recall','episodic recall (inject past sessions)',getattr(cfg.memory,'episodic_recall',True))}"
        "</div>"
        + "<div class='grid cols-2'>"
        + _num("retention_days", "Retention (days)", cfg.memory.retention_days, step="1", mn="1")
        + _num("episodic_recall_top_k", "Episodic recall depth (top-K sessions)", getattr(cfg.memory,"episodic_recall_top_k",3), step="1", mn="1", mx="10")
        + "</div>"
        + "<div class='grid cols-2'>"
        + _num("context_window_tokens", "Context window (tokens)", getattr(cfg.memory,"context_window_tokens",2400), step="100", mn="800", mx="16000")
        + "</div>"
        + "<div class='set-actions'>"
        + "<a class='btn ghost' href='/memory/episodes'>View &amp; manage episodes</a>"
        + "<span style='flex:1'></span>"
        + "<button class='btn' type='submit'>Save memory</button></div>"
        + "<p class='note'>Episodic recall injects prior research sessions into the planner's context. "
        + "Top-K sets how many prior sessions are recalled (1–10). "
        + "Context window controls the total token budget split across entity-hot/cold, episodic and KB context (800–16 000). "
        + "<a href='/memory/episodes'>View / delete individual run records →</a></p>"
        "</form></div>"
    )

    harness = (
        "<div class='card'><div class='card-head'><h2>Agent Harness</h2></div>"
        "<form method='post' action='/settings/harness' class='set-grid'>"
        "<div class='grid cols-3'>"
        + _num("max_turns", "Max turns per step", getattr(cfg.backend,"max_turns",30), step="1", mn="1")
        + _num("max_retries", "Max retries on failure", getattr(cfg.backend,"max_retries",3), step="1", mn="1")
        + _num("base_retry_delay_s", "Base retry delay (s)", getattr(cfg.backend,"base_retry_delay_s",1.0), step="0.1", mn="0")
        + "</div>"
        + "<div class='set-actions'><button class='btn' type='submit'>Save harness</button></div>"
        + "<p class='note'><b>Turn controller:</b> max turns per step caps how many LLM calls ADK makes "
        + "(default 30). <b>Retry policy:</b> on a transient vLLM 5xx, retries up to max-retries times "
        + "with exponential backoff (delay × 2ⁿ). Set base delay to 0 to disable sleeping (tests).</p>"
        "</form></div>"
    )

    gov = cfg.governance
    sovereign = gov.compliance_mode == "on_prem_required"
    governance = (
        "<div class='card'><div class='card-head'><h2>Governance · sovereignty policy</h2></div>"
        "<form method='post' action='/settings/governance' class='set-grid'>"
        + _sel("compliance_mode", "Compliance mode", gov.compliance_mode, [
            ("cloud_ok", "☁ cloud_ok — Gemini grounding allowed"),
            ("on_prem_preferred", "on_prem_preferred — prefer on-prem, cloud permitted"),
            ("on_prem_required", "🔒 on_prem_required — NO cloud (Gemini blocked)"),
        ])
        + "<div class='inline' style='gap:20px'>"
        + _chk("audit_log", "audit log enabled", gov.audit_log)
        + _chk("block_cloud_on_private", "force on-prem for any run touching private data",
               gov.block_cloud_on_private)
        + "</div>"
        "<div class='set-actions'><button class='btn' type='submit'>Save governance</button></div>"
        "<p class='note'><b>The orchestrator obeys this.</b> In "
        "<span class='mono'>on_prem_required</span> no Gemini model is built and public search "
        "falls back to a non-cloud provider — the no-cloud guarantee is structural, not a prompt. "
        + ("<b style='color:var(--accent-2)'>Sovereign mode is ON — cloud egress is blocked.</b>"
           if sovereign else "")
        + "</p></form></div>"
    )

    s = cfg.search
    search = (
        "<div class='card'><div class='card-head'><h2>Public search provider</h2></div>"
        "<form method='post' action='/settings/search' class='set-grid'>"
        "<div class='grid cols-2'>"
        + _sel("provider", "Provider", s.provider, [
            ("gemini", "☁ Gemini (google_search — cloud)"),
            ("google_cse", "Google CSE (GOOGLE_API_KEY + GOOGLE_CSE_ID)"),
            ("searxng", "⛨ SearXNG (self-hosted — sovereign)"),
            ("duckduckgo", "DuckDuckGo (keyless)"),
            ("brave", "Brave (BRAVE_API_KEY)"),
            ("serpapi", "SerpAPI (SERPAPI_API_KEY)"),
        ])
        + _sel("onprem_fallback", "On-prem fallback (when policy forbids Gemini)",
               s.onprem_fallback, [
                   ("google_cse", "Google CSE"),
                   ("searxng", "⛨ SearXNG (self-hosted)"),
                   ("duckduckgo", "DuckDuckGo (keyless)"),
                   ("brave", "Brave"),
                   ("serpapi", "SerpAPI"),
               ])
        + "</div>"
        + _num("results", "Results per query", s.results, step="1", mn="1", mx="20")
        + f"<div class='set-actions'>{_key_pill('GOOGLE_CSE_ID', google_cse_id_set)}"
        + f"{_key_pill('BRAVE_API_KEY', brave_key_set)}"
        + f"{_key_pill('SERPAPI_API_KEY', serpapi_key_set)}"
        "<span style='flex:1'></span><button class='btn' type='submit'>Save search</button></div>"
        "<p class='note'>The non-Gemini providers are function tools the reasoning model calls, so "
        "a no-cloud run still reaches the web. Provider keys live in <span class='mono'>.env</span> "
        "(shown only as set / not-set).</p>"
        "</form></div>"
    )

    comp = [k for k in cfg.agents if k.startswith("competitor.")]
    clnt = [k for k in cfg.agents if k.startswith("client.")]
    agents = (
        "<div class='page-head'><div class='grow'><h2>Agents — competitor</h2></div></div>"
        "<div class='grid cols-2'>"
        + "".join(_settings_agent_card(k, cfg.agents[k]) for k in comp)
        + "</div>"
        "<div class='page-head'><div class='grow'><h2>Agents — client</h2></div></div>"
        "<div class='grid cols-2'>"
        + "".join(_settings_agent_card(k, cfg.agents[k]) for k in clnt)
        + "</div>"
    )

    # --- Models · Gemma-4 role tiering (SENTINEL-011) ----------------------------------- #
    role_map = cfg.backend.roles or {}
    tiering_on = bool(role_map)

    # Endpoint placeholder for unset roles: this deployment's own vLLM base, never a baked-in host.
    _ep_hint = cfg.backend.vllm.api_base or "https://your-vllm-host/v1"

    def _role_row(role: str, tier: str, endpoint: str = "") -> str:
        endpoint = endpoint or _ep_hint
        opt = role_map.get(role)
        model_val = escape(opt.model) if opt else ""
        base_val = escape(opt.api_base) if (opt and opt.api_base) else ""
        return (
            "<div class='grid cols-2'>"
            f"<div class='field'><label>{escape(role)} <span class='hint' "
            f"style='font-weight:400'>({escape(tier)})</span></label>"
            f"<input class='input' name='model__{escape(role)}' value='{model_val}' "
            "placeholder='blank ⇒ flat vLLM fallback'></div>"
            f"<div class='field'><label>endpoint</label>"
            f"<input class='input mono' name='api_base__{escape(role)}' value='{base_val}' "
            f"placeholder='{escape(endpoint)}'></div>"
            "</div>"
        )

    models = (
        "<div class='card'><div class='card-head'><h2>Models · Gemma-4 role tiering</h2></div>"
        "<form method='post' action='/settings/models' class='set-grid'>"
        + "".join(_role_row(r, tier) for r, tier in _ROLE_TIERS)
        + f"<div class='set-actions'>{_key_pill('ATCUALITY_API_KEY', atcuality_key_set)}"
        "<span style='flex:1'></span><button class='btn' type='submit'>Save models</button></div>"
        "<p class='note'><b>Capability tiers (verified):</b> tool-callers run on "
        "<span class='mono'>gemma-4-12B</span>; reasoners on <span class='mono'>gemma-4-26B</span> "
        "(structurally tool-free — its native tool-calling is broken). Leave a model blank to use "
        "the flat vLLM backend for that role. "
        + ("<b style='color:var(--accent-2)'>Tiering is ON.</b>" if tiering_on
           else "Tiering is OFF (all roles use the flat vLLM backend).")
        + " The endpoint key lives in <span class='mono'>.env</span> "
        "(<span class='mono'>ATCUALITY_API_KEY</span>), shown only as set / not-set.</p>"
        "</form></div>"
    )

    # --- Coordinator · A2A topology (SENTINEL-011) -------------------------------------- #
    co = cfg.coordinator
    coordinator = (
        "<div class='card'><div class='card-head'><h2>Coordinator · A2A topology</h2></div>"
        "<form method='post' action='/settings/coordinator' class='set-grid'>"
        + _chk("enabled", "coordinator enabled (delegate to specialists via AgentTool)", co.enabled)
        + "<label class='chk' style='opacity:.5'>"
        "<input type='checkbox' disabled> remote private specialist — Phase 2 "
        "(needs a2a-sdk + ADR)</label>"
        "<div class='set-actions'><button class='btn' type='submit'>Save coordinator</button></div>"
        "<p class='note'><b>Ships dark.</b> When off, the deterministic per-mode pipeline runs "
        "(byte-identical to today). When on, a coordinator (12B) plans and delegates to specialist "
        "agents; the private/MCP boundary stays isolated to the private specialist. Remote on-prem "
        "A2A is a gated Phase-2 capability.</p>"
        "</form></div>"
    )

    # --- Strategy · action-plan overlay (SENTINEL-009) ---------------------------------- #
    st = cfg.strategy
    available_pb = [pb.name for pb in discover_playbooks(st.playbook_dir)]
    pb_note = (
        f"Found playbooks in <span class='mono'>{escape(st.playbook_dir)}</span>: "
        + (", ".join(f"<span class='mono'>{escape(n)}</span>" for n in available_pb)
           if available_pb else "<b>none</b>")
    )
    strategy = (
        "<div class='card'><div class='card-head'><h2>Strategy · action plan</h2></div>"
        "<form method='post' action='/settings/strategy' class='set-grid'>"
        + _chk("enabled", "strategy enabled (append a tool-free strategist + merge an action plan)",
               st.enabled)
        + "<div class='grid cols-2'>"
        f"<div class='field'><label for='st_comp'>Competitor playbook (stem)</label>"
        f"<input class='input' id='st_comp' name='competitor_playbook' value='{escape(st.competitor_playbook)}'></div>"
        f"<div class='field'><label for='st_clnt'>Client playbook (stem)</label>"
        f"<input class='input' id='st_clnt' name='client_playbook' value='{escape(st.client_playbook)}'></div>"
        "</div>"
        f"<div class='field'><label for='st_dir'>Playbook directory</label>"
        f"<input class='input' id='st_dir' name='playbook_dir' value='{escape(st.playbook_dir)}'></div>"
        "<div class='set-actions'><button class='btn' type='submit'>Save strategy</button></div>"
        f"<p class='note'><b>Ships dark.</b> When on, a tool-free strategist reads the finished "
        "artifact and a deterministic merge adds an assessment + prioritized action plan (client: "
        "+ objection handling), shaped by an admin-editable Markdown playbook — change house "
        f"strategy by editing a <span class='mono'>.md</span>, effective next run. {pb_note}.</p>"
        "</form></div>"
    )

    prompts = (
        "<div class='page-head'><div class='grow'><h2>Prompts</h2></div></div>"
        + "".join(_prompt_card(k, cfg.prompts[k]) for k in cfg.prompts)
    )

    _pw_msg = (f"<div class='banner ok'>{escape(password_ok)}</div>" if password_ok
               else (f"<div class='banner bad'>{escape(password_err)}</div>" if password_err else ""))
    security = (
        "<div class='card'><div class='card-head'>"
        + _icon('lock') + "<h2>Security · password</h2></div>"
        + _pw_msg
        + "<form method='post' action='/settings/password' class='set-grid'>"
        "<div class='grid cols-2'>"
        "<div class='field'><label for='sec_cur'>Current password</label>"
        "<input class='input' type='password' id='sec_cur' name='current_password' autocomplete='current-password' required></div>"
        "<div class='field'><label for='sec_new'>New password <span class='hint'>(min 8 chars)</span></label>"
        "<input class='input' type='password' id='sec_new' name='new_password' autocomplete='new-password' required></div>"
        "</div>"
        "<div class='field'><label for='sec_cfm'>Confirm new password</label>"
        "<input class='input' type='password' id='sec_cfm' name='confirm_password' autocomplete='new-password' required></div>"
        "<div class='set-actions'><button class='btn' type='submit'>Change password</button></div>"
        "<p class='note'>Changes take effect immediately. All active sessions remain valid.</p>"
        "</form></div>"
    )

    # ── External MCP servers — compact status rows + enable toggle ───────────
    mcp_rows = mcp_rows or []
    mcp_items = ""
    for i, r in enumerate(mcp_rows):
        cfg_chip = (
            "<span class='badge ok'>"
            f"{escape(r['secret_env'])} set</span>" if r["configured"] else
            "<span class='badge bad'>"
            f"{escape(r['secret_env'])} not set</span>"
        )
        scope = ", ".join(r["domains"]) if r["domains"] else "all domains"
        tools = ", ".join(r["tools"][:5]) if r["tools"] else "all tools"
        divider = "<div class='divider'></div>" if i else ""
        mcp_items += (
            divider
            + "<div class='row-between' style='flex-wrap:wrap'>"
            "<div class='inline'>"
            f"<b class='mono'>{escape(r['name'])}</b>"
            f"<span class='pv'>{escape(r['transport'])}</span>{cfg_chip}"
            f"<span class='muted' style='font-size:12px'>{escape(r['description'])} "
            f"· scope: {escape(scope)} · tools: {escape(tools)}</span></div>"
            f"<form method='post' action='/settings/mcp/{escape(r['name'])}' style='display:inline'>"
            f"<input type='hidden' name='enabled' value='{'' if r['enabled'] else '1'}'>"
            f"<button class='btn sm {'ghost' if r['enabled'] else 'ok'}' type='submit'>"
            f"{'Enable' if not r['enabled'] else 'Disable'}</button></form>"
            "</div>"
        )
    mcp_section = ""
    if mcp_items:
        mcp_section = (
            "<div class='card'><div class='card-head'><h2>MCP servers</h2></div>"
            "<div class='stack'>" + mcp_items + "</div>"
            "<p class='note' style='margin-top:8px'>External tool servers research agents can "
            "call (Model Context Protocol). Keys live in <span class='mono'>.env</span> — a "
            "server without its key is skipped automatically. Sovereign runs never use these "
            "(cloud egress). Edit domains/tool filters in "
            "<span class='mono'>sentinel.config.yaml</span>.</p></div>"
        )

    memory_sources = (
        "<div class='card' id='memory-sources'>"
        "<div class='card-head'><h2>Memory Sources</h2></div>"
        "<p class='note' style='margin:0 0 12px'>Configure which external sources feed each "
        "company's knowledge graph. Per-company source configuration is available on the "
        "project Memory tab — open a project and select the Memory tab.</p>"
        "<div class='stack'>"
        "<div class='inline'>"
        "<span class='badge badge-website'>🌐 Website</span>"
        "<span style='font-size:13px'>Public web crawl of the company's primary domain.</span>"
        "</div>"
        "<div class='divider'></div>"
        "<div class='inline'>"
        "<span class='badge badge-youtube'>▶ YouTube</span>"
        "<span style='font-size:13px'>Earnings calls, keynotes, and product demos.</span>"
        "</div>"
        "<div class='divider'></div>"
        "<div class='inline'>"
        "<span class='badge badge-email'>✉ Email</span>"
        "<span class='badge badge-private'>PRIVATE</span>"
        "<span style='font-size:13px'>Scoped to authorized mailboxes only — never crosses "
        "to public recall.</span>"
        "</div>"
        "<div class='divider'></div>"
        "<div class='inline'>"
        "<span class='badge badge-social'>📢 Social</span>"
        "<span style='font-size:13px'>LinkedIn posts and public social media signals.</span>"
        "</div>"
        "<div class='divider'></div>"
        "<div class='inline'>"
        "<span class='badge badge-research'>🔬 Research</span>"
        "<span style='font-size:13px'>Synthesized findings from Sentinel research runs.</span>"
        "</div>"
        "</div></div>"
    )

    page_head = (
        "<div class='page-head'><div class='grow'><h1>Settings</h1>"
        "<p>Backends, governance, search, and memory for this instance.</p></div></div>"
    )
    # OD settings layout = a 2-col .split of two card stacks. Form-heavy cards go
    # in the wider (2fr) left column; toggle/list cards in the 1fr right column.
    content = (
        page_head + banner
        + "<div class='split' style='align-items:start'>"
        + "<div class='stack' style='gap:var(--sp-5)'>"
        + backends + models + coordinator + generation + agents + prompts
        + "</div>"
        + "<div class='stack' style='gap:var(--sp-5)'>"
        + governance + search + mcp_section + strategy + memory + harness + security
        + memory_sources
        + "</div>"
        + "</div>"
    )
    return shell(active="settings", title="Settings", content=content, backend=backend)


def error_page(message: str, *, hint: str = "", backend: str = "gemini") -> str:
    hint_html = f"<p class='note'>{escape(hint)}</p>" if hint else ""
    content = (f"<div class='card'><div class='card-head'><h2 style='color:var(--bad)'>Run failed</h2></div>"
               f"<p>{escape(message)}</p>{hint_html}"
               "<p class='note'><a href='/projects'>← Back to New Run</a></p></div>")
    return shell(active="new", title="Error", content=content, backend=backend)


def episodes_page(records: list, *, backend: str, ok: str = "", err: str = "") -> str:
    """Episodic memory viewer + CRUD — list all run records with delete controls (SENTINEL-015).

    Each row shows: entity, mode, backend, finding count, created_at, and a delete button.
    Deleting a run record removes it from episodic recall permanently.
    """
    banner = ""
    if ok:
        banner = f"<div class='card banner ok'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad'>{escape(err)}</div>"

    def _row(r) -> str:
        ts = str(r.created_at or "")[:16]
        n_findings = len(getattr(r, "finding_texts", []) or [])
        run_id = escape(str(r.id))
        return (
            f"<tr>"
            f"<td>{escape(r.entity)}</td>"
            f"<td><span class='badge neutral'>{escape(r.mode)}</span></td>"
            f"<td class='mono'>{escape(r.backend)}</td>"
            f"<td class='num'>{n_findings}</td>"
            f"<td class='muted'>{ts}</td>"
            f"<td>"
            f"<form method='post' action='/memory/episodes/{run_id}/delete' "
            f"onsubmit=\"return confirm('Delete this run record from episodic memory?')\">"
            f"<button type='submit' class='btn sm danger'>Delete</button>"
            f"</form>"
            f"</td>"
            f"</tr>"
        )

    if records:
        rows = "".join(_row(r) for r in records)
        table = (
            "<div class='table-wrap'><table class='table'>"
            "<thead><tr>"
            "<th>Entity</th>"
            "<th>Mode</th>"
            "<th>Backend</th>"
            "<th class='num'>Findings</th>"
            "<th>Created</th>"
            "<th>Action</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table></div>"
        )
    else:
        table = (
            "<div class='empty'>"
            f"<div class='ico'>{_icon('brain')}</div>"
            "No run records yet. Run a research task to populate episodic memory.</div>"
        )

    content = (
        banner
        + "<div class='page-head'><div class='grow'><h1>Episodic Memory — Run Records</h1>"
        + f"<p>{len(records)} run record(s). Deleting a record removes it from episodic recall "
        + "— the entity's accumulated memory is unaffected.</p></div>"
        + "<a class='btn ghost' href='/settings#memory'>← Settings</a></div>"
        + "<div class='card'><div class='card-head'><h2>All episodes</h2>"
        + f"<span class='pill'>{len(records)} records</span></div>" + table + "</div>"
    )
    return shell(active="settings", title="Episodic Memory", content=content, backend=backend)


# --------------------------------------------------------------------------- #
# Prompts CRUD page — dedicated management for all 49 agent prompt templates
# --------------------------------------------------------------------------- #

# Role badges: colour-coded so planner/research/synthesizer are visually distinct at a glance.
_ROLE_COLOURS: dict[str, tuple[str, str]] = {
    "planner":          ("#8ab4f8", "rgba(66,133,244,.18)"),
    "public_research":  ("#4ea1ff", "rgba(22,100,220,.18)"),
    "private_research": ("#ffb24d", "rgba(255,170,60,.16)"),
    "extractor":        ("#81c995", "rgba(52,168,83,.16)"),
    "synthesizer":      ("#c58af9", "rgba(161,66,244,.18)"),
    "strategist":       ("#f28b82", "rgba(234,67,53,.16)"),
    "coordinator":      ("#fdd663", "rgba(251,188,4,.16)"),
}
