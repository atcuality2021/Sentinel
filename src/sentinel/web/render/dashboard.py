"""render.dashboard — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .accounts import _run_href
from .base import _CHARTJS, _icon, _kpi, shell
from .focus import focus_card

def dashboard_page(*, stats: dict, charts: dict, recent: list[dict], backend: str,
                   focus: list | None = None, project_by_entity: dict | None = None) -> str:
    kpis = (
        "<div class='grid kpis'>"
        + _kpi("run", "Runs (session)", stats["runs"], "spark")
        + _kpi("art", "Artifacts", stats["artifacts"], "doc")
        + _kpi("pub", "Public findings", stats["public"], "globe")
        + _kpi("priv", "Private findings", stats["private"], "lock")
        + "</div>"
    )

    has_data = stats["runs"] > 0
    if has_data:
        charts_html = (
            "<div class='grid charts' style='margin-top:16px'>"
            "<div class='card'><h3 class='ch'>Signal provenance</h3>"
            "<div class='chart-wrap'><canvas id='cProv'></canvas></div></div>"
            "<div class='card'><h3 class='ch'>Runs by mode</h3>"
            "<div class='chart-wrap'><canvas id='cMode'></canvas></div></div>"
            "<div class='card'><h3 class='ch'>Backend usage</h3>"
            "<div class='chart-wrap'><canvas id='cBack'></canvas></div></div>"
            "</div>"
        )
    else:
        charts_html = (
            "<div class='card' style='margin-top:16px'><div class='empty'>"
            "No runs yet. <a href='/projects' style='color:var(--accent-2)'>Run your first "
            "intelligence task</a> — the charts populate live, including the public vs "
            "private provenance split.</div></div>"
        )

    rows = ""
    for r in recent:
        name = escape(r["target"])
        if r.get("project_id") or r.get("entity"):
            name = (f"<a href='{_run_href(r)}' "
                    f"style='color:var(--accent-2)'>{name}</a>")
        rows += (
            f"<tr><td><b>{name}</b></td>"
            f"<td>{escape(r['mode'])}</td>"
            f"<td><span class='dotmark {'v' if r['backend']=='vllm' else 'g'}'></span> "
            f"<span class='mono'>{escape(r['backend'])}</span></td>"
            f"<td><span class='badge public'>{r['public']}</span>"
            f"<span class='badge private'>{r['private']}</span></td>"
            f"<td class='mono'>{escape(r['when'])}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='5' class='mono'>—</td></tr>"
    table = (
        "<div class='section-h'><h2>Recent runs</h2>"
        "<a class='btn ghost' href='/artifacts'>View all</a></div>"
        "<div class='card' style='padding:6px 8px'><table>"
        "<thead><tr><th>Target</th><th>Mode</th><th>Backend</th>"
        "<th>Public / Private</th><th>When</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )

    scripts = ""
    if has_data:
        data = json.dumps(charts)
        js = (
            "<script src='" + _CHARTJS + "'></script><script>"
            "const D=__DATA__;"
            "const _C=getComputedStyle(document.documentElement),"
            "MUT=(_C.getPropertyValue('--muted')||'#8b97a8').trim(),"
            "GRID=(_C.getPropertyValue('--line')||'#1e2940').trim(),"
            "PANEL=(_C.getPropertyValue('--panel')||'#0e1420').trim();"
            "const T={plugins:{legend:{labels:{color:MUT,boxWidth:12,font:{size:11}}}}};"
            "function donut(id,labels,vals,colors){new Chart(document.getElementById(id),"
            "{type:'doughnut',data:{labels:labels,datasets:[{data:vals,backgroundColor:colors,"
            "borderColor:PANEL,borderWidth:2}]},options:{...T,cutout:'62%',"
            "plugins:{legend:{position:'bottom',labels:{color:MUT,boxWidth:12,font:{size:11}}}}}});}"
            "donut('cProv',['Public','Private'],[D.provenance.public,D.provenance.private],"
            "['#4ea1ff','#ffb24d']);"
            "donut('cBack',['Gemini','Gemma/vLLM'],[D.backends.gemini,D.backends.vllm],"
            "['#4ea1ff','#ffb24d']);"
            "new Chart(document.getElementById('cMode'),{type:'bar',data:{labels:['Competitor','Client'],"
            "datasets:[{data:[D.modes.competitor,D.modes.client],backgroundColor:['#4285f4','#34a853'],"
            "borderRadius:6,barThickness:46}]},options:{...T,plugins:{legend:{display:false}},"
            "scales:{x:{ticks:{color:MUT},grid:{display:false}},"
            "y:{ticks:{color:MUT,precision:0},grid:{color:GRID}}}}});"
            "</script>"
        )
        scripts = js.replace("__DATA__", data)

    focus_html = focus_card(focus, project_by_entity) if focus else ""
    content = kpis + charts_html + focus_html + table
    return shell(active="dashboard", title="Dashboard", content=content, backend=backend,
                 body_scripts=scripts)


# --------------------------------------------------------------------------- #
# New-run form
# --------------------------------------------------------------------------- #
def form_page(*, default_backend: str, private_configured: bool, vllm_model: str,
              sovereign: bool = False) -> str:
    priv = (
        "<span class='badge private'>private</span> Workspace MCP connected"
        if private_configured
        else "<span class='badge private'>private</span> not connected — client mode "
        "degrades gracefully (public-only, gap flagged)"
    )
    # Governance overrides the toggle: in on_prem_required, cloud is blocked structurally, so the
    # run form must not offer Gemini — disable it and force on-prem, so the UI can't lie.
    if sovereign:
        gemini_checked, vllm_checked = "", "checked"
    else:
        gemini_checked = "checked" if default_backend != "vllm" else ""
        vllm_checked = "checked" if default_backend == "vllm" else ""
    gemini_disabled = "disabled" if sovereign else ""
    sovereign_chip = (
        "<span class='pill' style='border-color:var(--accent-2)'>"
        "<span class='dotmark v'></span>🔒 Sovereign — <b>cloud blocked by governance</b></span>"
        if sovereign else ""
    )
    sovereign_note = (
        "<b style='color:var(--accent-2)'>Governance is set to on_prem_required</b> — this run is "
        "forced on-prem (no Gemini, non-cloud search), regardless of the toggle. "
        if sovereign else ""
    )
    content = f"""
    <div class='card'>
      <form class='run' method='post' action='/run'>
        <div>
          <label class='lbl' for='target'>Target</label>
          <input id='target' name='target' placeholder='e.g. Stripe, or an account name'
                 required autofocus>
        </div>
        <div class='row2'>
          <div>
            <label class='lbl' for='mode'>Mode</label>
            <select id='mode' name='mode'>
              <option value='competitor'>Competitor → Battlecard</option>
              <option value='client'>Client / Account → Brief</option>
            </select>
          </div>
          <div>
            <label class='lbl' for='vertical'>Vertical (optional)</label>
            <input id='vertical' name='vertical' placeholder='e.g. BFSI, healthcare'>
          </div>
        </div>
        <div>
          <label class='lbl'>Reasoning backend</label>
          <div class='seg'>
            <input class='cloud' type='radio' id='b-gemini' name='backend' value='gemini' {gemini_checked} {gemini_disabled}>
            <label class='l-cloud' for='b-gemini'>☁ Cloud · Gemini<span class='sub'>managed API</span></label>
            <input class='onprem' type='radio' id='b-vllm' name='backend' value='vllm' {vllm_checked}>
            <label class='l-onprem' for='b-vllm'>🔒 On-prem · Gemma<span class='sub'>{escape(vllm_model)} · vLLM</span></label>
          </div>
        </div>
        <div><button class='btn' type='submit'>{_icon('bolt')} Run Sentinel</button></div>
      </form>
      <div style='margin-top:16px;display:flex;gap:10px;flex-wrap:wrap'>
        <span class='pill'>Default: <b>{escape(default_backend)}</b></span>
        <span class='pill'>{priv}</span>
        {sovereign_chip}
      </div>
    </div>
    <p class='note' style='margin-top:16px'>{sovereign_note}The <b>reasoning backend</b> toggle swaps
    the LLM that plans and synthesizes — and, in client mode, reads your private CRM data.
    <b>On-prem · Gemma</b> runs that reasoning on your own GPUs via vLLM; public web grounding
    uses the configured search provider. Same agent, same code — config-only swap.</p>
    """
    return shell(active="new", title="New Run", content=content, backend=default_backend)
