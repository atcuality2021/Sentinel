"""Dashboard UI for Sentinel — app shell, pages, and artifact rendering.

Presentation-only. An app shell (collapsible sidebar + top bar) wraps every page. The
dashboard home shows KPI cards and charts driven by an in-memory run store; the signature
chart is the public-vs-private *provenance* split — the sovereignty thesis as a number.

All model/user-derived text is passed through ``html.escape`` (artifacts are built from web
search + model output, so they are untrusted by default — no stored XSS via a finding).
"""

from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

from sentinel.artifacts.schemas import AccountBrief, Battlecard, Boundary, Finding, Gap, Source
from sentinel.strategy import discover_playbooks

# Chart.js from CDN — modern interactive charts without bundling. Demo runs online.
_CHARTJS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

CSS = """
:root{
  --bg:#0b0e14; --panel:#151a23; --panel-2:#11151d; --rail:#0c0f16; --ink:#e8eaed;
  --muted:#9aa0a6; --line:#2a2f3a; --public:#4ea1ff; --public-bg:#11233d; --private:#ffb24d;
  --private-bg:#2e2410; --accent:#4285f4; --accent-2:#8ab4f8; --ok:#34a853; --bad:#ea4335;
  --chip:#1b212c; --accent-soft:rgba(66,133,244,.14); --accent-line:#2c4a7a;
}
*{box-sizing:border-box} html,body{margin:0;height:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--ink);font:14.5px/1.55 -apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}

/* ---- shell ---- */
.shell{display:grid;grid-template-columns:248px 1fr;min-height:100vh;transition:grid-template-columns .18s ease}
.shell.collapsed{grid-template-columns:72px 1fr}
.sidebar{background:var(--rail);border-right:1px solid var(--line);display:flex;flex-direction:column;
  position:sticky;top:0;height:100vh;overflow:hidden}
.side-top{display:flex;align-items:center;gap:11px;padding:18px 16px 12px}
.dot{width:13px;height:13px;border-radius:50%;background:var(--accent);box-shadow:0 0 16px var(--accent);flex:0 0 auto}
.brand-text{font-weight:700;letter-spacing:.3px;font-size:16px;white-space:nowrap}
.navToggle{margin-left:auto;background:transparent;border:1px solid var(--line);color:var(--muted);
  width:30px;height:30px;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.navToggle:hover{color:var(--ink);border-color:var(--accent)}
.shell.collapsed .side-top{justify-content:center;padding:18px 0 12px}
.shell.collapsed .brand-text,.shell.collapsed .brand-mark,.shell.collapsed .nav-label,
.shell.collapsed .side-foot,.shell.collapsed .nav-group-label{display:none}
/* keep the toggle visible when collapsed — it is the only way back to expanded */
.shell.collapsed .navToggle{margin:0 auto}
nav{padding:10px 10px;display:flex;flex-direction:column;gap:3px;margin-top:6px}
.nav-group-label{color:var(--muted);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;
  padding:12px 12px 6px}
.nav-item{display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;color:var(--muted);
  white-space:nowrap;cursor:pointer;border:1px solid transparent}
.nav-item svg{flex:0 0 auto}
.nav-item:hover{background:var(--panel);color:var(--ink)}
.nav-item.active{background:linear-gradient(90deg,rgba(66,133,244,.20),rgba(66,133,244,.05));
  color:var(--ink);border-color:var(--accent-line)}
.nav-item.active svg{color:var(--accent-2)}
.shell.collapsed .nav-item{justify-content:center;padding:10px 0}
.side-foot{margin-top:auto;padding:14px 16px;color:var(--muted);font-size:11.5px;border-top:1px solid var(--line)}

/* ---- main ---- */
.main{min-width:0;display:flex;flex-direction:column}
.topbar{border-bottom:1px solid var(--line);position:sticky;top:0;
  background:rgba(10,14,22,.82);backdrop-filter:blur(8px);z-index:5}
.topbar-inner{max-width:1280px;margin:0 auto;width:100%;display:flex;align-items:center;
  gap:14px;padding:15px 26px}
.topbar h1{font-size:17px;margin:0;font-weight:600}
.topbar .spacer{flex:1}
.content{padding:24px 26px 64px;max-width:1280px;margin:0 auto;width:100%;min-width:0}

/* ---- pills / badges ---- */
.pill{font-size:12px;color:var(--muted);background:var(--panel-2);border:1px solid var(--line);
  padding:5px 11px;border-radius:999px;display:inline-flex;align-items:center;gap:7px}
.pill b{color:var(--ink);font-weight:600}
.dotmark{width:7px;height:7px;border-radius:50%;display:inline-block}
.dotmark.g{background:var(--public)} .dotmark.v{background:var(--private)}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
  padding:2px 8px;border-radius:999px;margin-right:9px;vertical-align:1px}
.badge.public{color:var(--public);background:var(--public-bg);border:1px solid #21456f}
.badge.private{color:var(--private);background:var(--private-bg);border:1px solid #5a4413}
.btn{background:var(--accent);color:#fff;border:0;padding:11px 16px;border-radius:10px;font-size:14px;
  font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:8px}
.btn:hover{filter:brightness(1.08)} .btn.ghost{background:var(--panel);border:1px solid var(--line);color:var(--ink)}

/* ---- cards / grid ---- */
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px}
.grid{display:grid;gap:16px}
.kpis{grid-template-columns:repeat(4,1fr)}
.kpi .k-top{display:flex;align-items:center;justify-content:space-between;color:var(--muted);font-size:12.5px}
.kpi .k-val{font-size:30px;font-weight:700;margin-top:8px;letter-spacing:.5px}
.kpi .k-accent{width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center}
.kpi.pub .k-accent{background:var(--public-bg);color:var(--public)}
.kpi.priv .k-accent{background:var(--private-bg);color:var(--private)}
.kpi.run .k-accent{background:var(--accent-soft);color:var(--accent-2)}
.kpi.art .k-accent{background:rgba(58,210,159,.14);color:var(--ok)}
.charts{grid-template-columns:1.2fr 1fr 1fr}
.card h3.ch{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:0 0 12px}
.chart-wrap{position:relative;height:200px}
.empty{color:var(--muted);font-size:13px;text-align:center;padding:48px 10px;border:1px dashed var(--line);
  border-radius:12px}
.section-h{display:flex;align-items:center;justify-content:space-between;margin:26px 0 12px}
.section-h h2{font-size:15px;margin:0}

/* ---- table ---- */
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.08em;padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:11px 12px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:var(--muted);
  overflow-wrap:anywhere}

/* ---- form ---- */
form.run{display:grid;gap:15px;max-width:680px}
label.lbl{font-size:11.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);display:block;margin-bottom:7px}
input,select{width:100%;background:var(--panel-2);border:1px solid var(--line);color:var(--ink);
  padding:11px 12px;border-radius:10px;font-size:14.5px}
input:focus,select:focus{outline:none;border-color:var(--accent)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:15px}
.seg{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:11px;overflow:hidden}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{display:block;text-align:center;padding:14px 12px;cursor:pointer;color:var(--muted);
  background:var(--panel-2);font-size:14px;transition:background .15s,box-shadow .15s,color .15s}
.seg label .sub{display:block;font-size:11px;margin-top:3px;opacity:.85;font-family:ui-monospace,Menlo,monospace}
.seg label.l-cloud{border-right:1px solid var(--line)}
.seg input.cloud:checked + label{background:var(--public-bg);color:#dcebff;box-shadow:inset 0 0 0 2px var(--public)}
.seg input.onprem:checked + label{background:var(--private-bg);color:#ffe9c9;box-shadow:inset 0 0 0 2px var(--private)}
.note{color:var(--muted);font-size:13px;max-width:680px;overflow-wrap:anywhere}
textarea{width:100%;background:var(--panel-2);border:1px solid var(--line);color:var(--ink);
  padding:11px 12px;border-radius:10px;font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
  resize:vertical;min-height:120px}
textarea:focus{outline:none;border-color:var(--accent)}
.set-grid{display:grid;gap:16px;max-width:760px}
.row4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.chk{display:flex;align-items:center;gap:9px;color:var(--ink);font-size:13.5px}
.chk input{width:auto}
.banner{margin-bottom:18px} .banner.ok{border-color:#1d5a44;background:#0e1f19}
.banner.bad{border-color:#5a1f1f;background:#1c1011}
.set-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}
.varsHint{color:var(--muted);font-size:12px;margin:8px 0 0;font-family:ui-monospace,Menlo,monospace}
.agent-key{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--accent-2)}
@media(max-width:880px){.row4{grid-template-columns:1fr 1fr}}

/* ---- artifact ---- */
.summary{font-size:17px;border-left:3px solid var(--accent);padding-left:14px;margin:8px 0 6px}
h2.sec{font-size:13px;text-transform:uppercase;letter-spacing:.11em;color:var(--muted);margin:22px 0 10px}
ul.find{list-style:none;padding:0;margin:0}
ul.find li{padding:11px 0;border-bottom:1px solid var(--line)} ul.find li:last-child{border-bottom:0}
.src{color:var(--muted);font-size:12.5px;margin-left:2px}
.src a{color:var(--public)} .src a:hover{text-decoration:underline}
ul.plain{margin:0;padding-left:20px} ul.plain li{margin:7px 0}
.gap{color:var(--private)}
.trace{font:12px/1.5 ui-monospace,Menlo,monospace;color:var(--muted);white-space:pre-wrap;
  background:var(--panel-2);border:1px solid var(--line);border-radius:10px;padding:14px;max-height:240px;overflow:auto}
details summary{cursor:pointer;color:var(--muted);font-size:13px}
.err{border-color:#5a1f1f;background:#1c1011}
.two-col{display:grid;grid-template-columns:1fr 300px;gap:18px;align-items:start}
@media(max-width:880px){.kpis{grid-template-columns:repeat(2,1fr)}.charts{grid-template-columns:1fr}
  .two-col{grid-template-columns:1fr}}

/* ---- console chrome (Google Cloud Agent Platform look) ---- */
.brand-mark{width:24px;height:24px;border-radius:7px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,var(--accent),#a142f4);color:#fff;flex:0 0 auto;font-weight:800;font-size:13px}
.crumb{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:13px}
.crumb .sep{opacity:.5}
.proj-pill{font-size:12px;color:var(--ink);background:var(--chip);border:1px solid var(--line);
  padding:5px 11px;border-radius:8px;display:inline-flex;align-items:center;gap:7px}
.icon-btn{background:transparent;border:1px solid var(--line);color:var(--muted);width:34px;height:34px;
  border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:pointer}
.icon-btn:hover{color:var(--ink);border-color:var(--accent-line)}

/* ---- hero ---- */
.hero{text-align:center;padding:30px 16px 8px}
.hero h1{font-size:34px;margin:0 0 8px;font-weight:700;letter-spacing:-.4px}
.hero p{color:var(--muted);font-size:15px;margin:0 auto;max-width:560px}
.hero.left{text-align:left;padding:6px 0 14px}
.hero.left h1{font-size:26px}

/* ---- preview / status badges ---- */
.pv{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;
  border-radius:6px;background:var(--accent-soft);color:var(--accent-2);border:1px solid var(--accent-line);
  vertical-align:middle;margin-left:8px}
.pv.live{background:rgba(52,168,83,.14);color:#5bd07f;border-color:#1f6b3e}
.pv.dark{background:#1a1f29;color:var(--muted);border-color:var(--line)}

/* ---- console cards (model/agent gallery) ---- */
.cards3{grid-template-columns:repeat(3,1fr)} .cards2{grid-template-columns:1fr 1fr}
.gc{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 18px;
  display:flex;flex-direction:column;gap:8px;transition:border-color .15s,transform .15s}
a.gc:hover{border-color:var(--accent-line);transform:translateY(-2px)}
.gc .gc-ico{width:38px;height:38px;border-radius:10px;background:var(--accent-soft);color:var(--accent-2);
  display:flex;align-items:center;justify-content:center}
.gc .gc-t{font-size:15px;font-weight:650;display:flex;align-items:center}
.gc .gc-d{color:var(--muted);font-size:13px;line-height:1.5}
.gc .gc-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:auto;padding-top:6px}
.tag{font-size:11px;color:var(--muted);background:var(--chip);border:1px solid var(--line);
  padding:2px 8px;border-radius:6px;font-family:ui-monospace,Menlo,monospace}

/* ---- agent flow graph ---- */
.flowwrap{overflow-x:auto;padding:6px 2px 14px}
.flow{display:flex;align-items:stretch;gap:0;min-width:max-content}
.node{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 15px;
  min-width:178px;display:flex;flex-direction:column;gap:6px;position:relative}
.node.dark{opacity:.55;border-style:dashed}
.node .n-top{display:flex;align-items:center;gap:8px}
.node .n-ico{width:26px;height:26px;border-radius:8px;display:flex;align-items:center;justify-content:center;
  background:var(--accent-soft);color:var(--accent-2)}
.node.reason .n-ico{background:rgba(161,66,244,.16);color:#c08cf7}
.node.private .n-ico{background:var(--private-bg);color:var(--private)}
.node .n-name{font-weight:650;font-size:13.5px}
.node .n-role{color:var(--muted);font-size:11.5px;font-family:ui-monospace,Menlo,monospace}
.node .n-meta{font-size:11px;color:var(--muted)}
.node .n-out{font-size:11px;color:var(--accent-2);font-family:ui-monospace,Menlo,monospace}
.arrow{display:flex;align-items:center;color:var(--muted);padding:0 4px;flex:0 0 auto}
.lane-h{display:flex;align-items:center;gap:10px;margin:20px 0 10px}
.lane-h h2{font-size:16px;margin:0} .lane-h .mut{color:var(--muted);font-size:13px}
.rail{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.rail .step{font-size:12px;color:var(--muted);background:var(--panel-2);border:1px solid var(--line);
  border-radius:999px;padding:6px 12px;display:inline-flex;align-items:center;gap:7px}
.rail .step b{color:var(--ink);font-weight:600}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12.5px;margin-top:6px}
.legend span{display:inline-flex;align-items:center;gap:7px}
.swatch{width:11px;height:11px;border-radius:4px;display:inline-block}
@media(max-width:880px){.cards3,.cards2{grid-template-columns:1fr}}
"""

