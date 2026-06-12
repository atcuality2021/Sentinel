"""Dashboard UI for Sentinel — app shell, pages, and artifact rendering.

Presentation-only. An app shell (collapsible sidebar + top bar) wraps every page. The
dashboard home shows KPI cards and charts driven by an in-memory run store; the signature
chart is the public-vs-private *provenance* split — the sovereignty thesis as a number.

All model/user-derived text is passed through ``html.escape`` (artifacts are built from web
search + model output, so they are untrusted by default — no stored XSS via a finding).
"""

from __future__ import annotations

import json
import re as _re
from html import escape
from urllib.parse import quote

from sentinel.artifacts.schemas import AccountBrief, Battlecard, Boundary, Finding, Gap, Source
from sentinel.kb.url_guard import safe_href
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
@media print{.sidebar,.shell-nav,.proj-subnav,.set-actions,.btn,nav,header{display:none!important}
  .shell-main{margin:0!important;padding:0!important}body{background:#fff;color:#111}}

/* ---- project subnav ---- */
.proj-subnav{border-bottom:1px solid var(--line);background:rgba(10,14,22,.88);
  backdrop-filter:blur(8px);position:sticky;top:57px;z-index:4}
.proj-subnav-inner{max-width:1280px;margin:0 auto;width:100%;display:flex;
  align-items:center;gap:2px;padding:0 22px}
.proj-tab{display:inline-flex;align-items:center;gap:7px;padding:11px 14px;
  color:var(--muted);font-size:13.5px;font-weight:500;border-bottom:2px solid transparent;
  white-space:nowrap;cursor:pointer;transition:color .15s,border-color .15s}
.proj-tab:hover{color:var(--ink)}
.proj-tab.active{color:var(--accent-2);border-bottom-color:var(--accent-2)}
.proj-tab svg{flex:0 0 auto}

/* ---- kb upload zone ---- */
.kb-zone{border:2px dashed var(--line);border-radius:14px;padding:40px 24px;
  text-align:center;color:var(--muted);font-size:14px}
.kb-zone:hover{border-color:var(--accent-line);color:var(--ink)}
.kb-types{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:16px}
.kb-type{background:var(--chip);border:1px solid var(--line);border-radius:8px;
  padding:6px 14px;font-size:12.5px;font-family:ui-monospace,Menlo,monospace;color:var(--muted)}
.btn-sm{padding:4px 12px;font-size:12px;border-radius:6px;border:1px solid var(--line);
  background:var(--chip);color:var(--ink);cursor:pointer;display:inline-flex;align-items:center;gap:5px;
  font-weight:500;transition:background .13s,border-color .13s,color .13s;white-space:nowrap}
.btn-sm:hover{background:var(--panel);border-color:var(--accent-line);color:var(--ink)}
.btn-sm.primary{background:var(--accent-soft);border-color:var(--accent-line);color:var(--accent-2)}
.btn-sm.primary:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-sm.ok{background:rgba(52,168,83,.14);border-color:rgba(52,168,83,.4);color:#5bd07f}
.btn-sm.ok:hover{background:var(--ok);color:#fff;border-color:var(--ok)}
.btn-sm.warn{background:rgba(234,179,8,.12);border-color:rgba(234,179,8,.35);color:#d4a017}
.btn-sm.warn:hover{background:#b78a00;color:#fff;border-color:#b78a00}
.btn-sm.bad{border-color:#5a1f1f;background:#1c1011;color:var(--bad)}
.btn-sm.bad:hover{background:var(--bad);color:#fff;border-color:var(--bad)}
/* task rows */
.task-row{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;
  padding:14px 16px;border-bottom:1px solid var(--line)}
.task-row:last-child{border-bottom:0}
.task-row:hover{background:rgba(255,255,255,.02)}
.task-row .tr-obj{font-size:13.5px;font-weight:600;color:var(--accent-2);
  text-decoration:none;display:block;margin-bottom:5px;line-height:1.4}
.task-row .tr-obj:hover{text-decoration:underline}
.task-row .tr-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.task-row .tr-actions{display:flex;gap:6px;align-items:center;flex-wrap:nowrap}
.flash{padding:10px 16px;border-radius:8px;font-size:14px}
.flash.ok{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#4ade80}
.flash.err{background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#f87171}

/* ---- consulting report ---- */
.rpt-cover{background:linear-gradient(135deg,#0d1627 0%,#0b0e14 60%,#0f1a2e 100%);
  border:1px solid var(--line);border-radius:16px;padding:48px 40px 40px;margin-bottom:28px;
  position:relative;overflow:hidden}
.rpt-cover::before{content:'';position:absolute;top:-40px;right:-40px;width:280px;height:280px;
  border-radius:50%;background:radial-gradient(circle,rgba(66,133,244,.18) 0%,transparent 70%);pointer-events:none}
.rpt-cover .rpt-firm{font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:20px}
.rpt-cover h1{font-size:30px;font-weight:700;letter-spacing:-.4px;line-height:1.2;margin:0 0 10px}
.rpt-cover .rpt-sub{color:var(--muted);font-size:14.5px;margin-bottom:28px;max-width:600px;line-height:1.6}
.rpt-cover .rpt-meta{display:flex;gap:10px;flex-wrap:wrap}
.rpt-tag{background:var(--accent-soft);color:var(--accent-2);border:1px solid var(--accent-line);
  padding:4px 12px;border-radius:999px;font-size:11px;font-weight:600;letter-spacing:.06em}
.rpt-tag.gold{background:rgba(251,191,36,.12);color:#fbbf24;border-color:rgba(251,191,36,.3)}
.rpt-tag.green{background:rgba(52,168,83,.12);color:#5bd07f;border-color:rgba(52,168,83,.3)}
.rpt-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}
.rpt-metric{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 16px;text-align:center}
.rpt-metric .rm-val{font-size:26px;font-weight:700;color:var(--accent-2);letter-spacing:-.5px}
.rpt-metric .rm-lbl{font-size:11px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.07em}
.rpt-sec{margin:32px 0}
.rpt-sec-hd{display:flex;align-items:center;gap:12px;margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.rpt-sec-hd .rpt-num{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;
  color:var(--accent-2);background:var(--accent-soft);border:1px solid var(--accent-line);
  padding:3px 9px;border-radius:6px;white-space:nowrap}
.rpt-sec-hd h2{font-size:18px;font-weight:700;margin:0;letter-spacing:-.2px}
.rpt-callout{background:var(--panel-2);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:0 10px 10px 0;padding:16px 18px;margin:16px 0;font-size:13.5px;line-height:1.6}
.rpt-callout.gold{border-left-color:#fbbf24;background:rgba(251,191,36,.05)}
.rpt-callout.green{border-left-color:var(--ok);background:rgba(52,168,83,.06)}
.rpt-callout b{color:var(--ink)}
.rpt-callout .rpt-cl-label{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);margin-bottom:7px;display:block}
.comp-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:16px 0}
.comp-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;
  display:flex;flex-direction:column;gap:8px}
.comp-card h4{font-size:14px;font-weight:650;margin:0;color:var(--ink)}
.comp-card .cc-tags{display:flex;gap:6px;flex-wrap:wrap}
.comp-card p{font-size:13px;color:var(--muted);line-height:1.55;margin:0}
.comp-card .cc-win{font-size:12.5px;color:var(--accent-2);line-height:1.5}
.acc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}
.acc-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;
  border-top:2px solid var(--accent-line)}
.acc-card h4{font-size:13.5px;font-weight:650;margin:0 0 4px;color:var(--ink)}
.acc-card .ac-vert{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px}
.acc-card p{font-size:12.5px;color:var(--muted);line-height:1.5;margin:0}
.acc-card .ac-entry{font-size:12px;color:var(--accent-2);margin-top:8px;line-height:1.4}
.tier-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin:16px 0}
.tier-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px 18px}
.tier-card.featured{background:linear-gradient(135deg,rgba(66,133,244,.18),rgba(66,133,244,.06));
  border-color:var(--accent-line)}
.tier-card .tc-name{font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.tier-card .tc-price{font-size:26px;font-weight:700;color:var(--ink);letter-spacing:-.5px;margin:0 0 3px}
.tier-card .tc-period{font-size:12px;color:var(--muted);margin-bottom:14px}
.tier-card ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:7px}
.tier-card li{font-size:13px;color:var(--muted);display:flex;align-items:flex-start;gap:8px}
.tier-card li::before{content:'✓';color:var(--ok);font-weight:700;flex:0 0 auto}
.tl{display:flex;flex-direction:column;gap:0;margin:16px 0}
.tl-item{display:grid;grid-template-columns:140px 1fr;gap:16px;position:relative;padding-bottom:24px}
.tl-item:last-child{padding-bottom:0}
.tl-left{display:flex;flex-direction:column;align-items:flex-end;gap:4px;padding-top:2px}
.tl-dot{width:10px;height:10px;border-radius:50%;background:var(--accent);margin-left:auto;margin-top:4px;
  box-shadow:0 0 10px rgba(66,133,244,.5);flex:0 0 auto}
.tl-dot.gold{background:#fbbf24;box-shadow:0 0 10px rgba(251,191,36,.5)}
.tl-dot.green{background:var(--ok);box-shadow:0 0 10px rgba(52,168,83,.5)}
.tl-phase{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.tl-right{border-left:1px solid var(--line);padding-left:20px}
.tl-right h4{font-size:14.5px;font-weight:650;margin:0 0 6px;color:var(--ink)}
.tl-right ul{padding-left:16px;margin:0;display:flex;flex-direction:column;gap:5px}
.tl-right li{font-size:13px;color:var(--muted)}
.action-grid{display:flex;flex-direction:column;gap:10px;margin:16px 0}
.action-row{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px;display:grid;grid-template-columns:60px 1fr 120px 160px;gap:12px;align-items:center}
.action-row .ar-p{font-size:13px;font-weight:700;text-align:center;width:48px;height:28px;
  border-radius:6px;display:flex;align-items:center;justify-content:center}
.ar-p.p0{background:rgba(234,67,53,.18);color:#ff6b6b}
.ar-p.p1{background:rgba(251,191,36,.14);color:#fbbf24}
.ar-p.p2{background:rgba(66,133,244,.14);color:var(--accent-2)}
.ar-p.p3{background:rgba(52,168,83,.12);color:var(--ok)}
.action-row h4{font-size:13.5px;font-weight:650;margin:0 0 3px;color:var(--ink)}
.action-row p{font-size:12.5px;color:var(--muted);margin:0;line-height:1.45}
.action-row .ar-owner{font-size:12px;color:var(--muted);text-align:center}
.action-row .ar-deadline{font-size:12px;color:var(--muted)}
@media(max-width:880px){.rpt-metrics{grid-template-columns:1fr 1fr}.comp-grid{grid-template-columns:1fr}
  .acc-grid{grid-template-columns:1fr 1fr}.tier-grid{grid-template-columns:1fr}
  .action-row{grid-template-columns:50px 1fr}}
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
        "book": "<path d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/><path d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/>",
        "database": "<ellipse cx='12' cy='5' rx='9' ry='3'/><path d='M21 12c0 1.66-4 3-9 3s-9-1.34-9-3'/><path d='M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5'/>",
        "folder": "<path d='M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'/>",
        "brain": "<path d='M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2z'/><path d='M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2z'/>",
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
    ]),
    ("Govern", [
        ("settings", "Settings", "cog", "/settings"),
        ("prompts", "Prompts", "doc", "/settings/prompts"),
        ("personas", "Personas", "agent", "/personas"),
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
        "separated by design.<br><a href='/logout' style='color:#9aa0a6;font-size:11px;"
        "text-decoration:none;margin-top:6px;display:inline-block'>Sign out</a></div>"
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
document.querySelectorAll('form').forEach(function(f){
var a=f.getAttribute('action')||'';
if(a.indexOf('run-plan')>-1||/\\/run$/.test(a))return; // runs redirect to the live timeline — no popup
f.addEventListener('submit',function(){
var b=f.querySelector('button[type=submit],button:not([type])');var m=document.getElementById('ldmsg');
if(m&&b&&b.textContent)m.textContent=b.textContent.trim()+'\\u2026';o.style.display='flex';});});})();
"""


_PROJECT_TABS = [
    ("overview",   "Overview",       "grid"),
    ("kb",         "Knowledge Base", "book"),
    ("tasks",      "Research",       "search"),
    ("memory",     "Memory",         "brain"),
    ("artifacts",  "Artifacts",      "folder"),
    ("report",     "Report",         "doc"),
]


def _project_subnav(project_id: str, active_tab: str, project_name: str = "") -> str:
    """Horizontal tab strip rendered below the topbar when inside a project."""
    pid = escape(project_id)
    hrefs = {
        "overview":  f"/projects/{pid}",
        "kb":        f"/projects/{pid}/kb",
        "tasks":     f"/projects/{pid}/tasks",
        "memory":    f"/projects/{pid}/memory",
        "artifacts": f"/projects/{pid}/artifacts",
        "report":    f"/projects/{pid}/report",
    }
    tabs = "".join(
        f"<a class='proj-tab {'active' if key == active_tab else ''}' href='{hrefs[key]}'>"
        f"{_icon(icon)}{label}</a>"
        for key, label, icon in _PROJECT_TABS
    )
    name_chip = (
        f"<span class='pill' style='margin-right:8px;border-color:var(--accent-line);"
        f"color:var(--accent-2)'>{_icon('plan')}{escape(project_name)}</span>"
        if project_name else ""
    )
    return (
        "<div class='proj-subnav'>"
        f"<div class='proj-subnav-inner'>{name_chip}{tabs}</div>"
        "</div>"
    )


def shell(*, active: str, title: str, content: str, backend: str, head_extra: str = "",
          body_scripts: str = "", project: str = "sovereign", subnav: str = "") -> str:
    """Wrap a content fragment in the full dashboard shell.

    ``project`` labels the top-bar pill.
    ``subnav`` is an optional horizontal tab strip (rendered below the topbar, sticky).
    """
    backend_pill = (
        f"<span class='pill'><span class='dotmark {'v' if backend=='vllm' else 'g'}'></span>"
        f"Backend: <b>{escape(backend)}</b></span>"
    )
    # When inside a project context, suppress the global "New Run" shortcut (Research tab owns it).
    topbar_action = (
        "" if subnav
        else f"<a class='btn ghost' href='/projects'>{_icon('plan')} Projects</a>"
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
        f"{topbar_action}</div></div>"
        f"{subnav}"
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


# --------------------------------------------------------------------------- #
# Finding / gap fragments
# --------------------------------------------------------------------------- #
def _badge(b) -> str:
    # b may be a Boundary enum or a plain string after JSON round-trip
    val = b.value if isinstance(b, Boundary) else str(b)
    cls = "public" if val == Boundary.PUBLIC.value else "private"
    return f"<span class='badge {cls}'>{val}</span>"


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
    # SENTINEL-014 domain artifacts (SoftwareBrief, FinancialProfile, AcademicBrief,
    # NutritionBrief, TravelBrief) use the shared _artifact_html card renderer.
    art_dict = artifact.model_dump() if hasattr(artifact, "model_dump") else dict(artifact)
    content = _artifact_html(type(artifact).__name__, art_dict)
    return shell(active="artifacts", title=type(artifact).__name__, content=content, backend=backend)


# --------------------------------------------------------------------------- #
# Artifacts list
# --------------------------------------------------------------------------- #
def artifacts_page(*, artifacts: list[dict], backend: str, project: str = "sovereign",
                   project_id: str = "") -> str:
    """Artifact list — scoped to a project when project_id is provided (shows project subnav)."""
    subnav = _project_subnav(project_id, "artifacts", project) if project_id else ""
    active = "projects" if project_id else "artifacts"
    title = "Artifacts" if not project_id else f"{project} · Artifacts"

    if not artifacts:
        run_link = (f"<a href='/projects/{escape(project_id)}/tasks' style='color:var(--accent-2)'>"
                    "create a research task</a>") if project_id else (
                        "<a href='/projects' style='color:var(--accent-2)'>start a project</a>")
        content = (f"<div class='card'><div class='empty'>No artifacts yet. "
                   f"{run_link} to generate a battlecard or account brief.</div></div>")
        return shell(active=active, title=title, content=content, backend=backend,
                     project=project, subnav=subnav)

    rows = ""
    for a in artifacts:
        name = escape(a["target"])
        if a.get("project_id") or a.get("entity"):
            name = (f"<a href='{_run_href(a)}' "
                    f"style='color:var(--accent-2)'>{name}</a>")
        # "Add to KB" button — available in project context whenever the run has any content
        kb_btn = ""
        if project_id and a.get("run_id"):
            rid = escape(a["run_id"])
            pid_esc = escape(project_id)
            kb_btn = (
                f"<form method='POST' action='/projects/{pid_esc}/kb/sources/artifact' "
                f"style='display:inline'>"
                f"<input type='hidden' name='run_id' value='{rid}'>"
                f"<button type='submit' class='btn' style='font-size:11px;padding:3px 9px' "
                f"title='Index this artifact into the project Knowledge Base'>"
                f"{_icon('database')} Add to KB</button></form>"
            )
        rows += (
            f"<tr><td><b>{name}</b></td><td>{escape(a['kind'])}</td>"
            f"<td><span class='badge public'>{a['public']}</span>"
            f"<span class='badge private'>{a['private']}</span></td>"
            f"<td><span class='dotmark {'v' if a['backend']=='vllm' else 'g'}'></span> "
            f"<span class='mono'>{escape(a['backend'])}</span></td>"
            f"<td class='mono'>{escape(a['reference'])}</td>"
            f"<td class='mono'>{escape(a['when'])}</td>"
            f"<td>{kb_btn}</td></tr>"
        )
    content = (
        "<div class='card' style='padding:6px 8px'><table><thead><tr>"
        "<th>Target</th><th>Kind</th><th>Public / Private</th><th>Backend</th>"
        "<th>Saved to</th><th>When</th><th></th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )
    return shell(active=active, title=title, content=content, backend=backend,
                 project=project, subnav=subnav)


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


# --------------------------------------------------------------------------- #
# Accounts (SENTINEL-004) — entity index + detail (run timeline + memory)
# --------------------------------------------------------------------------- #
def _account_href(entity: str) -> str:
    """Link to an account by its normalized key. ``safe=''`` encodes spaces/slashes so a key
    like ``acme corp`` round-trips through the path param (AC-10)."""
    return f"/accounts/{quote(entity, safe='')}"


def _run_href(run: dict) -> str:
    """Where a run row should take the operator. Prefer the run's PROJECT — that's where the
    tasks, artifacts and KB live. The account page is an entity-keyed CRM memory view and a
    confusing landing target from the dashboard (user feedback 2026-06-12); it stays only as
    the fallback for legacy/unscoped runs that have no project_id."""
    pid = run.get("project_id")
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return _account_href(run.get("entity", ""))


def _fmt_when(dt) -> str:
    # tz-aware UTC in storage; show the operator local wall-clock.
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def accounts_page(*, accounts: list, backend: str, ok: str = "", project: str = "sovereign") -> str:
    """The Accounts index — one row per distinct entity (AC-1, AC-2)."""
    banner = f"<div class='card banner ok' style='margin-bottom:18px'>{escape(ok)}</div>" if ok else ""
    if not accounts:
        content = (banner + "<div class='card'><div class='empty'>No accounts yet. "
                   "<a href='/projects' style='color:var(--accent-2)'>Run a task</a> against a "
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
        "<div><label class='lbl' for='p-client'>Target / client website (optional)</label>"
        "<input id='p-client' name='client_url' placeholder='https://assam.gov.in'></div>"
        "<div style='grid-column:1/-1'><label class='lbl' for='p-ctx'>Context &amp; use case (optional)</label>"
        "<textarea id='p-ctx' name='context' rows='3' "
        "placeholder='e.g. This is my website biltiq.ai and this is the Assam govt website — "
        "understand their major works and issues (flood, border security, agriculture), then map "
        "our services to an AI-based solution for better governance.'></textarea></div>"
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
    saved_names = [p.name for p in (saved_personas or [])]
    builtins = [p for p in _PERSONAS if p != "custom"]
    personas = "<option value='auto' selected>auto — let the agent pick</option>" + "".join(
        f"<option value='{escape(p)}'>{escape(p)}</option>"
        for p in builtins + saved_names + ["custom"])
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
                  gen: dict | None = None) -> str:
    """Persona library (/personas): built-in audience profiles (read-only), saved personas
    (create/delete), and an LLM generator that drafts a full profile from a plain-English
    audience description. Generated values arrive via gen_* query params (PRG) and prefill
    the create form — the user always reviews before saving."""
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

    if saved:
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
            for p in saved)
    else:
        saved_cards = ("<div class='card'><div class='empty'>No saved personas yet — "
                       "create one above or generate from a description.</div></div>")

    # --- built-in (read-only) cards -------------------------------------------
    builtin_cards = "".join(
        "<div class='card' style='margin-bottom:10px'>"
        f"<div><b>{escape(name)}</b> <span class='note'>— built-in</span>"
        + _profile_rows(
            profile.get("reading_level", "professional"), profile.get("tone", "neutral"),
            profile.get("format", "brief"), profile.get("source_policy", ""))
        + ("<div class='note' style='margin-top:6px'>Default audience — tasks with this persona "
           "skip the extra render pass.</div>" if not profile else "")
        + "</div></div>"
        for name, profile in PERSONA_PROFILES.items())

    content = (
        banner + generator + create_form
        + f"<div class='section-h'><h2>Saved personas <span class='note'>{len(saved)}</span></h2></div>"
        + saved_cards
        + "<div class='section-h' style='margin-top:24px'><h2>Built-in personas</h2></div>"
        + "<div class='note' style='margin-bottom:10px'>Defined in code (read-only). Pick "
        "<b>auto</b> in the task form to let the agent choose one by domain.</div>"
        + builtin_cards)
    return shell(active="personas", title="Personas", content=content, backend=backend)


def _task_status_badge(status: str, degraded: bool = False) -> str:
    """Colour-coded status badge. Degraded done→partial (amber)."""
    if status == "done" and degraded:
        return "<span class='badge' style='background:rgba(234,179,8,.16);color:#d4a017'>partial</span>"
    _map = {
        "created":  ("rgba(100,100,100,.18)", "#9aa0a6", "created"),
        "planned":  ("rgba(66,133,244,.16)",  "#8ab4f8", "planned"),
        "running":  ("rgba(66,133,244,.22)",  "#8ab4f8", "running…"),
        "done":     ("rgba(52,168,83,.18)",   "#5bd07f", "done"),
        "failed":   ("rgba(234,67,53,.18)",   "#ff6b6b", "failed"),
        "rejected": ("rgba(220,38,38,.18)",   "#dc2626", "rejected"),
    }
    bg, color, label = _map.get(status, ("transparent", "var(--muted)", status))
    return f"<span class='badge' style='background:{bg};color:{color}'>{escape(label)}</span>"


# Optional steering prompt that rides a re-run: lands in task.context → _plan_seeds →
# every agent's vertical_context. Compact inline input so the task rows stay one-line.
_RERUN_CTX = (
    "<input name='context' placeholder='guidance for better results (optional)' "
    "style='font-size:11px;padding:2px 6px;height:24px;width:210px;border-radius:4px;"
    "border:1px solid var(--line);background:var(--surface2);color:var(--text);"
    "vertical-align:middle;margin-right:4px'>"
)

_RERUN_SEL = (
    "<select name='backend' style='font-size:11px;padding:2px 4px;height:24px;"
    "border-radius:4px;border:1px solid var(--line);background:var(--surface2);"
    "color:var(--text);cursor:pointer;vertical-align:middle;color-scheme:dark'>"
    "<option value='' style='background:#16191f;color:#e8eaed'>auto</option>"
    "<option value='gemini' style='background:#16191f;color:#e8eaed'>☁ Gemini</option>"
    "<option value='vllm' style='background:#16191f;color:#e8eaed'>🔒 vLLM 12B</option>"
    "<option value='vllm-26b' style='background:#16191f;color:#e8eaed'>🔒 vLLM 26B</option>"
    "</select>"
)


def _task_row(task, pid: str, show_full_obj: bool = False) -> str:
    """Rich task row: objective link, meta pills, action buttons (View / Retry / Delete)."""
    tid = escape(task.id)
    obj = task.objective or ""
    display_obj = obj if show_full_obj else (obj[:110] + "…" if len(obj) > 110 else obj)
    status = task.status
    has_result = bool(getattr(task, "result", None))
    degraded = has_result and getattr(task.result, "degraded", False) if has_result else False

    # meta pills
    meta = (
        _task_status_badge(status, degraded)
        + f"<span class='tag' style='color:var(--muted)'>{escape(task.domain.name)}</span>"
    )
    if has_result and degraded:
        arts = getattr(task.result, "artifacts", []) or []
        meta += f"<span class='tag' style='color:#d4a017'>{len(arts)} artifact{'s' if len(arts) != 1 else ''} produced</span>"
    if has_result and not degraded:
        arts = getattr(task.result, "artifacts", []) or []
        if arts:
            meta += f"<span class='tag' style='color:#5bd07f'>{len(arts)} artifact{'s' if len(arts) != 1 else ''}</span>"

    # action buttons
    view_btn = (
        f"<a class='btn-sm ok' href='/projects/{pid}/tasks/{tid}'>"
        f"{_icon('doc')} View</a>"
        if has_result else
        f"<a class='btn-sm' href='/projects/{pid}/tasks/{tid}'>"
        f"{_icon('doc')} Details</a>"
    )
    retry_btn = ""
    if status in ("failed", "done"):
        retry_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn-sm warn' type='submit' title='Re-run this task' style='margin-left:4px'>"
            f"{_icon('bolt')} Re-run</button></form>"
        )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn-sm bad' type='submit' style='font-size:11px;padding:3px 8px'>"
        f"Delete</button></form>"
    )

    return (
        f"<div class='task-row'>"
        f"<div>"
        f"<a class='tr-obj' href='/projects/{pid}/tasks/{tid}'>{escape(display_obj)}</a>"
        f"<div class='tr-meta'>{meta}</div>"
        f"</div>"
        f"<div class='tr-actions'>{view_btn}{retry_btn}{del_btn}</div>"
        f"</div>"
    )


def _result_brief_card(task, pid: str) -> str:
    """Compact deliverable card for a completed task on the overview page.

    Shows: objective, domain, a 1-2 sentence summary from the result, and key metrics
    extracted from the artifact (dept count, product count, citation count, etc.).
    """
    tid = escape(task.id)
    obj = escape(task.objective or "")
    domain = task.domain.name if task.domain else ""

    # Pull summary text from result
    result = getattr(task, "result", None)
    summary = ""
    metrics: list[str] = []
    if result:
        summary = escape(getattr(result, "summary", "") or "")
        payload = getattr(result, "dashboard_payload", {}) or {}
        arts = payload.get("artifacts") or payload
        if isinstance(arts, dict):
            # Domain-specific metrics
            for v in arts.values():
                if not isinstance(v, dict):
                    continue
                if "department_mappings" in v:
                    n = len(v.get("department_mappings") or [])
                    if n:
                        metrics.append(f"{n} departments mapped")
                    chals = len(v.get("client_challenges") or [])
                    if chals:
                        metrics.append(f"{chals} client challenges")
                if "products_found" in v:
                    n = len(v.get("products_found") or [])
                    if n:
                        metrics.append(f"{n} products found")
                    winner = str(v.get("winner") or "").strip()
                    if winner and winner.lower() not in ("null", "none", ""):
                        metrics.append(f"Winner: {escape(winner[:60])}")
                if "strengths" in v:
                    n = len(v.get("strengths") or [])
                    if n:
                        metrics.append(f"{n} strengths identified")
                if "key_findings" in v:
                    n = len(v.get("key_findings") or [])
                    if n:
                        metrics.append(f"{n} key findings")
            cites = getattr(result, "citations", []) or []
            if cites:
                metrics.append(f"{len(cites)} citations")

    metrics_html = ""
    if metrics:
        chips = "".join(
            f"<span class='tag' style='color:var(--accent-2);margin-right:6px'>{m}</span>"
            for m in metrics[:5]
        )
        metrics_html = f"<div style='margin-top:8px'>{chips}</div>"

    summary_html = (
        f"<p style='margin:8px 0 0;font-size:13px;color:var(--text-secondary);line-height:1.5'>{summary}</p>"
        if summary else ""
    )

    domain_color = {
        "govt_proposal": "#a78bfa",
        "product_research": "#2dd4bf",
        "market": "#4ea1ff",
        "software": "#fb923c",
        "finance": "#5bd07f",
        "academic": "#d4a800",
    }.get(domain, "var(--muted)")

    rerun_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/run' style='display:inline'>"
        f"{_RERUN_CTX}{_RERUN_SEL}"
        f"<button class='btn-sm ghost' type='submit' title='Run this task again' style='margin-left:4px'>"
        f"{_icon('bolt')} Re-run</button></form>"
    )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline;margin-left:4px'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn-sm' type='submit' "
        f"style='background:transparent;border-color:rgba(220,38,38,.3);color:#f87171;"
        f"padding:3px 8px;font-size:11px'>Delete</button></form>"
    )
    return (
        f"<div class='card' style='border-left:3px solid {domain_color};margin-bottom:10px'>"
        f"<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:12px'>"
        f"<div style='flex:1'>"
        f"<a href='/projects/{pid}/tasks/{tid}' style='font-weight:600;font-size:14px;"
        f"color:var(--text);text-decoration:none;line-height:1.4'>{obj}</a>"
        f"<div style='margin-top:6px'>"
        f"<span class='tag' style='color:{domain_color}'>{escape(domain)}</span>"
        f"<span class='tag' style='color:#5bd07f'>done</span>"
        f"</div>"
        f"{summary_html}"
        f"{metrics_html}"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;gap:6px;flex-shrink:0;align-items:flex-end'>"
        f"<a class='btn-sm ok' href='/projects/{pid}/tasks/{tid}'>{_icon('doc')} View</a>"
        f"<div>{rerun_btn}{del_btn}</div>"
        f"</div>"
        f"</div></div>"
    )


def _pending_task_row(task, pid: str) -> str:
    """Compact row for a task that hasn't produced a result yet."""
    tid = escape(task.id)
    obj = escape(task.objective or "")
    domain = task.domain.name if task.domain else ""
    status = task.status
    badge = _task_status_badge(status, False)
    run_btn = ""
    if status in ("planned", "created"):
        run_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline;margin-left:6px'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn-sm' type='submit' style='margin-left:4px'>{_icon('bolt')} Run</button></form>"
        )
    elif status == "failed":
        run_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline;margin-left:6px'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn-sm warn' type='submit' style='margin-left:4px'>{_icon('bolt')} Retry</button></form>"
        )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline;margin-left:6px'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn-sm' type='submit' "
        f"style='background:transparent;border-color:rgba(220,38,38,.4);color:#f87171'>"
        f"Delete</button></form>"
    )
    return (
        f"<div class='task-row'>"
        f"<div><a class='tr-obj' href='/projects/{pid}/tasks/{tid}'>{obj}</a>"
        f"<div class='tr-meta'>{badge}"
        f"<span class='tag' style='color:var(--muted)'>{escape(domain)}</span></div></div>"
        f"<div class='tr-actions'>{run_btn}{del_btn}</div></div>"
    )


def project_detail_page(*, project, tasks: list, backend: str,
                        vllm_model: str = "gemma-4-12b-it", sovereign: bool = False,
                        ok: str = "", err: str = "",
                        kb_source_count: int = 0) -> str:
    """Overview tab — project CRUD, context, quick-add source, built/building tasks."""
    pid = escape(project.id)
    site = (f"<a href='{escape(project.website)}' rel='noopener' target='_blank' "
            f"style='color:var(--accent-2)'>{escape(project.website)}</a>") if project.website else "—"

    done_tasks  = [t for t in tasks if t.status == "done"]
    pending     = [t for t in tasks if t.status not in ("done",)]
    fail_count  = sum(1 for t in tasks if t.status == "failed")

    flash = ""
    if ok:
        flash = f"<div class='flash ok' style='margin-bottom:12px'>{escape(ok)}</div>"
    elif err:
        flash = f"<div class='flash err' style='margin-bottom:12px'>{escape(err)}</div>"

    # ── Edit project form (toggled by button, hidden by default) ──────────────
    _proj_desc = escape(getattr(project, "description", "") or "")
    _proj_ctx  = escape(getattr(project, "context", "") or "")
    _proj_site = escape(project.website or "")
    edit_form = (
        f"<div id='proj-edit-panel' style='display:none;margin-top:12px'>"
        f"<form method='post' action='/projects/{pid}/edit' "
        f"style='display:grid;gap:12px;max-width:600px'>"
        f"<div><label class='lbl'>Project name</label>"
        f"<input name='name' value='{escape(project.name)}' style='width:100%'></div>"
        f"<div><label class='lbl'>Website / primary source URL</label>"
        f"<input name='website' value='{_proj_site}' "
        f"placeholder='https://example.com' style='width:100%'></div>"
        f"<div><label class='lbl'>Description</label>"
        f"<input name='description' value='{_proj_desc}' "
        f"placeholder='What is this project researching?' style='width:100%'></div>"
        f"<div><label class='lbl'>Agent context "
        f"<span class='note' style='font-weight:400'>"
        f"— prepended to every research task in this project</span></label>"
        f"<textarea name='context' rows='3' style='width:100%;resize:vertical' "
        f"placeholder='e.g. Focus on the Indian market. Prioritise recent data from 2024-2025. "
        f"This research is for an enterprise pitch deck.'>"
        f"{_proj_ctx}</textarea></div>"
        f"<div style='display:flex;gap:8px'>"
        f"<button class='btn' type='submit'>Save changes</button>"
        f"<button type='button' class='btn ghost' "
        f"onclick=\"document.getElementById('proj-edit-panel').style.display='none';"
        f"document.getElementById('proj-edit-btn').style.display=''\">Cancel</button>"
        f"</div></form></div>"
        f"<script>function _toggleEdit(){{"
        f"var p=document.getElementById('proj-edit-panel'),"
        f"b=document.getElementById('proj-edit-btn');"
        f"p.style.display=p.style.display==='none'?'block':'none';"
        f"b.style.display=p.style.display==='block'?'none':'';}}</script>"
    )

    # ── Project header ────────────────────────────────────────────────────────
    fail_pill = (
        f"<span class='pill' style='border-color:rgba(234,67,53,.4);color:#ff6b6b'>"
        f"Failed: <b>{fail_count}</b></span>"
    ) if fail_count else ""

    desc_html = ""
    proj_desc = getattr(project, "description", "") or ""
    if proj_desc:
        desc_html = f"<p class='note' style='margin:8px 0 0'>{escape(proj_desc)}</p>"

    proj_ctx = getattr(project, "context", "") or ""
    ctx_pill = (
        f"<span class='pill' style='border-color:rgba(99,102,241,.4);color:#a5b4fc' "
        f"title='{escape(proj_ctx[:200])}'>📋 Agent context set</span>"
    ) if proj_ctx else ""

    header = (
        f"<div class='card'>{flash}"
        f"<div class='section-h' style='margin-top:0'>"
        f"<div style='display:flex;align-items:center;gap:10px'>"
        f"<h2 style='margin:0'>{escape(project.name)}</h2>"
        f"<button id='proj-edit-btn' type='button' class='btn ghost' "
        f"style='padding:4px 10px;font-size:12px' onclick='_toggleEdit()'>✏ Edit</button>"
        f"</div>"
        f"<a class='btn' href='/projects/{pid}/tasks'>{_icon('bolt')} New Research Task</a></div>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-top:8px'>"
        + (f"<span class='pill'>Website: <b>{site}</b></span>" if project.website else "")
        + f"<span class='pill' style='border-color:rgba(52,168,83,.4);color:#5bd07f'>"
        f"Completed: <b>{len(done_tasks)}</b></span>"
        f"<span class='pill'>In progress / planned: <b>{len(pending)}</b></span>"
        f"{fail_pill}{ctx_pill}</div>"
        f"{desc_html}"
        f"{edit_form}"
        f"</div>"
    )

    # ── Quick-add source (compact inline form) ────────────────────────────────
    quick_source = (
        f"<div class='card' style='margin-top:16px'>"
        f"<div style='font-weight:600;font-size:13px;margin-bottom:12px'>📎 Add sources for the agent to use</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>"

        # ── Left: URL input (type auto-inferred server-side) ──
        f"<div>"
        f"<label class='lbl' style='margin-bottom:4px;display:block'>🔗 Paste a URL</label>"
        f"<form method='post' action='/projects/{pid}/kb/sources' style='display:flex;gap:6px'>"
        f"<input type='hidden' name='redirect' value='overview'>"
        f"<input name='url' placeholder='Website, article, or PDF link…' style='flex:1;min-width:0'>"
        f"<button class='btn' type='submit' style='white-space:nowrap;padding:8px 14px'>"
        f"{_icon('bolt')} Add</button>"
        f"</form>"
        f"<p class='note' style='margin:5px 0 0;font-size:11px'>Type is detected automatically — web, PDF, or social</p>"
        f"</div>"

        # ── Right: File upload (multiple files) ──
        f"<div>"
        f"<label class='lbl' style='margin-bottom:4px;display:block'>📄 Upload files <span class='note' style='font-weight:400'>&nbsp;·&nbsp;PDF, TXT, MD</span></label>"
        f"<form method='post' action='/projects/{pid}/kb/upload' enctype='multipart/form-data' style='display:flex;gap:6px'>"
        f"<input type='hidden' name='redirect' value='overview'>"
        f"<input type='file' name='files' multiple accept='.pdf,.txt,.md' "
        f"style='flex:1;min-width:0;font-size:12px;padding:6px 8px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;color:var(--text)'>"
        f"<button class='btn' type='submit' style='white-space:nowrap;padding:8px 14px'>"
        f"{_icon('bolt')} Upload</button>"
        f"</form>"
        f"<p class='note' style='margin:5px 0 0;font-size:11px'>Select one or more files to index into the Knowledge Base</p>"
        f"</div>"

        f"</div>"
        f"<p class='note' style='margin:10px 0 0'>Need to chat with your sources? "
        f"<a href='/projects/{pid}/kb' style='color:var(--accent-2)'>Open the full Knowledge Base</a></p>"
        f"</div>"
    )

    # ── What has been built (completed tasks with actual findings) ─────────────
    if done_tasks:
        brief_cards = "".join(_result_brief_card(t, pid) for t in done_tasks)
        built_html = (
            "<div class='section-h' style='margin-top:24px'>"
            "<h2>What we have built</h2>"
            f"<a class='btn ghost' href='/projects/{pid}/artifacts'>All artifacts</a></div>"
            + brief_cards
        )
    else:
        built_html = ""

    # ── What we are building (pending / in-progress tasks) ────────────────────
    if pending:
        p_rows = "".join(_pending_task_row(t, pid) for t in pending)
        building_html = (
            "<div class='section-h' style='margin-top:24px'>"
            "<h2>What we are building</h2>"
            f"<a class='btn ghost' href='/projects/{pid}/tasks'>Manage</a></div>"
            f"<div class='card' style='padding:0'>{p_rows}</div>"
        )
    else:
        building_html = ""

    # ── Empty state ────────────────────────────────────────────────────────────
    if not tasks:
        building_html = (
            "<div class='card' style='margin-top:16px;text-align:center;padding:32px 16px'>"
            f"<div style='font-size:32px;margin-bottom:12px'>🔬</div>"
            f"<div style='font-weight:600;margin-bottom:8px'>No research tasks yet</div>"
            "<p class='note' style='max-width:400px;margin:0 auto 16px'>Add your first research task — "
            "define what you want to investigate, choose a domain, and the agent pipeline does the rest.</p>"
            f"<a class='btn' href='/projects/{pid}/tasks'>{_icon('bolt')} Create first task</a>"
            "</div>"
        )

    # ── Quick-links row ────────────────────────────────────────────────────────
    _kb_count_label = (
        f"<span style='color:var(--accent-2);font-weight:600'>{kb_source_count}</span> source{'s' if kb_source_count != 1 else ''} indexed"
        if kb_source_count else "No sources yet"
    )
    quicklinks = (
        "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:24px'>"
        f"<a href='/projects/{pid}/kb' style='display:block;text-decoration:none'>"
        "<div class='card' style='text-align:center;padding:16px 10px'>"
        "<div style='font-size:20px;margin-bottom:6px'>📚</div>"
        "<div style='font-weight:600;font-size:13px'>Knowledge Base</div>"
        f"<p class='note' style='margin:4px 0 0;font-size:12px'>{_kb_count_label}</p></div></a>"
        f"<a href='/projects/{pid}/memory' style='display:block;text-decoration:none'>"
        "<div class='card' style='text-align:center;padding:16px 10px'>"
        "<div style='font-size:20px;margin-bottom:6px'>🧠</div>"
        "<div style='font-weight:600;font-size:13px'>Memory</div>"
        "<p class='note' style='margin:4px 0 0;font-size:12px'>Facts &amp; episodic records</p></div></a>"
        f"<a href='/projects/{pid}/report' style='display:block;text-decoration:none'>"
        "<div class='card' style='text-align:center;padding:16px 10px'>"
        "<div style='font-size:20px;margin-bottom:6px'>📄</div>"
        "<div style='font-weight:600;font-size:13px'>Report</div>"
        "<p class='note' style='margin:4px 0 0;font-size:12px'>Full compiled report</p></div></a>"
        "</div>"
    )

    # ── Danger zone ────────────────────────────────────────────────────────────
    danger_zone = (
        "<div class='card' style='margin-top:32px;border-color:#5a1f1f;background:#140c0c'>"
        "<div style='display:flex;align-items:center;gap:10px;margin-bottom:14px'>"
        f"<span style='color:var(--bad);font-size:13px;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:.1em'>⚠ Danger Zone</span></div>"
        "<div style='display:flex;align-items:flex-start;justify-content:space-between;"
        "flex-wrap:wrap;gap:16px;padding:16px;background:#1c1011;border-radius:10px;"
        "border:1px solid #5a1f1f'>"
        "<div>"
        "<div style='font-weight:650;font-size:14px;margin-bottom:6px'>Delete this project</div>"
        "<p class='note' style='margin:0;max-width:520px'>Permanently removes the project, "
        "all its tasks, plans, and KB sources. "
        "Episodic memory run records are kept.</p>"
        "</div>"
        f"<form method='post' action='/projects/{pid}/delete' "
        f"onsubmit='return confirm(\"Delete project \" + {escape(json.dumps(project.name), quote=True)} + \"? All tasks and data will be permanently removed.\")'>"
        "<button class='btn' type='submit' "
        "style='background:#7f1d1d;border:1px solid #dc2626;color:#fca5a5;"
        "padding:10px 18px;flex:0 0 auto'>"
        f"{_icon('shield')} Delete project</button></form>"
        "</div></div>"
    )

    content = header + quick_source + built_html + building_html + quicklinks + danger_zone
    return shell(
        active="projects", title=project.name, content=content, backend=backend,
        project=project.name,
        subnav=_project_subnav(project.id, "overview", project.name),
    )


def project_tasks_page(*, project, tasks: list, backend: str,
                       vllm_model: str = "gemma-4-12b-it", sovereign: bool = False,
                       saved_personas: list | None = None) -> str:
    """Research/Tasks tab — task creation form + full task list."""
    pid = escape(project.id)
    form_html = _task_form(project.id, default_backend=backend,
                           vllm_model=vllm_model, sovereign=sovereign,
                           project_context=getattr(project, "context", "") or "",
                           saved_personas=saved_personas)
    failed_count = sum(1 for t in tasks if t.status == "failed")

    # When tasks already exist, collapse the form behind a toggle button so the
    # task list is immediately visible on load.
    if tasks:
        form_block = (
            "<div style='margin-bottom:24px'>"
            "<div class='section-h' style='margin-bottom:0'>"
            "<button type='button' class='btn ghost' style='font-size:13px' "
            "onclick=\"var p=document.getElementById('new-task-panel');"
            "p.style.display=p.style.display==='none'?'block':'none'\">"
            "＋ New research task</button></div>"
            "<div id='new-task-panel' style='display:none;margin-top:12px'>"
            f"{form_html}</div></div>"
        )
    else:
        form_block = form_html + "<div style='margin-top:24px'></div>"

    if tasks:
        rows = "".join(_task_row(t, pid, show_full_obj=True) for t in tasks)
        failed_note = (
            f"<span class='tag' style='color:#ff6b6b;margin-left:6px'>"
            f"{failed_count} failed</span>"
        ) if failed_count else ""
        tasks_html = (
            f"<div class='section-h'><h2>Tasks{failed_note}</h2></div>"
            f"<div class='card' style='padding:0'>{rows}</div>"
        )
    else:
        tasks_html = (
            "<div class='section-h'><h2>Tasks</h2></div>"
            "<div class='card'><div class='empty'>No tasks yet — create one above.</div></div>"
        )
    content = form_block + tasks_html
    return shell(
        active="projects", title=f"{project.name} · Research", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "tasks", project.name),
    )


def _kb_error_friendly(raw: str) -> str:
    """Translate a raw embed/crawl error string into a human-readable one-liner."""
    if not raw:
        return ""
    low = raw.lower()
    if "401" in low or "unauthorized" in low:
        return "Embedding unavailable — API key rejected. Check VLLM_API_KEY in .env."
    if "403" in low or "forbidden" in low:
        return "Access denied by embedding server."
    if "404" in low:
        return "Embedding endpoint not found. Check EMBED_API_BASE in .env."
    if "connect" in low or "connection" in low or "refused" in low:
        return "Cannot reach embedding server. Is it running?"
    if "timeout" in low:
        return "Embedding server timed out."
    if "empty" in low or "nothing to index" in low:
        return "No content found to index."
    return raw[:120]


def project_kb_page(*, project, sources: list, backend: str, ok: str = "", err: str = "") -> str:
    """Knowledge Base tab — live crawl form + indexed sources list."""
    pid = escape(project.id)

    # Status → badge colour
    _status_colour = {
        "indexed": "var(--public)", "crawling": "var(--accent-2)",
        "pending": "var(--ink-3)", "failed": "var(--bad)",
    }

    flash = ""
    if ok:
        flash = f"<div class='flash ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        flash = f"<div class='flash err' style='margin-bottom:16px'>{escape(err)}</div>"

    # Add-source form — pre-fill URL with project website if set
    website_val = escape(getattr(project, "website", "") or "")
    website_prefill = f" value='{website_val}'" if website_val else ""

    add_form = (
        "<div class='card'>"
        "<div class='section-h' style='margin-top:0'><h2>Add Knowledge Source</h2></div>"
        # URL crawl
        f"<form method='post' action='/projects/{pid}/kb/sources' "
        "style='display:grid;gap:12px;max-width:640px'>"
        "<div><label class='lbl'>URL — website, article, or remote PDF</label>"
        f"<input name='url' required placeholder='https://example.com  or  https://example.com/report.pdf'{website_prefill} "
        "style='width:100%'></div>"
        "<div><label class='lbl'>Source type</label>"
        "<select name='source_type'>"
        "<option value='web'>Web — crawl all pages on this domain</option>"
        "<option value='social'>Social — LinkedIn / YouTube / Crunchbase</option>"
        "<option value='document'>Document — single URL to a PDF or text file</option>"
        "</select></div>"
        f"<div><button class='btn' type='submit'>{_icon('bolt')} Crawl &amp; index</button>"
        "<span class='note' style='margin-left:12px'>Runs in background — refresh to see status.</span></div>"
        "</form>"
        # File upload divider
        "<div style='display:flex;align-items:center;gap:12px;margin:18px 0 14px'>"
        "<hr style='flex:1;border:0;border-top:1px solid var(--line);margin:0'>"
        "<span class='note' style='white-space:nowrap'>or upload a file</span>"
        "<hr style='flex:1;border:0;border-top:1px solid var(--line);margin:0'></div>"
        # File upload form
        f"<form method='post' action='/projects/{pid}/kb/upload' "
        "enctype='multipart/form-data' style='display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;max-width:640px'>"
        "<div style='flex:1;min-width:240px'><label class='lbl'>PDF, TXT, or MD file</label>"
        "<input type='file' name='files' multiple accept='.pdf,.txt,.md' required "
        "style='width:100%;padding:6px 8px;background:var(--panel);border:1px solid var(--line);"
        "border-radius:6px;color:var(--ink);font-size:13px'></div>"
        f"<button class='btn' type='submit' style='margin-bottom:2px'>{_icon('bolt')} Upload &amp; index</button>"
        "</form>"
        "<p class='note' style='margin-top:14px'>Each source is embedded with "
        "<b>Qwen3-VL-Embedding-2B</b> + BM25 and reranked via your cross-encoder. "
        "Agents query this KB automatically via the <code>search_project_kb</code> MCP tool.</p>"
        "</div>"
    )

    # Sources table
    _ART_LABELS = {
        "self_profile": ("Self Profile", "🏢"),
        "competitor": ("Competitor Intelligence", "🎯"),
        "compare": ("Head-to-Head Comparison", "⚖️"),
        "comparison_matrix": ("Comparison Matrix", "⚖️"),
        "battle_card": ("Battle Card", "⚔️"),
        "strategy": ("Strategic Plan", "📋"),
        "program_strategy": ("Program Strategy", "📋"),
        "market_map": ("Market Map", "🗺️"),
    }

    def _friendly_artifact_label(raw_url: str) -> str:
        """Convert artifact://compare:_BiltIQ_AI to 'Head-to-Head Comparison — BiltIQ AI'."""
        if not raw_url.startswith("artifact://"):
            return raw_url
        inner = raw_url[len("artifact://"):]
        # Format: art_type:_Entity_Name  or  art_type_Entity_Name (old format)
        if ":" in inner:
            art_type, entity_part = inner.split(":", 1)
        else:
            # Try to split on first _
            parts = inner.split("_", 1)
            art_type, entity_part = (parts[0], parts[1]) if len(parts) == 2 else (inner, "")
        entity = entity_part.replace("_", " ").strip()
        label_info = _ART_LABELS.get(art_type.lower(), (art_type.replace("_", " ").title(), "📄"))
        label, icon = label_info
        return f"{icon} {label}{(' — ' + entity) if entity else ''}"

    if sources:
        rows = ""
        # Separate artifact sources (auto-ingested research) from web sources
        art_sources = [s for s in sources if s.get("url", "").startswith("artifact://")]
        web_sources = [s for s in sources if not s.get("url", "").startswith("artifact://")]

        def _build_source_row(s):
            status = s.get("status", "pending")
            colour = _status_colour.get(status, "var(--ink-3)")
            badge = f"<span style='color:{colour};font-weight:600;text-transform:uppercase;font-size:11px'>{escape(status)}</span>"
            chunks = s.get("chunk_count", 0)
            stype = s.get("source_type", "web")
            raw_url = s.get("url", "")
            is_artifact = raw_url.startswith("artifact://")
            if is_artifact:
                url_display = escape(_friendly_artifact_label(raw_url))
                url_cell = f"<span style='color:var(--ink);font-size:13px'>{url_display}</span>"
            else:
                url_display = escape(raw_url)
                safe_url = safe_href(raw_url)
                url_cell = (
                    f"<a href='{escape(safe_url)}' target='_blank' rel='noopener noreferrer'>{url_display}</a>"
                    if safe_url else url_display
                )
            raw_err = (s.get("error") or "").split("\n")[0][:200]
            friendly_err = _kb_error_friendly(raw_err)
            err_note = (
                f"<br><span style='color:var(--bad);font-size:11px'>{escape(friendly_err)}</span>"
                if friendly_err else ""
            )
            sid = escape(s["id"])
            delete_btn = (
                f"<form method='post' action='/projects/{pid}/kb/sources/{sid}/delete' "
                "style='display:inline'>"
                "<button class='btn-sm bad' type='submit' title='Remove source'>×</button></form>"
            )
            retry_btn = (
                f"<form method='post' action='/projects/{pid}/kb/sources/{sid}/retry' "
                "style='display:inline;margin-left:4px'>"
                "<button class='btn-sm' type='submit' title='Re-index this source'>↺</button></form>"
                if status == "failed" and not is_artifact else ""
            )
            return (
                f"<tr><td style='max-width:360px;word-break:break-word'>"
                f"{url_cell}{err_note}</td>"
                f"<td><span class='pill' style='font-size:11px'>{escape(stype)}</span></td>"
                f"<td>{badge}</td>"
                f"<td style='text-align:right'>{chunks:,}</td>"
                f"<td style='white-space:nowrap'>{retry_btn}{delete_btn}</td></tr>"
            )
        def _make_table(src_list, title, note=""):
            trows = "".join(_build_source_row(s) for s in src_list)
            header_note = f"<p class='note' style='margin:4px 0 10px'>{note}</p>" if note else ""
            return (
                f"<div class='section-h'><h3 style='font-size:14px;margin:0'>{title}</h3></div>"
                + header_note
                + "<table style='width:100%;border-collapse:collapse'>"
                "<thead><tr style='font-size:11px;color:var(--ink-3);text-transform:uppercase'>"
                "<th style='text-align:left;padding:6px 8px'>Source</th>"
                "<th style='text-align:left;padding:6px 8px'>Type</th>"
                "<th style='text-align:left;padding:6px 8px'>Status</th>"
                "<th style='text-align:right;padding:6px 8px'>Chunks</th>"
                "<th></th></tr></thead>"
                f"<tbody>{trows}</tbody></table>"
            )

        inner = ""
        if art_sources:
            inner += _make_table(
                art_sources,
                "🤖 Auto-ingested from Research Runs",
                "Automatically indexed by the agent after each completed research task — searchable by future runs.",
            )
        if web_sources:
            if inner:
                inner += "<hr style='border:0;border-top:1px solid var(--line);margin:18px 0'>"
            inner += _make_table(web_sources, "🌐 Web / Document Sources")
        if not art_sources and not web_sources:
            inner = "<p class='note' style='margin:0'>No sources indexed yet. Add a URL above to build the KB.</p>"

        sources_section = (
            f"<div class='card' style='margin-top:16px'>"
            f"<div class='section-h' style='margin-top:0'><h2>Indexed Knowledge</h2></div>"
            f"<div style='max-height:420px;overflow-y:auto'>{inner}</div></div>"
        )
    else:
        sources_section = (
            "<div class='card' style='margin-top:16px'>"
            "<div class='section-h' style='margin-top:0'><h2>Indexed Knowledge</h2></div>"
            "<p class='note' style='margin:0'>No sources indexed yet. "
            "Add a URL above, or run a research task — agent findings auto-populate here.</p>"
            "</div>"
        )

    crm_zone = (
        "<div class='card' style='margin-top:16px'>"
        "<div class='section-h' style='margin-top:0'><h2>CRM &amp; Database Connections</h2></div>"
        "<div class='grid cards3' style='margin-top:8px'>"
        + "".join(
            f"<div class='gc'><div class='gc-ico'>{_icon('database')}</div>"
            f"<div class='gc-t'>{name}</div>"
            f"<div class='gc-d' style='font-size:12px'>{desc}</div>"
            "<div class='gc-tags'><span class='tag pv dark'>coming soon</span></div></div>"
            for name, desc in [
                ("Salesforce", "Sync account + opportunity data into project KB"),
                ("HubSpot", "Pull contact and deal context for research runs"),
                ("PostgreSQL / MySQL", "Query structured data as private research signal"),
            ]
        )
        + "</div></div>"
    )

    # KB Chat panel — full conversational interface backed by hybrid search + LLM synthesis
    has_indexed = any(s.get("status") == "indexed" for s in sources)
    empty_note = (
        "<div style='text-align:center;padding:24px 16px;color:var(--ink-3);font-size:13px'>"
        "Index a source above first — then come back to chat with your knowledge base.</div>"
        if not has_indexed else ""
    )
    proj_name_esc = escape(project.name)
    chat_panel = f"""
<div class='card' style='margin-top:16px' id='kb-chat-card'>
  <div class='section-h' style='margin-top:0;display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
    <h2 style='margin:0'>Ask the Knowledge Base</h2>
    <span class='pill' style='font-size:11px;background:rgba(66,133,244,.14);color:#8ab4f8'>AI · grounded answers</span>
    <button class='btn ghost' id='kb-clear-btn' onclick='kbClearChat()'
            style='margin-left:auto;font-size:12px;padding:4px 10px'>Clear chat</button>
  </div>
  {empty_note}
  <div id='kb-thread'
       style='{"display:none" if not has_indexed else "display:flex;flex-direction:column;gap:10px"};min-height:120px;max-height:480px;overflow-y:auto;padding:8px 0;margin-bottom:12px'></div>
  <div id='kb-input-row' style='{"display:none" if not has_indexed else "display:flex"};gap:8px;align-items:flex-end'>
    <textarea id='kb-q' rows='2' placeholder='Ask anything about {proj_name_esc}…'
              autocomplete='off'
              style='flex:1;resize:vertical;padding:9px 12px;font-size:13.5px;min-height:44px'
              onkeydown='if(event.key==="Enter"&&!event.shiftKey){{event.preventDefault();kbChat();}}'
              {"disabled" if not has_indexed else ""}></textarea>
    <button class='btn' onclick='kbChat()' id='kb-btn'
            style='height:44px;padding:0 16px' {"disabled" if not has_indexed else ""}
            >{_icon("search")} Ask</button>
  </div>
  <p class='note' style='margin:8px 0 0;font-size:11px'>
    Shift+Enter for new line · Enter to send · Answers grounded in indexed sources only
  </p>
</div>
<script>
(function(){{
  var _history = [];
  var _thread = document.getElementById('kb-thread');
  var _btn = document.getElementById('kb-btn');

  function _el(tag, style, text) {{
    var e = document.createElement(tag);
    if(style) e.style.cssText = style;
    if(text !== undefined) e.textContent = text;
    return e;
  }}

  function _addBubble(role, text) {{
    var isUser = role === 'user';
    var wrap = _el('div',
      'display:flex;justify-content:' + (isUser ? 'flex-end' : 'flex-start'));
    var bubble = _el('div',
      'max-width:82%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.65;' +
      'white-space:pre-wrap;word-break:break-word;' +
      (isUser
        ? 'background:rgba(66,133,244,.18);color:var(--ink);border-bottom-right-radius:3px'
        : 'background:var(--panel);border:1px solid var(--line);color:var(--ink);border-bottom-left-radius:3px'),
      text);
    wrap.appendChild(bubble);
    _thread.appendChild(wrap);
    _thread.scrollTop = _thread.scrollHeight;
    return bubble;
  }}

  function _addTyping() {{
    var wrap = _el('div', 'display:flex;justify-content:flex-start');
    var bubble = _el('div',
      'padding:10px 14px;border-radius:12px;font-size:13px;background:var(--panel);' +
      'border:1px solid var(--line);color:var(--ink-3);border-bottom-left-radius:3px',
      'Thinking…');
    wrap.appendChild(bubble);
    wrap.id = 'kb-typing';
    _thread.appendChild(wrap);
    _thread.scrollTop = _thread.scrollHeight;
    return wrap;
  }}

  function kbChat() {{
    var q = document.getElementById('kb-q').value.trim();
    if(!q) return;
    document.getElementById('kb-q').value = '';
    _btn.disabled = true;
    _btn.textContent = '…';

    _addBubble('user', q);
    var typing = _addTyping();

    _history.push({{role:'user', content:q}});

    fetch('/projects/{pid}/kb/chat', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{message: q, history: _history.slice(0,-1)}})
    }})
    .then(function(r){{ return r.json(); }})
    .then(function(data) {{
      var t = document.getElementById('kb-typing');
      if(t) t.parentNode.removeChild(t);
      _btn.disabled = false;
      _btn.textContent = 'Ask';

      if(data.error) {{
        _addBubble('assistant', '⚠ ' + data.error);
        _history.pop();
        return;
      }}
      var answer = data.answer || '(no answer)';
      _addBubble('assistant', answer);
      _history.push({{role:'assistant', content:answer}});
      if(data.sources_used > 0) {{
        var srcNote = _el('div',
          'font-size:11px;color:var(--ink-3);padding:2px 4px;text-align:right',
          '📚 ' + data.sources_used + ' KB chunk(s) used');
        _thread.appendChild(srcNote);
      }}
    }})
    .catch(function(e) {{
      var t = document.getElementById('kb-typing');
      if(t) t.parentNode.removeChild(t);
      _btn.disabled = false;
      _btn.textContent = 'Ask';
      _addBubble('assistant', '⚠ Request failed: ' + e.message);
      _history.pop();
    }});
  }}

  function kbClearChat() {{
    _history = [];
    while(_thread.firstChild) _thread.removeChild(_thread.firstChild);
  }}

  window.kbChat = kbChat;
  window.kbClearChat = kbClearChat;
}})();
</script>
"""

    content = flash + add_form + sources_section + chat_panel + crm_zone
    return shell(
        active="projects", title=f"{project.name} · Knowledge Base", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "kb", project.name),
    )


def project_memory_page(*, project, records: list, backend: str,
                        ok: str = "", err: str = "",
                        semantic_facts: list = None) -> str:
    """Memory tab — episodic run records scoped to this project."""
    semantic_facts = semantic_facts or []
    pid = escape(project.id)
    banner = ""
    if ok:
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad' style='margin-bottom:16px'>{escape(err)}</div>"

    def _row(r) -> str:
        ts = str(r.created_at or "")[:16]
        n_findings = len(getattr(r, "finding_texts", []) or [])
        run_id = escape(str(r.id))
        return (
            f"<tr>"
            f"<td><a href='/accounts/{escape(r.entity)}' style='color:var(--accent-2)'>"
            f"{escape(r.entity)}</a></td>"
            f"<td><span class='pill' style='font-size:11.5px'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td style='text-align:right'>{n_findings}</td>"
            f"<td class='mono'>{ts}</td>"
            f"<td><form method='post' "
            f"action='/projects/{pid}/memory/{run_id}/delete' "
            f"onsubmit=\"return confirm('Remove this run from episodic memory?')\">"
            f"<button type='submit' class='btn' "
            f"style='background:var(--bad);padding:4px 10px;font-size:12px'>Delete</button>"
            f"</form></td>"
            f"</tr>"
        )

    _sem_live = len(semantic_facts) > 0
    _sem_desc = (
        f"Entity facts extracted and accumulated across runs ({len(semantic_facts)} facts)"
        if _sem_live else "Entity facts extracted and accumulated across runs"
    )
    memory_types = (
        "<div class='grid cards3' style='margin-bottom:24px'>"
        + "".join(
            f"<div class='gc'><div class='gc-ico'>{_icon(ico)}</div>"
            f"<div class='gc-t'>{name}</div><div class='gc-d'>{desc}</div>"
            f"<div class='gc-tags'><span class='tag pv {'live' if live else 'dark'}' "
            f"style='{'opacity:.5' if not live else ''}'>"
            f"{'live' if live else 'phase 2'}</span></div></div>"
            for name, ico, desc, live in [
                ("Episodic", "spark", "Run records — every research task this project has run", True),
                ("Semantic", "brain", _sem_desc, _sem_live),
                ("Procedural", "cog", "Learned skills and workflow patterns for this domain", False),
            ]
        )
        + "</div>"
    )

    if records:
        rows_html = "".join(_row(r) for r in records)
        table = (
            "<div class='card' style='padding:6px 8px;overflow:auto'>"
            "<table><thead><tr>"
            "<th>Entity</th><th>Mode</th><th>Backend</th>"
            "<th style='text-align:right'>Findings</th><th>When</th><th></th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
        )
        header_line = (
            f"<p class='note' style='margin-bottom:12px'>{len(records)} run record(s) in this project. "
            "Deleting removes the record from episodic recall; accumulated entity facts are unaffected.</p>"
        )
    else:
        table = "<div class='card'><div class='empty'>No run records for this project yet. " \
                "Complete a research task to populate episodic memory.</div></div>"
        header_line = ""

    # Semantic facts section
    if semantic_facts:
        def _fact_row(f) -> str:
            ts = str(f.created_at or "")[:10]
            return (
                f"<tr>"
                f"<td style='font-weight:500'>{escape(f.entity)}</td>"
                f"<td>{escape(f.content)}</td>"
                f"<td><span class='pill' style='font-size:11px'>{escape(f.source_label)}</span></td>"
                f"<td class='mono' style='color:var(--fg-2);font-size:12px'>{ts}</td>"
                f"</tr>"
            )
        sem_rows = "".join(_fact_row(f) for f in semantic_facts)
        sem_section = (
            "<div class='section-h' style='margin-top:24px'><h2>Semantic Memory</h2></div>"
            f"<p class='note' style='margin-bottom:12px'>{len(semantic_facts)} entity fact(s) "
            "extracted from completed research tasks.</p>"
            "<div class='card' style='padding:6px 8px;overflow:auto'>"
            "<table><thead><tr>"
            "<th>Entity</th><th>Fact</th><th>Source</th><th>Date</th>"
            "</tr></thead>"
            f"<tbody>{sem_rows}</tbody></table></div>"
        )
    else:
        sem_section = ""

    content = (banner + memory_types
               + "<div class='section-h'><h2>Episodic Memory</h2></div>"
               + header_line + table + sem_section)
    return shell(
        active="projects", title=f"{project.name} · Memory", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "memory", project.name),
    )


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


def _entity_href(entity: str, project_by_entity: dict | None) -> str:
    """Focus rows are entity-keyed (PriorityScore has no project_id), but the operator wants to
    land on the entity's PROJECT — the account page is a thin memory view (user feedback
    2026-06-12). The caller passes a {entity: project_id} map resolved from run records;
    entities with no project (legacy runs) keep the account link."""
    pid = (project_by_entity or {}).get(entity)
    if pid:
        return f"/projects/{quote(str(pid), safe='')}"
    return _account_href(entity)


def _focus_row(rank: int, s, project_by_entity: dict | None = None) -> str:
    reasons = "".join(_reason_html(r) for r in s.reasons[:3]) or "<li class='src'>—</li>"
    return (
        f"<tr><td class='mono'>{rank}</td>"
        f"<td><a href='{_entity_href(s.entity, project_by_entity)}' style='color:var(--accent-2)'>"
        f"<b>{escape(s.display_name or s.entity)}</b></a></td>"
        f"<td class='mono'><b>{s.score:.0f}</b></td>"
        f"<td>{_tier_badge(s.tier)}</td>"
        f"<td><ul class='find' style='margin:0'>{reasons}</ul>"
        f"{_breakdown_html(s.breakdown, s.notes)}</td></tr>"
    )


def focus_page(*, scores: list, backend: str, enabled: bool = True, project: str = "sovereign",
               project_by_entity: dict | None = None) -> str:
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
                   "<a href='/projects' style='color:var(--accent-2)'>Run a task</a> and the focus "
                   "list ranks every researched account here, with cited reasons.</div></div>")
        return shell(active="focus", title="Focus", content=content, backend=backend,
                 project=project)
    rows = "".join(_focus_row(i, s, project_by_entity) for i, s in enumerate(scores, start=1))
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


def focus_card(scores: list, project_by_entity: dict | None = None) -> str:
    """Compact 'Top 5 to focus on' card for the dashboard (OQ-2). Empty string when no scores."""
    top = [s for s in scores if s.tier != "cold"][:5] or scores[:5]
    if not top:
        return ""
    rows = "".join(
        f"<tr><td><a href='{_entity_href(s.entity, project_by_entity)}' style='color:var(--accent-2)'>"
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


def _settings_agent_card(key: str, a) -> str:
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
        f"<div><label class='lbl' for='vllm_model'>vLLM tool-caller model <span class='muted' style='font-size:11px'>(12B — planners, extractors)</span></label>"
        f"<input id='vllm_model' name='vllm_model' value='{escape(cfg.backend.vllm.model)}'></div>"
        "</div>"
        f"<div><label class='lbl' for='vllm_api_base'>vLLM API base (tool-caller)</label>"
        f"<input id='vllm_api_base' name='vllm_api_base' "
        f"value='{escape(cfg.backend.vllm.api_base or '')}'></div>"
        + (lambda _r, _ra: (
            f"<div class='row2' style='margin-top:8px'>"
            f"<div><label class='lbl' for='vllm_reasoning_model'>vLLM reasoning model <span class='muted' style='font-size:11px'>(26B — synthesizers, strategists)</span></label>"
            f"<input id='vllm_reasoning_model' name='vllm_reasoning_model' value='{escape(_r)}'></div>"
            f"<div><label class='lbl' for='vllm_reasoning_api_base'>vLLM API base (reasoning)</label>"
            f"<input id='vllm_reasoning_api_base' name='vllm_reasoning_api_base' value='{escape(_ra)}'></div>"
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
        f"{_chk('inject_org_prefs','inject org preferences',cfg.memory.inject_org_prefs)}"
        f"{_chk('episodic_recall','episodic recall (inject past sessions)',getattr(cfg.memory,'episodic_recall',True))}"
        "</div>"
        + "<div class='row2'>"
        + _num("retention_days", "Retention (days)", cfg.memory.retention_days, step="1", mn="1")
        + _num("episodic_recall_top_k", "Episodic recall depth (top-K sessions)", getattr(cfg.memory,"episodic_recall_top_k",3), step="1", mn="1", mx="10")
        + "</div>"
        + "<div class='row2'>"
        + _num("context_window_tokens", "Context window (tokens)", getattr(cfg.memory,"context_window_tokens",2400), step="100", mn="800", mx="16000")
        + "</div>"
        + "<div class='set-actions'>"
        + "<a class='btn' href='/memory/episodes' style='background:var(--bg2);color:var(--txt)'>View &amp; manage episodes</a>"
        + "<span style='flex:1'></span>"
        + "<button class='btn' type='submit'>Save memory</button></div>"
        + "<p class='note'>Episodic recall injects prior research sessions into the planner's context. "
        + "Top-K sets how many prior sessions are recalled (1–10). "
        + "Context window controls the total token budget split across entity-hot/cold, episodic and KB context (800–16 000). "
        + "<a href='/memory/episodes'>View / delete individual run records →</a></p>"
        "</form></div>"
    )

    harness = (
        "<h2 class='sec'>Agent Harness</h2>"
        "<div class='card'><form method='post' action='/settings/harness' class='set-grid'>"
        "<div class='row3'>"
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
        "<h2 class='sec'>Agents — competitor</h2><div class='grid' style='gap:12px'>"
        + "".join(_settings_agent_card(k, cfg.agents[k]) for k in comp)
        + "</div><h2 class='sec'>Agents — client</h2><div class='grid' style='gap:12px'>"
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

    _pw_msg = (f"<div class='banner ok'>{escape(password_ok)}</div>" if password_ok
               else (f"<div class='banner bad'>{escape(password_err)}</div>" if password_err else ""))
    security = (
        "<h2 class='sec'>Security · password</h2>"
        "<div class='card'>"
        + _pw_msg
        + "<form method='post' action='/settings/password' class='set-grid'>"
        "<div class='row2'>"
        "<div><label class='lbl' for='sec_cur'>Current password</label>"
        "<input type='password' id='sec_cur' name='current_password' autocomplete='current-password' required></div>"
        "<div><label class='lbl' for='sec_new'>New password <span style='color:#9aa0a6;font-size:11px'>(min 8 chars)</span></label>"
        "<input type='password' id='sec_new' name='new_password' autocomplete='new-password' required></div>"
        "</div>"
        "<div><label class='lbl' for='sec_cfm'>Confirm new password</label>"
        "<input type='password' id='sec_cfm' name='confirm_password' autocomplete='new-password' required></div>"
        "<div class='set-actions'><button class='btn' type='submit'>Change password</button></div>"
        "<p class='note'>Changes take effect immediately. All active sessions remain valid.</p>"
        "</form></div>"
    )

    # ── External MCP servers — compact status rows + enable toggle ───────────
    mcp_rows = mcp_rows or []
    mcp_items = ""
    for r in mcp_rows:
        cfg_chip = (
            "<span class='pill'><span class='dotmark' style='background:#3ad29f'></span>"
            f"{escape(r['secret_env'])} set</span>" if r["configured"] else
            "<span class='pill'><span class='dotmark' style='background:#ff6b6b'></span>"
            f"{escape(r['secret_env'])} not set</span>"
        )
        scope = ", ".join(r["domains"]) if r["domains"] else "all domains"
        tools = ", ".join(r["tools"][:5]) if r["tools"] else "all tools"
        mcp_items += (
            "<div style='display:flex;align-items:center;gap:10px;padding:8px 0;"
            "border-bottom:1px solid var(--line);flex-wrap:wrap'>"
            f"<b style='font-family:monospace;font-size:13px'>{escape(r['name'])}</b>"
            f"<span class='pv'>{escape(r['transport'])}</span>{cfg_chip}"
            f"<span class='mut' style='font-size:12px;flex:1'>{escape(r['description'])} "
            f"· scope: {escape(scope)} · tools: {escape(tools)}</span>"
            f"<form method='post' action='/settings/mcp/{escape(r['name'])}' style='display:inline'>"
            f"<input type='hidden' name='enabled' value='{'' if r['enabled'] else '1'}'>"
            f"<button class='btn-sm{' ok' if not r['enabled'] else ''}' type='submit'>"
            f"{'Enable' if not r['enabled'] else 'Disable'}</button></form>"
            "</div>"
        )
    mcp_section = ""
    if mcp_items:
        mcp_section = (
            "<h2 class='sec'>MCP servers</h2>"
            "<div class='card'>" + mcp_items +
            "<p class='note' style='margin-top:8px'>External tool servers research agents can "
            "call (Model Context Protocol). Keys live in <span class='mono'>.env</span> — a "
            "server without its key is skipped automatically. Sovereign runs never use these "
            "(cloud egress). Edit domains/tool filters in "
            "<span class='mono'>sentinel.config.yaml</span>.</p></div>"
        )

    content = (
        banner + backends + models + coordinator + governance + search + mcp_section
        + strategy + generation + memory + harness + agents + prompts + security
    )
    return shell(active="settings", title="Settings", content=content, backend=backend)


def error_page(message: str, *, hint: str = "", backend: str = "gemini") -> str:
    hint_html = f"<p class='note'>{escape(hint)}</p>" if hint else ""
    content = (f"<div class='card err'><h2 class='sec' style='color:var(--bad)'>Run failed</h2>"
               f"<p>{escape(message)}</p>{hint_html}"
               "<p class='note'><a href='/projects' style='color:var(--accent-2)'>← Back to New Run</a></p></div>")
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
            f"<td><a href='/accounts/{escape(r.entity)}'>{escape(r.entity)}</a></td>"
            f"<td><span class='pill'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td style='text-align:right'>{n_findings}</td>"
            f"<td>{ts}</td>"
            f"<td>"
            f"<form method='post' action='/memory/episodes/{run_id}/delete' "
            f"onsubmit=\"return confirm('Delete this run record from episodic memory?')\">"
            f"<button type='submit' class='btn' "
            f"style='background:var(--bad);color:#fff;font-size:12px;padding:4px 10px'>Delete</button>"
            f"</form>"
            f"</td>"
            f"</tr>"
        )

    if records:
        rows = "".join(_row(r) for r in records)
        table = (
            "<table style='width:100%;border-collapse:collapse'>"
            "<thead><tr style='text-align:left;color:var(--txt2)'>"
            "<th style='padding:8px 12px'>Entity</th>"
            "<th style='padding:8px 12px'>Mode</th>"
            "<th style='padding:8px 12px'>Backend</th>"
            "<th style='padding:8px 12px;text-align:right'>Findings</th>"
            "<th style='padding:8px 12px'>Created</th>"
            "<th style='padding:8px 12px'>Action</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody>"
            "</table>"
        )
    else:
        table = "<div class='empty'>No run records yet. Run a research task to populate episodic memory.</div>"

    content = (
        banner
        + "<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:8px'>"
        + "<h2 class='sec' style='margin:0'>Episodic Memory — Run Records</h2>"
        + "<a class='btn' href='/settings#memory' style='background:var(--bg2);color:var(--txt)'>← Settings</a>"
        + "</div>"
        + f"<p class='note'>{len(records)} run record(s). Deleting a record removes it from episodic recall "
        + "— the entity's <a href='/accounts'>accumulated memory</a> is unaffected.</p>"
        + "<div class='card' style='padding:0;overflow:auto'>" + table + "</div>"
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

_PROMPT_GROUPS_ORDER = [
    "competitor", "client", "self_profile", "finance", "software",
    "academic", "nutrition", "travel", "compare", "orchestrator",
    "coordinator", "program", "eval", "persona",
]


def _prompt_role_badge(key: str, cfg) -> str:
    ac = cfg.agents.get(key)
    role = ac.role if ac else ""
    if not role:
        return ""
    colour, bg = _ROLE_COLOURS.get(role, ("#9aa0a6", "rgba(150,160,170,.15)"))
    return (
        f"<span style='font-size:11px;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:.07em;padding:2px 8px;border-radius:999px;"
        f"color:{colour};background:{bg};margin-left:10px'>{escape(role)}</span>"
    )


def _prompt_crud_card(key: str, p, cfg) -> str:
    is_custom = p.default_template is None
    vars_html = (
        "<p class='varsHint'>vars: "
        + escape(", ".join("{" + v + "}" for v in p.variables))
        + "</p>"
    ) if p.variables else "<p class='varsHint'>no required vars</p>"

    reset_btn = (
        f"<form method='post' action='/settings/prompts/{escape(key)}/reset' style='display:inline'>"
        "<button class='btn ghost' type='submit' style='font-size:12px;padding:7px 12px'>Reset to default</button>"
        "</form>"
    ) if not is_custom else (
        f"<form method='post' action='/settings/prompts/{escape(key)}/delete' style='display:inline' "
        f"onsubmit=\"return confirm('Delete custom prompt {escape(key)}? This cannot be undone.')\">"
        "<button class='btn ghost' type='submit' style='font-size:12px;padding:7px 12px;"
        "color:#f28b82;border-color:#5a1f1f'>Delete</button>"
        "</form>"
    )

    custom_badge = (
        "<span style='font-size:10px;color:#fdd663;background:rgba(251,188,4,.15);"
        "border-radius:999px;padding:1px 7px;margin-left:8px;font-weight:700'>custom</span>"
        if is_custom else ""
    )

    return (
        f"<details class='card prompt-card' data-key='{escape(key)}' "
        "style='margin-bottom:10px;padding:0'>"
        f"<summary style='padding:14px 18px;cursor:pointer;display:flex;align-items:center;"
        "gap:4px;border-radius:14px;list-style:none'>"
        f"<span class='agent-key'>{escape(key)}</span>"
        f"{_prompt_role_badge(key, cfg)}{custom_badge}"
        "</summary>"
        "<div style='padding:0 18px 18px'>"
        f"<form method='post' action='/settings/prompts/{escape(key)}' class='set-grid'>"
        f"<textarea name='template' rows='8' style='font-size:12px'>{escape(p.template)}</textarea>"
        f"{vars_html}"
        "<div class='set-actions'>"
        "<button class='btn' type='submit' style='font-size:12px;padding:7px 14px'>Save</button>"
        f"{reset_btn}"
        "</div>"
        "</form></div></details>"
    )


def prompts_page(cfg, *, backend: str, ok: str = "", err: str = "") -> str:
    """Full CRUD page for all agent prompt templates, grouped by skill domain."""
    banner = ""
    if ok:
        banner = f"<div class='card banner ok' style='margin-bottom:16px'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card banner bad' style='margin-bottom:16px'>{escape(err)}</div>"

    # Group prompt keys by prefix
    groups: dict[str, list[str]] = {}
    for k in sorted(cfg.prompts):
        prefix = k.split(".")[0]
        groups.setdefault(prefix, []).append(k)

    ordered = [(g, groups[g]) for g in _PROMPT_GROUPS_ORDER if g in groups]
    ordered += [(g, groups[g]) for g in sorted(groups) if g not in _PROMPT_GROUPS_ORDER]

    # Build group sections
    sections = []
    for group, keys in ordered:
        cards = "".join(_prompt_crud_card(k, cfg.prompts[k], cfg) for k in keys)
        sections.append(
            f"<h2 class='sec' style='margin-top:28px' id='group-{escape(group)}'>"
            f"{escape(group.replace('_',' ').title())} "
            f"<span style='color:var(--muted);font-weight:400;font-size:11px'>{len(keys)} prompts</span>"
            f"</h2>{cards}"
        )

    # Create new prompt form
    create_form = (
        "<div class='card' style='margin-bottom:24px'>"
        "<h2 class='sec' style='margin-top:0'>New custom prompt</h2>"
        "<form method='post' action='/settings/prompts/create' class='set-grid'>"
        "<div class='row2'>"
        "<div><label class='lbl' for='new-key'>Key <span class='note'>(e.g. finance.custom_scorer)</span></label>"
        "<input id='new-key' name='key' placeholder='skill.step_name' required></div>"
        "<div><label class='lbl' for='new-vars'>Variables <span class='note'>(comma-separated, no braces)</span></label>"
        "<input id='new-vars' name='variables' placeholder='target, research_plan'></div>"
        "</div>"
        "<div><label class='lbl' for='new-tmpl'>Template</label>"
        "<textarea id='new-tmpl' name='template' rows='5' "
        "placeholder='You are a researcher. The topic is {target}...' required></textarea></div>"
        "<div class='set-actions'>"
        "<button class='btn' type='submit'>Create prompt</button>"
        "<span class='note' style='align-self:center;margin-left:8px'>Custom prompts can be deleted; shipped prompts can only be reset.</span>"
        "</div></form></div>"
    )

    # Search + jump bar
    group_links = " ".join(
        f"<a href='#group-{escape(g)}' style='color:var(--accent-2);font-size:12px;"
        f"padding:4px 10px;border:1px solid var(--line);border-radius:999px;"
        f"background:var(--panel-2)'>{escape(g)}</a>"
        for g, _ in ordered
    )
    controls = (
        "<div style='display:flex;align-items:center;gap:12px;margin-bottom:20px;flex-wrap:wrap'>"
        "<input id='prompt-search' placeholder='Filter prompts…' oninput='filterPrompts()' "
        "style='width:260px;padding:9px 13px;font-size:13px'>"
        f"<div style='display:flex;gap:7px;flex-wrap:wrap'>{group_links}</div>"
        "</div>"
        "<script>"
        "function filterPrompts(){"
        "  const q=document.getElementById('prompt-search').value.toLowerCase();"
        "  document.querySelectorAll('.prompt-card').forEach(c=>{"
        "    c.style.display=c.dataset.key.toLowerCase().includes(q)?'':'none'"
        "  });"
        "  document.querySelectorAll('h2.sec[id^=group-]').forEach(h=>{"
        "    const cards=[...document.querySelectorAll('.prompt-card[data-key]')]"
        "      .filter(c=>c.previousElementSibling===h||"
        "        [...h.parentElement.children].indexOf(c)>"
        "        [...h.parentElement.children].indexOf(h));"
        "    h.style.display=cards.some(c=>c.style.display!=='none')?'':'none';"
        "  });"
        "}"
        "</script>"
    )

    total = len(cfg.prompts)
    custom_count = sum(1 for p in cfg.prompts.values() if p.default_template is None)

    summary_bar = (
        "<div class='card' style='margin-bottom:20px;padding:14px 18px;"
        "display:flex;gap:24px;align-items:center'>"
        f"<span class='pill'><b>{total}</b> total prompts</span>"
        f"<span class='pill'><b>{len(ordered)}</b> skill groups</span>"
        f"<span class='pill'><b>{custom_count}</b> custom</span>"
        "<span style='flex:1'></span>"
        "<a href='/settings' class='btn ghost' style='font-size:12px;padding:7px 12px'>← Settings</a>"
        "</div>"
    )

    content = banner + summary_bar + controls + create_form + "".join(sections)
    return shell(active="prompts", title="Prompts", content=content, backend=backend)


# --------------------------------------------------------------------------- #
# Project Report page — consulting-grade output compiled from task results
# --------------------------------------------------------------------------- #

def _rpt_section(num: str, title: str, body: str) -> str:
    return (
        f"<div class='rpt-sec'>"
        f"<div class='rpt-sec-hd'>"
        f"<span class='rpt-num'>{escape(num)}</span>"
        f"<h2>{escape(title)}</h2>"
        f"</div>{body}</div>"
    )


def _rpt_callout(label: str, body: str, variant: str = "") -> str:
    cls = f"rpt-callout {variant}".strip()
    return (
        f"<div class='{cls}'>"
        f"<span class='rpt-cl-label'>{escape(label)}</span>"
        f"{body}"
        f"</div>"
    )


def _rpt_metric(val: str, label: str) -> str:
    return (
        f"<div class='rpt-metric'>"
        f"<div class='rm-val'>{escape(val)}</div>"
        f"<div class='rm-lbl'>{escape(label)}</div>"
        f"</div>"
    )


def _rpt_table(headers: list[str], rows: list[list[str]]) -> str:
    ths = "".join(f"<th>{escape(h)}</th>" for h in headers)
    trs = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<div class='card' style='padding:0;overflow:auto;margin:16px 0'><table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>"


def _src_link(src: dict) -> str:
    """Render a Finding.source dict as a compact linked badge for report tables.

    Only emits an <a href> for http/https URLs — blocks javascript: and data: scheme injection.
    """
    if not src or not isinstance(src, dict):
        return "<span style='color:var(--muted);font-size:11px'>—</span>"
    label = escape(str(src.get("label") or "source"))
    url   = str(src.get("url") or "").strip()
    if url and (url.startswith("https://") or url.startswith("http://")):
        return (f"<a href='{escape(url)}' target='_blank' rel='noopener' "
                f"style='font-size:11px;color:var(--accent-2)'>{label}</a>")
    return f"<span style='font-size:11px;color:var(--muted)'>{label}</span>"


def project_report_page(*, project, tasks: list, backend: str) -> str:
    """Research Intelligence Report — compiled dynamically from actual task artifacts."""
    pname = escape(project.name)
    subnav = _project_subnav(project.id, "report", project.name)

    done_tasks = [t for t in tasks if t.get("status") == "done" and t.get("result")]

    cover = (
        "<div class='rpt-cover'>"
        "<div class='rpt-firm'>Sentinel Intelligence Platform · Sovereign Research Division</div>"
        f"<h1>{pname}</h1>"
        "<p class='rpt-sub'>Research Intelligence Report — on-premise sovereign AI, zero cloud dependency</p>"
        "<div class='rpt-meta'>"
        "<span class='rpt-tag'>Confidential</span>"
        "<span class='rpt-tag green'>Sovereign On-Premise</span>"
        f"<span class='rpt-tag' style='background:var(--panel-2)'>"
        f"{len(done_tasks)} Research Task{'s' if len(done_tasks) != 1 else ''} Complete</span>"
        "</div>"
        "</div>"
    )

    if not done_tasks:
        return shell(
            active="projects", title=f"{project.name} · Report",
            content=(cover
                     + "<div style='margin:32px 0'><div class='card'>"
                     "<div class='empty' style='padding:48px;text-align:center;font-size:15px'>"
                     "No completed research tasks yet — run a task to populate this report."
                     "</div></div></div>"),
            backend=backend, subnav=subnav, project=project.name,
        )

    _SUB = "font-size:13px;margin:20px 0 8px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)"
    sections: list[str] = []

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

        obj_trunc_display = obj_raw[:80] + ("…" if len(obj_raw) > 80 else "")
        body = (f"<div class='note' style='margin-bottom:16px'>"
                f"<b>Objective:</b> {escape(obj_trunc_display)}</div>")

        # ── Domain-aware metric row ───────────────────────────────────────────
        if govt_art:
            depts   = [d for d in (govt_art.get("department_mappings") or []) if isinstance(d, dict)]
            client  = escape(str(govt_art.get("client") or "Client"))
            vendor  = escape(str(govt_art.get("vendor") or "Vendor"))
            pilot   = "Defined" if govt_art.get("pilot_plan") else "—"
            body += (
                "<div class='rpt-metrics' style='grid-template-columns:repeat(3,1fr)'>"
                + _rpt_metric(str(len(depts)) if depts else "—", "Departments Mapped")
                + _rpt_metric(pilot,                             "Pilot Plan")
                + _rpt_metric(str(len(citations)),               "Sources Cited")
                + "</div>"
                + f"<div style='margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap'>"
                + f"<span class='pill'>client: <b>{client}</b></span>"
                + f"<span class='pill'>vendor: <b>{vendor}</b></span>"
                + "</div>"
            )
        elif prod_art:
            prods  = [p for p in (prod_art.get("products_found") or []) if isinstance(p, dict)]
            winner = escape(str(prod_art.get("winner") or "—"))
            body += (
                "<div class='rpt-metrics' style='grid-template-columns:repeat(3,1fr)'>"
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
                "<div class='rpt-metrics' style='grid-template-columns:repeat(3,1fr)'>"
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
                    "<div class='card' style='border-left:3px solid #5bd07f;padding:14px 18px'>"
                    f"<div style='font-size:18px;font-weight:700;color:#5bd07f'>{escape(winner)}</div>"
                    + (f"<div style='margin-top:6px;font-size:13px;color:var(--muted)'>"
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
                body += f"<div class='card'><ol style='margin:0;padding-left:20px'>{rank_html}</ol></div>"

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
                        "<div class='card'><div class='empty' style='padding:16px'>"
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
                    clr = "#5bd07f" if w > l else "#ff6b6b" if l > w else "#fbbf24"
                    body += (
                        f"<div style='font-size:12px;color:var(--muted);margin-top:4px;margin-bottom:8px'>"
                        f"Score vs {rival}: "
                        f"<span style='color:{clr};font-weight:700'>{w}&nbsp;Win / {l}&nbsp;Lose / {p}&nbsp;Parity</span>"
                        "</div>"
                    )
                else:
                    body += "<div class='card'><div class='empty'>No comparison dimensions produced.</div></div>"

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
            pub_style  = "background:rgba(66,133,244,.14);color:var(--accent-2)"
            priv_style = "background:rgba(251,191,36,.14);color:#fbbf24"
            cites = "".join(
                "<li>"
                + (f"<span class='badge' style='font-size:9px;margin-right:4px;"
                   + (pub_style if str(c.get("boundary") or "").lower() == "public" else priv_style)
                   + f"'>{escape(str(c.get('boundary') or '?').upper())}</span>"
                   + f"<b>{escape(str(c.get('label') or '—'))}</b>"
                   + (f" · <a href='{escape(str(c['url']))}' target='_blank' rel='noopener' "
                      f"style='color:var(--accent-2)'>{escape(str(c['url']))}</a>"
                      if c.get("url") else "")
                   if isinstance(c, dict) else escape(str(c)))
                + "</li>"
                for c in citations[:20]
            )
            body += (
                f"<h3 style='{_SUB}'>Sources ({len(citations)})</h3>"
                f"<div class='card'><ul class='find'>{cites}</ul></div>"
            )

        obj_trunc = obj_raw[:70] + ("…" if len(obj_raw) > 70 else "")
        sections.append(_rpt_section(str(i).zfill(2), f"Task {i}: {obj_trunc}", body))

    return shell(
        active="projects",
        title=f"{project.name} · Report",
        content=cover + "".join(sections),
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


# --------------------------------------------------------------------------- #
# Auth pages — login + first-boot setup (no shell wrapper, standalone HTML)
# --------------------------------------------------------------------------- #
_AUTH_CSS = """
<style>
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:#0b0e14;color:#e8eaed;
  font:14.5px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.box{background:#151a23;border:1px solid #2a2f3a;border-radius:18px;padding:40px 36px;
  width:100%;max-width:400px;box-shadow:0 8px 48px rgba(0,0,0,.55)}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:28px}
.logo-mark{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;background:linear-gradient(135deg,#4285f4,#a142f4);
  color:#fff;font-weight:800;font-size:18px;flex:0 0 auto}
.logo-text{font-size:20px;font-weight:700;letter-spacing:.2px}
h2{font-size:16px;font-weight:600;margin:0 0 6px}
.sub{color:#9aa0a6;font-size:13px;margin:0 0 24px}
label{font-size:11.5px;text-transform:uppercase;letter-spacing:.1em;color:#9aa0a6;
  display:block;margin-bottom:6px}
input[type=password]{width:100%;background:#11151d;border:1px solid #2a2f3a;color:#e8eaed;
  padding:11px 13px;border-radius:10px;font-size:14.5px;margin-bottom:16px}
input[type=password]:focus{outline:none;border-color:#4285f4}
.btn-full{width:100%;background:#4285f4;color:#fff;border:0;padding:13px;border-radius:10px;
  font-size:15px;font-weight:600;cursor:pointer;margin-top:4px}
.btn-full:hover{filter:brightness(1.1)}
.err{background:#1c1011;border:1px solid #5a1f1f;color:#ff6b6b;border-radius:8px;
  padding:10px 14px;font-size:13px;margin-bottom:16px}
.foot{color:#9aa0a6;font-size:12px;text-align:center;margin-top:18px}
</style>
"""


def login_page(*, next_url: str = "", err: str = "") -> str:
    err_html = f"<div class='err'>{escape(err)}</div>" if err else ""
    next_field = f"<input type='hidden' name='next' value='{escape(next_url)}'>" if next_url else ""
    return f"""<!doctype html><html lang='en'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Sign in · Sentinel</title>{_AUTH_CSS}</head>
<body><div class='wrap'><div class='box'>
<div class='logo'><div class='logo-mark'>S</div><div class='logo-text'>Sentinel</div></div>
<h2>Sign in</h2>
<p class='sub'>Sovereign Intelligence Agent</p>
{err_html}
<form method='post' action='/login'>
{next_field}
<label for='pw'>Password</label>
<input type='password' id='pw' name='password' autofocus required placeholder='Enter password'>
<button class='btn-full' type='submit'>Sign in</button>
</form>
</div></div></body></html>"""


def setup_page(*, err: str = "") -> str:
    err_html = f"<div class='err'>{escape(err)}</div>" if err else ""
    return f"""<!doctype html><html lang='en'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Set up password · Sentinel</title>{_AUTH_CSS}</head>
<body><div class='wrap'><div class='box'>
<div class='logo'><div class='logo-mark'>S</div><div class='logo-text'>Sentinel</div></div>
<h2>Set up your password</h2>
<p class='sub'>First boot — create a password to protect this instance.</p>
{err_html}
<form method='post' action='/setup'>
<label for='pw'>Password <span style='color:#9aa0a6;font-size:11px'>(min 8 characters)</span></label>
<input type='password' id='pw' name='password' autofocus required placeholder='Choose a password'>
<label for='pw2'>Confirm password</label>
<input type='password' id='pw2' name='confirm' required placeholder='Repeat password'>
<button class='btn-full' type='submit'>Create password &amp; sign in</button>
</form>
</div></div></body></html>"""