# --------------------------------------------------------------------------- #
# Icons (inline SVG, currentColor)
# --------------------------------------------------------------------------- #
def _icon(name: str) -> str:
    p = {
        "grid": "<rect x='3' y='3' width='7' height='7' rx='1'/><rect x='14' y='3' width='7' height='7' rx='1'/><rect x='3' y='14' width='7' height='7' rx='1'/><rect x='14' y='14' width='7' height='7' rx='1'/>",
        "search": "<circle cx='11' cy='11' r='7'/><path d='M21 21l-4.3-4.3'/>",
        "doc": "<path d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/><path d='M14 3v5h5'/>",
        "chip": "<rect x='6' y='6' width='12' height='12' rx='2'/><path d='M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3'/>",
        "flow": "<rect x='3' y='3' width='6' height='6' rx='1'/><rect x='15' y='15' width='6' height='6' rx='1'/><path d='M9 6h6a3 3 0 0 1 3 3v6'/>",
        "menu": "<path d='M3 6h18M3 12h18M3 18h18'/>",
        "bolt": "<path d='M13 2L3 14h7l-1 8 10-12h-7z'/>",
        "globe": "<circle cx='12' cy='12' r='9'/><path d='M3 12h18M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18'/>",
        "lock": "<rect x='4' y='10' width='16' height='10' rx='2'/><path d='M8 10V7a4 4 0 0 1 8 0v3'/>",
        "spark": "<path d='M12 3v6M12 15v6M3 12h6M15 12h6'/>",
        "cog": "<circle cx='12' cy='12' r='3'/><path d='M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'/>",
        "users": "<path d='M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2'/><circle cx='9' cy='7' r='4'/><path d='M22 21v-2a4 4 0 0 0-3-3.87'/><path d='M16 3.13a4 4 0 0 1 0 7.75'/>",
        "agent": "<rect x='4' y='8' width='16' height='12' rx='3'/><path d='M12 8V4M9 4h6'/><circle cx='9' cy='14' r='1.2'/><circle cx='15' cy='14' r='1.2'/>",
        "plan": "<path d='M9 11l3 3L22 4'/><path d='M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'/>",
        "merge": "<path d='M6 3v6a6 6 0 0 0 6 6h6'/><path d='M6 21v-6'/><circle cx='6' cy='4' r='2'/><circle cx='6' cy='20' r='2'/><circle cx='20' cy='15' r='2'/>",
        "shield": "<path d='M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z'/>",
        "play": "<path d='M5 3l14 9-14 9z'/>",
    }.get(name, "")
    return (
        f"<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>{p}</svg>"
    )


# Grouped navigation, mirroring the Google Cloud Agent Platform console (Build / Scale / Govern /
# Optimize). Each item: (key, label, icon, href). The key matches the page's ``active`` marker.
_NAV_GROUPS = [
    ("Build", [
        ("dashboard", "Dashboard", "grid", "/"),
        ("projects", "Projects", "plan", "/projects"),
        ("agents", "Agents", "agent", "/agents"),
        ("new", "New Run", "search", "/new"),
    ]),
    ("Scale", [
        ("accounts", "Accounts", "users", "/accounts"),
        ("artifacts", "Artifacts", "doc", "/artifacts"),
    ]),
    ("Govern", [
        ("backends", "Backends", "chip", "/backends"),
        ("settings", "Settings", "cog", "/settings"),
    ]),
    ("Optimize", [
        ("focus", "Focus", "spark", "/focus"),
    ]),
]


def _sidebar(active: str) -> str:
    blocks = []
    for group, items in _NAV_GROUPS:
        rows = []
        for key, label, icon, href in items:
            cls = "nav-item active" if key == active else "nav-item"
            rows.append(
                f"<a class='{cls}' href='{href}' title='{label}'>{_icon(icon)}"
                f"<span class='nav-label'>{label}</span></a>"
            )
        blocks.append(
            f"<div class='nav-group-label'>{group}</div><nav>{''.join(rows)}</nav>"
        )
    return (
        "<aside class='sidebar'>"
        "<div class='side-top'><span class='brand-mark'>S</span>"
        "<span class='brand-text'>Sentinel</span>"
        "<button class='navToggle' id='navToggle' aria-label='Toggle menu'>"
        f"{_icon('menu')}</button></div>"
        f"{''.join(blocks)}"
        "<div class='side-foot'>Sovereign Intelligence Agent<br>Public &amp; private signal, "
        "separated by design.</div>"
        "</aside>"
    )


_COLLAPSE_JS = """
(function(){var KEY='sentinel-nav-collapsed';var s=document.getElementById('shell');
if(localStorage.getItem(KEY)==='1')s.classList.add('collapsed');
var b=document.getElementById('navToggle');if(b)b.addEventListener('click',function(){
s.classList.toggle('collapsed');localStorage.setItem(KEY,s.classList.contains('collapsed')?'1':'0');});})();
"""

# A full-screen loading overlay shown while a form POSTs (planning/running take ~seconds on the live
# engine) — so a click gives immediate feedback instead of a frozen page. The submit button's own label
# becomes the spinner message ("Approve & run…", "Plan task…").
_LOADER_HTML = (
    "<style>@keyframes spin{to{transform:rotate(360deg)}}</style>"
    "<div id='ld' style='position:fixed;inset:0;display:none;z-index:60;"
    "background:rgba(8,10,14,.74);align-items:center;justify-content:center'>"
    "<div style='text-align:center;color:#e6e8ee'>"
    "<div style='width:44px;height:44px;border:3px solid rgba(255,255,255,.15);border-top-color:#4285f4;"
    "border-radius:50%;margin:0 auto 14px;animation:spin .9s linear infinite'></div>"
    "<div id='ldmsg' style='font-weight:600'>Working…</div>"
    "<div style='color:#8b93a7;font-size:13px;margin-top:4px'>"
    "agents are running on the sovereign engine — this can take a few seconds</div></div></div>"
)
_LOADER_JS = """
(function(){var o=document.getElementById('ld');if(!o)return;
document.querySelectorAll('form').forEach(function(f){f.addEventListener('submit',function(){
var b=f.querySelector('button[type=submit],button:not([type])');var m=document.getElementById('ldmsg');
if(m&&b&&b.textContent)m.textContent=b.textContent.trim()+'\\u2026';o.style.display='flex';});});})();
"""


def shell(*, active: str, title: str, content: str, backend: str, head_extra: str = "",
          body_scripts: str = "", project: str = "sovereign") -> str:
    """Wrap a content fragment in the full dashboard shell.

    ``project`` labels the top-bar pill: the active project's name when a project filter is in
    effect (SENTINEL-012), else the default ``sovereign`` demo label.
    """
    backend_pill = (
        f"<span class='pill'><span class='dotmark {'v' if backend=='vllm' else 'g'}'></span>"
        f"Backend: <b>{escape(backend)}</b></span>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<link rel='icon' href=\"data:image/svg+xml,"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        "<rect x='5' y='5' width='22' height='22' rx='6' fill='%234285f4'/></svg>\">"
        f"<title>{escape(title)} · Sentinel</title><style>{CSS}</style>{head_extra}</head>"
        "<body><div class='shell' id='shell'>"
        f"{_sidebar(active)}"
        "<div class='main'>"
        f"<div class='topbar'><div class='topbar-inner'>"
        "<div class='crumb'><span>Agent Platform</span><span class='sep'>/</span>"
        f"<b style='color:var(--ink);font-weight:600'>{escape(title)}</b></div>"
        f"<div class='spacer'></div>"
        "<span class='proj-pill'>" + _icon("shield") + " project: " + escape(project) + "</span>"
        f"{backend_pill}"
        "<a class='btn' href='/new'>" + _icon("bolt") + " New Run</a></div></div>"
        f"<div class='content'>{content}</div>"
        "</div></div>"
        f"{_LOADER_HTML}"
        f"<script>{_COLLAPSE_JS}{_LOADER_JS}</script>{body_scripts}</body></html>"
    )


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def _kpi(cls: str, label: str, value, icon: str) -> str:
    return (
        f"<div class='card kpi {cls}'><div class='k-top'><span>{escape(label)}</span>"
        f"<span class='k-accent'>{_icon(icon)}</span></div>"
        f"<div class='k-val'>{value}</div></div>"
    )


def dashboard_page(*, stats: dict, charts: dict, recent: list[dict], backend: str,
                   focus: list | None = None) -> str:
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
            "No runs yet. <a href='/new' style='color:var(--accent-2)'>Run your first "
            "intelligence task</a> — the charts populate live, including the public vs "
            "private provenance split.</div></div>"
        )

    rows = ""
    for r in recent:
        name = escape(r["target"])
        if r.get("entity"):
            name = (f"<a href='{_account_href(r['entity'])}' "
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
            "const T={plugins:{legend:{labels:{color:'#8b97a8',boxWidth:12,font:{size:11}}}}},"
            "GRID='#1e2940',MUT='#8b97a8';"
            "function donut(id,labels,vals,colors){new Chart(document.getElementById(id),"
            "{type:'doughnut',data:{labels:labels,datasets:[{data:vals,backgroundColor:colors,"
            "borderColor:'#0e1420',borderWidth:2}]},options:{...T,cutout:'62%',"
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

    focus_html = focus_card(focus) if focus else ""
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


# --------------------------------------------------------------------------- #
# Finding / gap fragments
# --------------------------------------------------------------------------- #
def _badge(b: Boundary) -> str:
    cls = "public" if b is Boundary.PUBLIC else "private"
    return f"<span class='badge {cls}'>{b.value}</span>"


def _source(s: Source) -> str:
    if s.url:
        return (f"<span class='src'>· <a href='{escape(s.url)}' rel='noopener' "
                f"target='_blank'>{escape(s.label)}</a></span>")
    return f"<span class='src'>· {escape(s.label)}</span>"


def _run_sources(sources: list[Source]) -> str:
    """Persisted provenance for one timeline row (SENTINEL-008). A legacy row (pre-008, no
    captured sources) shows a neutral dash — never an empty cell that reads as "0 sources"."""
    if not sources:
        return "<span class='muted'>—</span>"
    return "".join(_source(s) for s in sources)


def _findings(title: str, items: list[Finding]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li>{_badge(f.source.boundary)}{escape(f.text)}{_source(f.source)}</li>" for f in items
    )
    return f"<h2 class='sec'>{escape(title)}</h2><ul class='find'>{rows}</ul>"


def _plain(title: str, items: list[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{escape(x)}</li>" for x in items)
    return f"<h2 class='sec'>{escape(title)}</h2><ul class='plain'>{rows}</ul>"


_PRIORITY_RANK = {"high": 0, "med": 1, "low": 2}


def _strategy_block(artifact) -> str:
    """Strategy overlay sections for the dashboard (SENTINEL-009). Empty when nothing populated."""
    out = ""
    if getattr(artifact, "assessment", None):
        out += f"<h2 class='sec'>Strategic assessment</h2><p>{escape(artifact.assessment)}</p>"
    actions = getattr(artifact, "action_plan", None) or []
    if actions:
        rows = "".join(
            f"<tr><td><span class='badge'>{escape(a.priority)}</span></td>"
            f"<td>{escape(a.action)}</td><td>{escape(a.timeline)}</td>"
            f"<td>{escape(a.rationale)}</td></tr>"
            for a in sorted(actions, key=lambda x: _PRIORITY_RANK.get(x.priority, 9))
        )
        out += (
            "<h2 class='sec'>Action plan</h2><table class='find'><thead><tr>"
            "<th>Priority</th><th>Action</th><th>Timeline</th><th>Rationale</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    objections = getattr(artifact, "objection_handling", None) or []
    if objections:
        rows = "".join(
            f"<li><b>{escape(o.objection)}</b> → {escape(o.reframe)}</li>" for o in objections
        )
        out += f"<h2 class='sec'>Objection handling</h2><ul class='plain'>{rows}</ul>"
    return out


def _gaps(items: list[Gap]) -> str:
    if not items:
        return ""
    rows = "".join(
        f"<li>{_badge(g.boundary)}<span class='gap'>{escape(g.what_was_missing)}</span> "
        f"<span class='src'>— {escape(g.impact)}</span></li>" for g in items
    )
    return f"<h2 class='sec'>Gaps (sources unavailable)</h2><ul class='find'>{rows}</ul>"


def provenance_counts(artifact) -> tuple[int, int]:
    """(public, private) finding counts for an artifact — drives the per-artifact donut."""
    pub = priv = 0
    if isinstance(artifact, Battlecard):
        for f in (artifact.strengths + artifact.weaknesses + artifact.pricing_signals
                  + artifact.recent_developments):
            pub += f.source.boundary is Boundary.PUBLIC
            priv += f.source.boundary is Boundary.PRIVATE
    elif isinstance(artifact, AccountBrief):
        pub = len(artifact.public_signal)
        priv = len(artifact.private_signal)
    return pub, priv


def _aside(artifact, backend: str, reference: str) -> str:
    pub, priv = provenance_counts(artifact)
    data = json.dumps({"pub": pub, "priv": priv})
    js = (
        "<script src='" + _CHARTJS + "'></script><script>"
        "var d=__DATA__;new Chart(document.getElementById('cArt'),{type:'doughnut',"
        "data:{labels:['Public','Private'],datasets:[{data:[d.pub,d.priv],"
        "backgroundColor:['#4ea1ff','#ffb24d'],borderColor:'#0e1420',borderWidth:2}]},"
        "options:{cutout:'62%',plugins:{legend:{position:'bottom',labels:{color:'#8b97a8',"
        "boxWidth:12,font:{size:11}}}}}});</script>"
    ).replace("__DATA__", data)
    card = (
        "<div class='card'><h3 class='ch'>Signal provenance</h3>"
        "<div class='chart-wrap' style='height:180px'><canvas id='cArt'></canvas></div>"
        "<div style='margin-top:14px;display:flex;flex-direction:column;gap:8px'>"
        f"<span class='pill'><span class='dotmark {'v' if backend=='vllm' else 'g'}'></span>"
        f"Backend: <b>{escape(backend)}</b></span>"
        f"<span class='pill'>Saved: <b>{escape(reference)}</b></span></div></div>"
    )
    return card, js


def _trace(trace: list[str]) -> str:
    if not trace:
        return ""
    return ("<details style='margin-top:18px'><summary>Run trace (observability)</summary>"
            f"<div class='trace'>{escape(chr(10).join(trace))}</div></details>")


def _delta_block(delta) -> str:
    """"Since last run" card (SENTINEL-002, AC-8). Empty string when there's no delta."""
    if delta is None:
        return ""
    chips = ""
    if getattr(delta, "added", None):
        chips += f"<span class='badge public'>+{len(delta.added)} new</span> "
    if getattr(delta, "removed", None):
        chips += f"<span class='badge private'>-{len(delta.removed)} dropped</span>"
    items = "".join(f"<li>{escape(t)}</li>" for t in (delta.added or [])[:6])
    new_list = f"<ul class='since-list' style='margin:10px 0 0;padding-left:18px'>{items}</ul>" if items else ""
    return (
        "<div class='card' style='margin-bottom:18px'>"
        "<h3 class='ch'>Since last run</h3>"
        f"<div class='summary'>{escape(delta.summary)}</div>"
        f"<div style='margin-top:8px'>{chips}</div>{new_list}</div>"
    )


def render_battlecard(
    b: Battlecard, *, backend: str, reference: str, trace: list[str], delta=None
) -> str:
    vert = (f"<span class='pill'>Vertical: <b>{escape(b.vertical_context)}</b></span>"
            if b.vertical_context else "")
    aside, js = _aside(b, backend, reference)
    main = (
        f"<div class='card'><div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap'>"
        f"<h2 style='font-size:24px;margin:0'>Battlecard — {escape(b.target)}</h2>{vert}</div>"
        f"<div class='summary'>{escape(b.one_line_summary)}</div>"
        f"<h2 class='sec'>Positioning</h2><p>{escape(b.positioning)}</p>"
        + _findings("Strengths", b.strengths)
        + _findings("Weaknesses", b.weaknesses)
        + _findings("Pricing signals", b.pricing_signals)
        + _findings("Recent developments", b.recent_developments)
        + _plain("How to win against them", b.how_to_win)
        + _strategy_block(b)
        + _gaps(b.gaps) + _trace(trace) + "</div>"
    )
    content = f"{_delta_block(delta)}<div class='two-col'>{main}{aside}</div>"
    return shell(active="artifacts", title=f"Battlecard — {b.target}", content=content,
                 backend=backend, body_scripts=js)


def render_account_brief(
    a: AccountBrief, *, backend: str, reference: str, trace: list[str], delta=None
) -> str:
    vert = (f"<span class='pill'>Vertical: <b>{escape(a.vertical_context)}</b></span>"
            if a.vertical_context else "")
    aside, js = _aside(a, backend, reference)
    main = (
        f"<div class='card'><div style='display:flex;gap:10px;align-items:center;flex-wrap:wrap'>"
        f"<h2 style='font-size:24px;margin:0'>Account Brief — {escape(a.account)}</h2>{vert}</div>"
        f"<div class='summary'>{escape(a.one_line_summary)}</div>"
        + _findings("Public signal", a.public_signal)
        + _findings("Private signal", a.private_signal)
        + _plain("Merged insights (public ⊕ private)", a.merged_insights)
        + _plain("Recommended actions", a.recommended_actions)
        + _strategy_block(a)
        + _gaps(a.gaps) + _trace(trace) + "</div>"
    )
    content = f"{_delta_block(delta)}<div class='two-col'>{main}{aside}</div>"
    return shell(active="artifacts", title=f"Account Brief — {a.account}", content=content,
                 backend=backend, body_scripts=js)


def render_artifact(artifact, *, backend: str, reference: str, trace: list[str], delta=None) -> str:
    if isinstance(artifact, Battlecard):
        return render_battlecard(
            artifact, backend=backend, reference=reference, trace=trace, delta=delta
        )
    if isinstance(artifact, AccountBrief):
        return render_account_brief(
            artifact, backend=backend, reference=reference, trace=trace, delta=delta
        )
    raise TypeError(f"No renderer for {type(artifact).__name__}")


# --------------------------------------------------------------------------- #
# Artifacts list
# --------------------------------------------------------------------------- #
def artifacts_page(*, artifacts: list[dict], backend: str, project: str = "sovereign") -> str:
    if not artifacts:
        content = ("<div class='card'><div class='empty'>No artifacts yet. "
                   "<a href='/new' style='color:var(--accent-2)'>Run a task</a> to generate "
                   "a battlecard or account brief.</div></div>")
        return shell(active="artifacts", title="Artifacts", content=content, backend=backend,
                 project=project)
    rows = ""
    for a in artifacts:
        name = escape(a["target"])
        if a.get("entity"):
            name = (f"<a href='{_account_href(a['entity'])}' "
                    f"style='color:var(--accent-2)'>{name}</a>")
        rows += (
            f"<tr><td><b>{name}</b></td><td>{escape(a['kind'])}</td>"
            f"<td><span class='badge public'>{a['public']}</span>"
            f"<span class='badge private'>{a['private']}</span></td>"
            f"<td><span class='dotmark {'v' if a['backend']=='vllm' else 'g'}'></span> "
            f"<span class='mono'>{escape(a['backend'])}</span></td>"
            f"<td class='mono'>{escape(a['reference'])}</td>"
            f"<td class='mono'>{escape(a['when'])}</td></tr>"
        )
    content = (
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>Target</th><th>Kind</th><th>Public / Private</th><th>Backend</th>"
        "<th>Saved to</th><th>When</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active="artifacts", title="Artifacts", content=content, backend=backend,
                 project=project)


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


def agents_page(*, modes: list[dict], flags: dict, backend: str) -> str:
    """Render the agent roster + per-mode pipeline flow graph."""
    legend = (
        "<div class='legend'>"
        "<span><span class='swatch' style='background:var(--accent-2)'></span>tool-caller (Gemma-12B)</span>"
        "<span><span class='swatch' style='background:#c08cf7'></span>reasoner (Gemma-26B, tool-free)</span>"
        "<span><span class='swatch' style='background:var(--private)'></span>private boundary (MCP)</span>"
        "<span><span class='swatch' style='background:var(--line)'></span>dashed = stage off by config</span>"
        "</div>"
    )
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

    # The deterministic (non-LLM) steps that wrap the LLM pipeline.
    rail_steps = [
        ("recall", "Memory recall", "boundary-filtered, injected as context"),
        ("merge", "Merge overlays", "strategy + extraction gaps → artifact"),
        ("persist", "Persist run", "memory + run record (sources, run_seq)"),
        ("priority", "Recompute priority", "deterministic 0–100 score — no LLM"),
    ]
    rail = "".join(
        f"<span class='step'>{_icon('merge')} <b>{escape(t)}</b> · {escape(d)}</span>"
        for _k, t, d in rail_steps
    )

    topo = "A2A coordinator" if flags.get("coordinator") else "Sequential pipeline"
    coord_card = (
        "<div class='card' style='margin-top:18px'>"
        f"<div class='gc-t'>Execution topology <span class='pv'>{escape(topo)}</span></div>"
        "<p class='gc-d'>Default: a <b>SequentialAgent</b> runs the stages in order, each writing its "
        "<span class='agent-key'>output_key</span> into shared session state for the next to read. "
        "When <b>coordinator.enabled</b>, an <b>LlmAgent</b> (Gemma-12B) instead delegates to the same "
        "stages wrapped as <span class='agent-key'>AgentTool</span> specialists (Goal→Plan→Delegate→Merge). "
        "Either way the artifact, boundary split, and provenance are identical.</p>"
        "<div class='rail'>" + rail + "</div></div>"
    )

    flagline = (
        "<div class='legend' style='margin-top:10px'>"
        f"<span>two-tier extractor: <b style='color:var(--ink)'>{'on' if flags.get('two_tier') else 'off'}</b></span>"
        f"<span>strategy overlay: <b style='color:var(--ink)'>{'on' if flags.get('strategy') else 'off'}</b></span>"
        f"<span>private boundary: <b style='color:var(--ink)'>{'configured' if flags.get('private') else 'not configured'}</b></span>"
        "</div>"
    )

    hero = (
        "<div class='hero left'><h1>Agents</h1>"
        "<p style='margin:0'>The agents Sentinel runs, what each does, and how they hand off. "
        "Tool-callers gather; reasoners decide; deterministic steps score and persist.</p></div>"
    )
    content = hero + legend + flagline + lanes + coord_card
    return shell(active="agents", title="Agents", content=content, backend=backend)


# --------------------------------------------------------------------------- #
# Accounts (SENTINEL-004) — entity index + detail (run timeline + memory)
# --------------------------------------------------------------------------- #
def _account_href(entity: str) -> str:
    """Link to an account by its normalized key. ``safe=''`` encodes spaces/slashes so a key
    like ``acme corp`` round-trips through the path param (AC-10)."""
    return f"/accounts/{quote(entity, safe='')}"


def _fmt_when(dt) -> str:
    # tz-aware UTC in storage; show the operator local wall-clock.
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def accounts_page(*, accounts: list, backend: str, ok: str = "", project: str = "sovereign") -> str:
    """The Accounts index — one row per distinct entity (AC-1, AC-2)."""
    banner = f"<div class='card banner ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    if not accounts:
        content = (banner + "<div class='card'><div class='empty'>No accounts yet. "
                   "<a href='/new' style='color:var(--accent-2)'>Run a task</a> against a "
                   "competitor or client and it appears here, with its full history.</div></div>")
        return shell(active="accounts", title="Accounts", content=content, backend=backend,
                 project=project)
    rows = ""
    for s in accounts:
        modes = ", ".join(escape(m) for m in s.modes) or "—"
        rows += (
            f"<tr><td><a href='{_account_href(s.entity)}' style='color:var(--accent-2)'>"
            f"<b>{escape(s.display_name)}</b></a></td>"
            f"<td>{modes}</td>"
            f"<td class='mono'>{s.runs}</td>"
            f"<td><span class='badge public'>{s.public}</span>"
            f"<span class='badge private'>{s.private}</span></td>"
            f"<td class='mono'>{escape(_fmt_when(s.last_run_at))}</td></tr>"
        )
    content = (
        banner
        + "<p class='note'>Every entity researched, collapsed to one row. Open one to see its run "
        "timeline and accumulated memory — public and private signal kept separate.</p>"
        "<div class='card' style='padding:6px 8px;margin-top:16px'><table><thead><tr>"
        "<th>Account</th><th>Modes</th><th>Runs</th><th>Public / Private</th>"
        "<th>Last run</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active="accounts", title="Accounts", content=content, backend=backend,
                 project=project)


# --------------------------------------------------------------------------- #
# Projects (SENTINEL-012) — the top-level organising construct. Step 6 ships the
# shell: create a project, list projects, open one to a task/results placeholder.
# --------------------------------------------------------------------------- #
def _project_form() -> str:
    return (
        "<div class='card'><div class='section-h' style='margin-top:0'><h2>New project</h2></div>"
        "<form class='run' method='post' action='/projects'>"
        "<div><label class='lbl' for='p-name'>Name</label>"
        "<input id='p-name' name='name' placeholder='e.g. BiltIQ market-capture' required></div>"
        "<div><label class='lbl' for='p-website'>Website (optional)</label>"
        "<input id='p-website' name='website' placeholder='https://biltiq.ai'></div>"
        "<div><label class='lbl' for='p-obj'>First research objective (optional)</label>"
        "<input id='p-obj' name='objective' "
        "placeholder='e.g. Profile us and compare against a competitor'></div>"
        f"<div><button class='btn' type='submit'>{_icon('bolt')} Create project</button></div>"
        "</form>"
        "<div class='note' style='margin-top:8px'>A project is a workspace that groups research tasks. "
        "Add an objective to jump straight into planning your first task; leave it blank to set up the "
        "workspace and add tasks later.</div></div>"
    )


def projects_page(*, projects: list, backend: str, ok: str = "") -> str:
    banner = f"<div class='card banner ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    form = _project_form()
    if not projects:
        empty = ("<div class='card' style='margin-top:16px'><div class='empty'>No projects yet. "
                 "Create one above — a project groups the tasks and results of a research program.</div></div>")
        return shell(active="projects", title="Projects", content=banner + form + empty, backend=backend)
    rows = ""
    for p in projects:
        site = (f"<a href='{escape(p.website)}' rel='noopener' target='_blank' "
                f"style='color:var(--accent-2)'>{escape(p.website)}</a>") if p.website else "—"
        rows += (
            f"<tr><td><a href='/projects/{escape(p.id)}' style='color:var(--accent-2)'>"
            f"<b>{escape(p.name)}</b></a></td>"
            f"<td>{site}</td>"
            f"<td><span class='badge'>{escape(p.settings.autonomy)}</span></td>"
            f"<td class='mono'>{escape(p.created_at)}</td></tr>"
        )
    table = (
        "<div class='card' style='padding:6px 8px;margin-top:16px'><table><thead><tr>"
        "<th>Project</th><th>Website</th><th>Autonomy</th><th>Created</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active="projects", title="Projects", content=banner + form + table, backend=backend)


_DOMAINS = ["market", "account", "software", "finance", "academic", "nutrition", "travel"]
# Persona = who the output is for (reading level / tone / format). The orchestrated run renders the
# deliverable for this persona without changing the facts (SENTINEL-012 AC-8/17).
_PERSONAS = ["enterprise", "developer", "consumer", "student", "doctor", "nurse"]


def _task_form(project_id: str) -> str:
    """The objective → plan entry point (SENTINEL-012): a GET form that hands the objective, domain and
    persona to the planner route, which proposes a step-DAG. This is the UI door to the orchestrator —
    the place a Task's three dimensions (objective × domain × persona) are chosen."""
    domains = "".join(f"<option value='{d}'>{d}</option>" for d in _DOMAINS)
    personas = "".join(f"<option value='{p}'>{p}</option>" for p in _PERSONAS)
    return (
        "<div class='section-h'><h2>New task</h2></div>"
        "<div class='card'>"
        f"<form class='run' method='get' action='/projects/{escape(project_id)}/plan'>"
        "<div><label class='lbl' for='t-obj'>Objective</label>"
        "<input id='t-obj' name='objective' required "
        "placeholder='e.g. Profile us, find competitors, and produce a market-capture strategy'></div>"
        "<div><label class='lbl' for='t-dom'>Domain</label>"
        f"<select id='t-dom' name='domain'>{domains}</select></div>"
        "<div><label class='lbl' for='t-per'>Persona</label>"
        f"<select id='t-per' name='persona'>{personas}</select></div>"
        f"<div><button class='btn' type='submit'>{_icon('bolt')} Plan task</button></div>"
        "</form>"
        "<div class='note' style='margin-top:8px'>Domain selects the research skills + output shape; "
        "persona adapts the output's reading level &amp; tone (facts unchanged). The planner proposes a "
        "step-DAG; you review and approve before anything runs (unless the project is autonomous).</div></div>"
    )


def _task_status_badge(status: str) -> str:
    """Colour a task's lifecycle status so the Tasks list is honest at a glance (not all 'created')."""
    colour = {
        "created": "var(--muted)", "planned": "rgba(66,133,244,.16);color:var(--accent-2)",
        "running": "rgba(66,133,244,.16);color:var(--accent-2)",
        "done": "rgba(22,163,74,.16);color:#16a34a",
        "failed": "rgba(234,179,8,.16);color:#b78a00",
        "rejected": "rgba(220,38,38,.16);color:#dc2626",
    }.get(status, "var(--muted)")
    bg = colour if ";" in colour else f"transparent;color:{colour}"
    return f"<span class='badge' style='background:{bg}'>{escape(status)}</span>"


def project_detail_page(*, project, tasks: list, backend: str) -> str:
    """One project: a task entry form + its tasks. The form posts an objective to the planner route,
    which proposes a step-DAG; the top-bar pill shows this project as the active scope (SENTINEL-012)."""
    site = (f"<a href='{escape(project.website)}' rel='noopener' target='_blank' "
            f"style='color:var(--accent-2)'>{escape(project.website)}</a>") if project.website else "—"
    header = (
        "<div class='card'><div class='section-h' style='margin-top:0'>"
        f"<h2>{escape(project.name)}</h2>"
        f"<a class='btn ghost' href='/artifacts?project={escape(project.id)}'>Scoped artifacts</a></div>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-top:8px'>"
        f"<span class='pill'>Website: <b>{site}</b></span>"
        f"<span class='pill'>Autonomy: <b>{escape(project.settings.autonomy)}</b></span></div></div>"
    )
    form_html = _task_form(project.id)
    if tasks:
        rows = "".join(
            f"<tr><td><a href='/projects/{escape(project.id)}/tasks/{escape(t.id)}' "
            f"style='color:var(--accent-2)'><b>{escape(t.objective)}</b></a></td>"
            f"<td>{escape(t.domain.name)}</td>"
            f"<td>{_task_status_badge(t.status)}</td>"
            f"<td style='text-align:right'><form method='post' style='display:inline' "
            f"action='/projects/{escape(project.id)}/tasks/{escape(t.id)}/delete'>"
            "<button class='btn ghost' type='submit' title='Remove task' "
            "style='padding:2px 8px'>&times;</button></form></td></tr>" for t in tasks
        )
        tasks_html = (
            "<div class='section-h'><h2>Tasks</h2></div>"
            "<div class='card' style='padding:6px 8px'><table><thead><tr>"
            "<th>Objective</th><th>Domain</th><th>Status</th><th></th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    else:
        tasks_html = (
            "<div class='section-h'><h2>Tasks</h2></div>"
            "<div class='card'><div class='empty'>No tasks yet. Task definition and the "
            "orchestrated value chain (map → compare → strategy) arrive next — this is the project "
            "workspace they'll populate.</div></div>"
        )
    content = (header + "<div style='margin-top:16px'></div>" + form_html
               + "<div style='margin-top:16px'></div>" + tasks_html)
    return shell(active="projects", title=project.name, content=content, backend=backend,
                 project=project.name)


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
    lis = "".join(f"<li>{escape(f.get('text', '') if isinstance(f, dict) else str(f))}</li>" for f in items)
    return f"<div style='margin-top:8px'><b>{escape(title)}</b><ul class='find'>{lis}</ul></div>"


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

    if "action_plan" in art and "assessment" in art:            # ProgramStrategy
        rows = "".join(
            f"<tr><td>{_prio_badge(a.get('priority', ''))}</td>"
            f"<td><b>{escape(a.get('action', ''))}</b>"
            f"<div class='note'>{escape(a.get('rationale', ''))}</div></td>"
            f"<td>{escape(a.get('timeline', ''))}</td></tr>" for a in art.get("action_plan", []))
        body = (f"<div class='note'>{escape(art.get('assessment', ''))}</div>"
                + (f"<table style='margin-top:8px'><thead><tr><th>Priority</th><th>Action</th>"
                   f"<th>Timeline</th></tr></thead><tbody>{rows}</tbody></table>" if rows else ""))
        return _art_wrap("Market-capture strategy", body)

    if "one_line_summary" in art or ("strengths" in art and "weaknesses" in art):   # Battlecard
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + _findings_block("Strengths", art.get("strengths", []))
                + _findings_block("Weaknesses", art.get("weaknesses", []))
                + _findings_block("Pricing signals", art.get("pricing_signals", []))
                + _findings_block("Recent developments", art.get("recent_developments", [])))
        return _art_wrap(f"Battlecard — {escape(art.get('target', '') or key)}", body)

    return _art_wrap(key, "<pre style='white-space:pre-wrap;overflow:auto;font-size:.82em'>"
                     f"{escape(json.dumps(art, indent=2, default=str))}</pre>")


def _result_card(result) -> str:
    """Render an orchestrated Result inline (the deliverable): summary + honesty flags, each produced
    artifact, the cited sources by boundary, and any persona-adapted prose / model grade. This is what
    makes 'the run produced something' visible instead of a dead link."""
    deg = ("<span class='badge' style='background:rgba(234,179,8,.16);color:#b78a00'>partial</span>"
           if result.degraded else
           "<span class='badge' style='background:rgba(22,163,74,.16);color:#16a34a'>complete</span>")
    pub = sum(1 for c in result.citations if getattr(c.boundary, "value", c.boundary) == "public")
    prv = len(result.citations) - pub
    head = (f"<div class='card'><div class='section-h' style='margin-top:0'><h2>Result</h2>{deg}</div>"
            f"<div class='note' style='margin:6px 0 10px'>{escape(result.summary)}</div>"
            f"{_provenance_bar(pub, prv)}</div>")

    arts = (result.dashboard_payload or {}).get("artifacts", {}) or {}
    if arts:
        blocks = [_artifact_html(key, art) for key, art in arts.items()]
        arts_html = ("<div class='section-h'><h2>Deliverables</h2></div>"
                     "<div style='display:grid;gap:10px'>" + "".join(blocks) + "</div>")
    else:
        arts_html = ("<div class='section-h'><h2>Artifacts</h2></div>"
                     "<div class='card'><div class='empty'>No artifact content produced (the run "
                     "degraded — see the missing steps above).</div></div>")

    if result.citations:
        cites = "".join(
            f"<li>{_badge(c.boundary)}{escape(c.label or '—')}"
            + (f" · <a href='{escape(c.url)}' rel='noopener' target='_blank' "
               f"style='color:var(--accent-2)'>{escape(c.url)}</a>" if c.url else "")
            + "</li>" for c in result.citations)
        cites_html = (f"<div class='section-h'><h2>Citations ({len(result.citations)})</h2></div>"
                      f"<div class='card'><ul class='find'>{cites}</ul></div>")
    else:
        cites_html = ("<div class='section-h'><h2>Citations</h2></div>"
                      "<div class='card'><div class='empty'>No sources cited in this run.</div></div>")

    extra = ""
    if getattr(result, "persona_rendered", None):
        extra += ("<div class='section-h'><h2>Persona view</h2></div>"
                  f"<div class='card'><div class='note'>{escape(result.persona_rendered)}</div></div>")
    if getattr(result, "grade", None) is not None:
        g = result.grade
        verdict = "pass" if getattr(g, "passed", False) else "review"
        extra += ("<div class='section-h'><h2>Quality grade</h2></div>"
                  f"<div class='card'><span class='pill'>score: <b>{getattr(g,'score',0):.2f}</b></span> "
                  f"<span class='badge'>{escape(verdict)}</span></div>")

    return (head + "<div style='margin-top:16px'></div>" + arts_html
            + "<div style='margin-top:16px'></div>" + cites_html + extra)


def plan_review_page(*, task, proposal, autonomy: str, backend: str, ran: bool = False,
                     result=None, trace: list[str] | None = None) -> str:
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

    header = (
        "<div class='card'><div class='section-h' style='margin-top:0'><h2>Plan review</h2>"
        f"<span class='badge'>autonomy: {escape(autonomy)}</span></div>"
        f"<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap'>"
        f"<span class='pill'>objective: <b>{escape(task.objective)}</b></span>"
        f"<span class='pill'>domain: <b>{escape(task.domain.name)}</b></span>"
        f"<span class='pill'>persona: <b>{escape(task.persona.name)}</b></span>"
        f"<span class='pill'>steps: <b>{len(plan.steps)}</b></span>"
        f"<span class='pill'>new agents: <b>{len(created)}</b></span></div></div>"
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

    if not ran:
        action = (
            f"<form method='post' action='/projects/{escape(task.project_id)}/tasks/{escape(task.id)}/run' "
            "style='margin-top:16px'>"
            "<button class='btn' type='submit'>" + _icon("bolt") + " Approve &amp; run</button></form>"
        )
    else:
        exec_html = ("<div style='margin-top:16px'></div>" + _execution_log(trace)) if trace else ""
        result_html = ("<div style='margin-top:16px'></div>" + _result_card(result)) if result else ""
        action = (exec_html + result_html + "<div style='margin-top:16px'><a class='btn ghost' "
                  f"href='/projects/{escape(task.project_id)}'>Back to project</a> "
                  f"<a class='btn ghost' href='/artifacts?project={escape(task.project_id)}'>"
                  "All scoped artifacts</a></div>")

    content = (banner + "<div style='margin-top:16px'></div>" + header
               + "<div style='margin-top:16px'></div>" + dag_html
               + "<div style='margin-top:16px'></div>" + created_html + action)
    return shell(active="projects", title="Plan review", content=content, backend=backend)


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
        "var a=__DATA__;new Chart(document.getElementById('cAcc'),{type:'doughnut',"
        "data:{labels:['Public','Private'],datasets:[{data:[a.pub,a.priv],"
        "backgroundColor:['#4ea1ff','#ffb24d'],borderColor:'#0e1420',borderWidth:2}]},"
        "options:{cutout:'62%',plugins:{legend:{position:'bottom',labels:{color:'#8b97a8',"
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
        + f"<div class='two-col'>{left}{donut}</div>"
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


# --------------------------------------------------------------------------- #
# Focus list (SENTINEL-010) — deterministic, cited account prioritization.
# A row's score/tier/reasons all come from compute_account_priority; this layer only escapes and
# lays out. A reason carrying a private boundary is rendered with the private badge so an operator
# can see at a glance which signal it came from (the engine already drops private reasons from a
# public-only score, so nothing leaks here — AC-10).
# --------------------------------------------------------------------------- #
_TIER_STYLE = {
    "hot": "color:#ff8a8a;background:rgba(255,80,80,.12);border:1px solid #7f3030",
    "warm": "color:var(--private);background:var(--private-bg);border:1px solid #5a4413",
    "cold": "color:var(--muted);background:var(--panel);border:1px solid var(--line)",
}


def _tier_badge(tier: str) -> str:
    style = _TIER_STYLE.get(tier, _TIER_STYLE["cold"])
    return (f"<span class='badge' style='{style};text-transform:uppercase;"
            f"letter-spacing:.05em'>{escape(tier)}</span>")


def _reason_html(r) -> str:
    """One cited reason: text + optional source link + a private badge when private-sourced."""
    badge = _badge(r.boundary) if r.boundary == Boundary.PRIVATE else ""
    src = ""
    if getattr(r, "source_url", None):
        src = (f" <span class='src'>· <a href='{escape(r.source_url)}' rel='noopener' "
               f"target='_blank'>{escape(r.source_label or 'source')}</a></span>")
    elif getattr(r, "source_label", ""):
        src = f" <span class='src'>· {escape(r.source_label)}</span>"
    return f"<li>{badge}{escape(r.text)}{src}</li>"


def _breakdown_html(breakdown: dict, notes: list) -> str:
    """Auditable per-signal detail in a collapsed <details> — the deterministic receipt (AC-11)."""
    rows = "".join(
        f"<tr><td class='mono'>{escape(name)}</td>"
        f"<td class='mono'>{raw:.2f}</td>"
        f"<td><div style='height:6px;border-radius:4px;background:var(--accent);"
        f"width:{max(2, min(100, int(raw * 100)))}%'></div></td></tr>"
        for name, raw in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    )
    note = (f"<p class='note' style='margin:6px 0 0'>{escape('; '.join(notes))}</p>" if notes else "")
    return (
        "<details style='margin-top:6px'><summary class='src' style='cursor:pointer'>"
        "Signal breakdown</summary>"
        "<table style='margin-top:6px'><thead><tr><th>Signal</th><th>Raw</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table>{note}</details>"
    )


def _focus_row(rank: int, s) -> str:
    reasons = "".join(_reason_html(r) for r in s.reasons[:3]) or "<li class='src'>—</li>"
    return (
        f"<tr><td class='mono'>{rank}</td>"
        f"<td><a href='{_account_href(s.entity)}' style='color:var(--accent-2)'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td>"
        f"<td><ul class='find' style='margin:0'>{reasons}</ul>"
        f"{_breakdown_html(s.breakdown, s.notes)}</td></tr>"
    )


def focus_page(*, scores: list, backend: str, enabled: bool = True, project: str = "sovereign") -> str:
    """Ranked focus list — highest priority first, each row cited and auditable (AC-9)."""
    if not enabled:
        content = ("<div class='card'><div class='empty'>The focus list is turned off. "
                   "Enable <b>Prioritization</b> in "
                   "<a href='/settings' style='color:var(--accent-2)'>Settings</a> to rank "
                   "accounts by who needs attention now.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    if not scores:
        content = ("<div class='card'><div class='empty'>No accounts to prioritize yet. "
                   "<a href='/new' style='color:var(--accent-2)'>Run a task</a> and the focus "
                   "list ranks every researched account here, with cited reasons.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    rows = "".join(_focus_row(i, s) for i, s in enumerate(scores, start=1))
    content = (
        "<p class='note'>Who needs attention now — ranked by a deterministic, cited score (no "
        "LLM in the arithmetic). Each reason links to the finding behind it; the breakdown shows "
        "every signal. Tune the weights in "
        "<a href='/settings' style='color:var(--accent-2)'>Settings</a>.</p>"
        "<div class='card' style='padding:6px 8px;margin-top:16px'><table><thead><tr>"
        "<th>#</th><th>Account</th><th>Score</th><th>Tier</th><th>Why now</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)


def focus_card(scores: list) -> str:
    """Compact 'Top 5 to focus on' card for the dashboard (OQ-2). Empty string when no scores."""
    top = [s for s in scores if s.tier != "cold"][:5] or scores[:5]
    if not top:
        return ""
    rows = "".join(
        f"<tr><td><a href='{_account_href(s.entity)}' style='color:var(--accent-2)'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td></tr>"
        for s in top
    )
    return (
        "<div class='section-h' style='margin-top:16px'><h2>Top to focus on</h2>"
        "<a class='btn ghost' href='/focus'>Open focus list</a></div>"
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>Account</th><th>Score</th><th>Tier</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


# --------------------------------------------------------------------------- #
# Backends config
# --------------------------------------------------------------------------- #
def backends_page(*, default_backend: str, gemini_model: str, vllm_model: str,
                  vllm_api_base: str, gemini_key_set: bool, private_configured: bool,
                  vllm_key_set: bool = False) -> str:
    def chip(ok: bool, yes: str, no: str) -> str:
        return (f"<span class='pill'><span class='dotmark' style='background:"
                f"{'#3ad29f' if ok else '#ff6b6b'}'></span>{yes if ok else no}</span>")

    g_active = "background:var(--public-bg);box-shadow:inset 0 0 0 2px var(--public)" if default_backend != "vllm" else ""
    v_active = "background:var(--private-bg);box-shadow:inset 0 0 0 2px var(--private)" if default_backend == "vllm" else ""
    content = f"""
    <p class='note'>Sentinel runs against two interchangeable reasoning backends. <b>One rule:</b>
    API keys live in <span class='mono'>.env</span>; everything else — models, endpoints, the
    default backend — is edited in <a href='/settings' style='color:var(--accent-2)'>Settings</a>
    (saved to <span class='mono'>sentinel.config.yaml</span>). Every run can still override the
    default with the toggle on <a href='/new' style='color:var(--accent-2)'>New Run</a>.</p>
    <div class='grid' style='grid-template-columns:1fr 1fr;margin-top:16px'>
      <div class='card' style='{g_active}'>
        <div style='display:flex;align-items:center;gap:10px'>{_icon('globe')}
          <h3 style='margin:0'>Cloud · Gemini</h3>
          {"<span class='badge public'>default</span>" if default_backend!='vllm' else ""}</div>
        <p class='note' style='margin-top:10px'>Managed Gemini for grounding + reasoning. Fastest path.</p>
        <div style='display:flex;flex-direction:column;gap:8px;margin-top:6px'>
          <span class='pill'>Model: <b>{escape(gemini_model)}</b></span>
          {chip(gemini_key_set, "GOOGLE_API_KEY set", "GOOGLE_API_KEY missing")}
        </div>
      </div>
      <div class='card' style='{v_active}'>
        <div style='display:flex;align-items:center;gap:10px'>{_icon('lock')}
          <h3 style='margin:0'>On-prem · Gemma</h3>
          {"<span class='badge private'>default</span>" if default_backend=='vllm' else ""}</div>
        <p class='note' style='margin-top:10px'>Reasoning on your own GPUs via vLLM. Private data never leaves.</p>
        <div style='display:flex;flex-direction:column;gap:8px;margin-top:6px'>
          <span class='pill'>Model: <b>{escape(vllm_model)}</b></span>
          <span class='pill'>Endpoint: <b>{escape(vllm_api_base)}</b></span>
          {chip(vllm_key_set, "VLLM_API_KEY set", "VLLM_API_KEY not set (unauthenticated)")}
        </div>
      </div>
    </div>
    <div class='card' style='margin-top:16px'>
      <h3 style='margin:0 0 10px'>Private boundary (Workspace MCP)</h3>
      {chip(private_configured, "Connected — client mode uses private signal",
            "Not connected — client mode degrades gracefully (public-only, gap flagged)")}
    </div>
    <p class='note' style='margin-top:16px'>Start the local Gemma server with
    <span class='mono'>docker compose -f deploy/vllm-compose.yml up</span>, then switch the
    toggle to On-prem. Presets: <span class='mono'>.env.gemini</span> /
    <span class='mono'>.env.vllm</span>.</p>
    """
    return shell(active="backends", title="Backends", content=content, backend=default_backend)


# --------------------------------------------------------------------------- #
# Settings (SENTINEL-003)
# --------------------------------------------------------------------------- #
def _num(name: str, label: str, value, *, step: str = "any", mn: str = "", mx: str = "") -> str:
    v = "" if value is None else escape(str(value))
    mn_a = f" min='{mn}'" if mn != "" else ""
    mx_a = f" max='{mx}'" if mx != "" else ""
    return (
        f"<div><label class='lbl' for='{name}'>{escape(label)}</label>"
        f"<input type='number' step='{step}'{mn_a}{mx_a} id='{name}' name='{name}' value='{v}'></div>"
    )


def _gen_row(gen) -> str:
    """Four generation inputs (temperature/max_output_tokens/top_p/top_k)."""
    return (
        "<div class='row4'>"
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
        f"<div><label class='lbl' for='{name}'>{escape(label)}</label>"
        f"<select id='{name}' name='{name}'>{opts}</select></div>"
    )


def _agent_card(key: str, a) -> str:
    return (
        "<div class='card'>"
        f"<form method='post' action='/settings/agents/{escape(key)}' class='set-grid'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;gap:10px'>"
        f"<span class='agent-key'>{escape(key)}</span>"
        f"<div style='display:flex;gap:16px'>{_chk('enabled','enabled',a.enabled)}"
        f"{_chk('pin_gemini','pin to Gemini',a.pin_gemini)}</div></div>"
        "<div><label class='lbl' for='model-" + escape(key) + "'>Model "
        "(blank ⇒ backend default)</label>"
        f"<input id='model-{escape(key)}' name='model' value='{escape(a.model or '')}' "
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
        f"<textarea name='template' rows='7'>{escape(p.template)}</textarea>"
        f"{vars_hint}"
        "<div class='set-actions'><button class='btn' type='submit'>Save prompt</button></div>"
        "</form>"
        f"<form method='post' action='/settings/prompts/{escape(key)}/reset' "
        "style='margin-top:8px'>"
        "<button class='btn ghost' type='submit'>Reset to shipped default</button>"
        "</form></div></details>"
    )


# Per-role model tiering (SENTINEL-011): role → (tier label, suggested on-prem endpoint).
_ROLE_TIERS = [
    ("coordinator", "tool-caller · 12B", "https://gemma.atcuality.com/v1"),
    ("planner", "tool-caller · 12B", "https://gemma.atcuality.com/v1"),
    ("public_research", "tool-caller · 12B", "https://gemma.atcuality.com/v1"),
    ("private_research", "tool-caller · 12B", "https://gemma.atcuality.com/v1"),
    ("extractor", "tool-caller · 12B", "https://gemma.atcuality.com/v1"),
    ("synthesizer", "reasoner · 26B (no tools)", "https://omni.atcuality.com/v1"),
    ("strategist", "reasoner · 26B (no tools)", "https://omni.atcuality.com/v1"),
]


def settings_page(cfg, *, backend: str, gemini_key_set: bool, ok: str = "", err: str = "",
                  vllm_key_set: bool = False, brave_key_set: bool = False,
                  serpapi_key_set: bool = False, atcuality_key_set: bool = False) -> str:
    banner = ""
    if ok:
        banner = f"<div class='card banner ok'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad'>{escape(err)}</div>"

    def _key_pill(name: str, ok_: bool) -> str:
        return (f"<span class='pill'><span class='dotmark' style='background:"
                f"{'#3ad29f' if ok_ else '#ff6b6b'}'></span>"
                f"{escape(name)}: <b>{'set' if ok_ else 'not set'}</b></span>")

    key_pill = _key_pill("GOOGLE_API_KEY", gemini_key_set) + _key_pill("VLLM_API_KEY", vllm_key_set)
    g_checked = "checked" if backend != "vllm" else ""
    v_checked = "checked" if backend == "vllm" else ""

    backends = (
        "<h2 class='sec'>Backends</h2>"
        "<div class='card'><form method='post' action='/settings/backends' class='set-grid'>"
        "<div><label class='lbl'>Default reasoning backend</label><div class='seg'>"
        f"<input class='cloud' type='radio' id='sb-gemini' name='default' value='gemini' {g_checked}>"
        "<label class='l-cloud' for='sb-gemini'>☁ Cloud · Gemini</label>"
        f"<input class='onprem' type='radio' id='sb-vllm' name='default' value='vllm' {v_checked}>"
        "<label class='l-onprem' for='sb-vllm'>🔒 On-prem · Gemma</label></div></div>"
        "<div class='row2'>"
        f"<div><label class='lbl' for='gemini_model'>Gemini model</label>"
        f"<input id='gemini_model' name='gemini_model' value='{escape(cfg.backend.gemini.model)}'></div>"
        f"<div><label class='lbl' for='vllm_model'>vLLM model</label>"
        f"<input id='vllm_model' name='vllm_model' value='{escape(cfg.backend.vllm.model)}'></div>"
        "</div>"
        f"<div><label class='lbl' for='vllm_api_base'>vLLM API base</label>"
        f"<input id='vllm_api_base' name='vllm_api_base' "
        f"value='{escape(cfg.backend.vllm.api_base or '')}'></div>"
        f"<div class='set-actions'>{key_pill}"
        "<span style='flex:1'></span><button class='btn' type='submit'>Save backends</button></div>"
        "<p class='note'><b>One source of truth:</b> API keys live in <span class='mono'>.env</span> "
        "(shown here only as set / not-set, never the value); models, endpoints and the default "
        "backend live here and are saved to <span class='mono'>sentinel.config.yaml</span>. The "
        "topbar pill and every run read this same saved default — no env override.</p>"
        "</form></div>"
    )

    generation = (
        "<h2 class='sec'>Generation defaults</h2>"
        "<div class='card'><form method='post' action='/settings/generation' class='set-grid'>"
        f"{_gen_row(cfg.generation)}"
        "<div class='set-actions'><button class='btn' type='submit'>Save generation</button></div>"
        "<p class='note'>Global defaults. A per-agent field left blank inherits these.</p>"
        "</form></div>"
    )

    memory = (
        "<h2 class='sec'>Memory</h2>"
        "<div class='card'><form method='post' action='/settings/memory' class='set-grid'>"
        f"<div style='display:flex;gap:20px;flex-wrap:wrap'>"
        f"{_chk('entity_memory','entity memory enabled',cfg.memory.entity_memory)}"
        f"{_chk('inject_org_prefs','inject org preferences',cfg.memory.inject_org_prefs)}</div>"
        + _num("retention_days", "Retention (days)", cfg.memory.retention_days, step="1", mn="1")
        + "<div class='set-actions'><button class='btn' type='submit'>Save memory</button></div>"
        "</form></div>"
    )

    gov = cfg.governance
    sovereign = gov.compliance_mode == "on_prem_required"
    governance = (
        "<h2 class='sec'>Governance · sovereignty policy</h2>"
        "<div class='card'><form method='post' action='/settings/governance' class='set-grid'>"
        + _sel("compliance_mode", "Compliance mode", gov.compliance_mode, [
            ("cloud_ok", "☁ cloud_ok — Gemini grounding allowed"),
            ("on_prem_preferred", "on_prem_preferred — prefer on-prem, cloud permitted"),
            ("on_prem_required", "🔒 on_prem_required — NO cloud (Gemini blocked)"),
        ])
        + "<div style='display:flex;gap:20px;flex-wrap:wrap'>"
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
        "<h2 class='sec'>Public search provider</h2>"
        "<div class='card'><form method='post' action='/settings/search' class='set-grid'>"
        "<div class='row2'>"
        + _sel("provider", "Provider", s.provider, [
            ("gemini", "☁ Gemini (google_search — cloud)"),
            ("searxng", "⛨ SearXNG (self-hosted — sovereign)"),
            ("duckduckgo", "DuckDuckGo (keyless)"),
            ("brave", "Brave (BRAVE_API_KEY)"),
            ("serpapi", "SerpAPI (SERPAPI_API_KEY)"),
        ])
        + _sel("onprem_fallback", "On-prem fallback (when policy forbids Gemini)",
               s.onprem_fallback, [
                   ("searxng", "⛨ SearXNG (self-hosted)"),
                   ("duckduckgo", "DuckDuckGo (keyless)"),
                   ("brave", "Brave"),
                   ("serpapi", "SerpAPI"),
               ])
        + "</div>"
        + _num("results", "Results per query", s.results, step="1", mn="1", mx="20")
        + f"<div class='set-actions'>{_key_pill('BRAVE_API_KEY', brave_key_set)}"
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
        "<h2 class='sec'>Agents — competitor</h2><div class='grid' style='gap:12px'>"
        + "".join(_agent_card(k, cfg.agents[k]) for k in comp)
        + "</div><h2 class='sec'>Agents — client</h2><div class='grid' style='gap:12px'>"
        + "".join(_agent_card(k, cfg.agents[k]) for k in clnt)
        + "</div>"
    )

    # --- Models · Gemma-4 role tiering (SENTINEL-011) ----------------------------------- #
    role_map = cfg.backend.roles or {}
    tiering_on = bool(role_map)

    def _role_row(role: str, tier: str, endpoint: str) -> str:
        opt = role_map.get(role)
        model_val = escape(opt.model) if opt else ""
        base_val = escape(opt.api_base) if (opt and opt.api_base) else ""
        return (
            "<div class='row2'>"
            f"<div><label class='lbl'>{escape(role)} <span class='note' "
            f"style='font-weight:400'>({escape(tier)})</span></label>"
            f"<input name='model__{escape(role)}' value='{model_val}' "
            "placeholder='blank ⇒ flat vLLM fallback'></div>"
            f"<div><label class='lbl'>endpoint</label>"
            f"<input name='api_base__{escape(role)}' value='{base_val}' "
            f"placeholder='{escape(endpoint)}'></div>"
            "</div>"
        )

    models = (
        "<h2 class='sec'>Models · Gemma-4 role tiering</h2>"
        "<div class='card'><form method='post' action='/settings/models' class='set-grid'>"
        + "".join(_role_row(r, tier, ep) for r, tier, ep in _ROLE_TIERS)
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
        "<h2 class='sec'>Coordinator · A2A topology</h2>"
        "<div class='card'><form method='post' action='/settings/coordinator' class='set-grid'>"
        + _chk("enabled", "coordinator enabled (delegate to specialists via AgentTool)", co.enabled)
        + "<label class='lbl' style='opacity:.5'>"
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
        "<h2 class='sec'>Strategy · action plan</h2>"
        "<div class='card'><form method='post' action='/settings/strategy' class='set-grid'>"
        + _chk("enabled", "strategy enabled (append a tool-free strategist + merge an action plan)",
               st.enabled)
        + "<div class='row2'>"
        f"<div><label class='lbl' for='st_comp'>Competitor playbook (stem)</label>"
        f"<input id='st_comp' name='competitor_playbook' value='{escape(st.competitor_playbook)}'></div>"
        f"<div><label class='lbl' for='st_clnt'>Client playbook (stem)</label>"
        f"<input id='st_clnt' name='client_playbook' value='{escape(st.client_playbook)}'></div>"
        "</div>"
        f"<div><label class='lbl' for='st_dir'>Playbook directory</label>"
        f"<input id='st_dir' name='playbook_dir' value='{escape(st.playbook_dir)}'></div>"
        "<div class='set-actions'><button class='btn' type='submit'>Save strategy</button></div>"
        f"<p class='note'><b>Ships dark.</b> When on, a tool-free strategist reads the finished "
        "artifact and a deterministic merge adds an assessment + prioritized action plan (client: "
        "+ objection handling), shaped by an admin-editable Markdown playbook — change house "
        f"strategy by editing a <span class='mono'>.md</span>, effective next run. {pb_note}.</p>"
        "</form></div>"
    )

    prompts = (
        "<h2 class='sec'>Prompts</h2>"
        + "".join(_prompt_card(k, cfg.prompts[k]) for k in cfg.prompts)
    )

    content = (
        banner + backends + models + coordinator + governance + search
        + strategy + generation + memory + agents + prompts
    )
    return shell(active="settings", title="Settings", content=content, backend=backend)


def error_page(message: str, *, hint: str = "", backend: str = "gemini") -> str:
    hint_html = f"<p class='note'>{escape(hint)}</p>" if hint else ""
    content = (f"<div class='card err'><h2 class='sec' style='color:var(--bad)'>Run failed</h2>"
               f"<p>{escape(message)}</p>{hint_html}"
               "<p class='note'><a href='/new' style='color:var(--accent-2)'>← Back to New Run</a></p></div>")
    return shell(active="new", title="Error", content=content, backend=backend)
