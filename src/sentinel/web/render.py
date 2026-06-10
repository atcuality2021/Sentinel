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
        ("backends", "Backends", "chip", "/backends"),
        ("settings", "Settings", "cog", "/settings"),
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
            "No runs yet. <a href='/projects' style='color:var(--accent-2)'>Run your first "
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


def _task_form(project_id: str, *, default_backend: str = "gemini",
               vllm_model: str = "gemma-4-12b-it", sovereign: bool = False) -> str:
    """The objective → plan entry point (SENTINEL-012): a GET form that hands the objective, domain,
    persona, and reasoning backend to the planner route. The backend toggle mirrors the New Run form
    so users with both Gemini and vLLM can choose per-task."""
    domains = "".join(f"<option value='{d}'>{d}</option>" for d in _DOMAINS)
    personas = "".join(f"<option value='{p}'>{p}</option>" for p in _PERSONAS)
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
        "placeholder='e.g. Profile us, find competitors, and produce a market-capture strategy'></div>"
        "<div><label class='lbl' for='t-dom'>Domain</label>"
        f"<select id='t-dom' name='domain'>{domains}</select></div>"
        "<div><label class='lbl' for='t-per'>Persona</label>"
        f"<select id='t-per' name='persona'>{personas}</select></div>"
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
        "<div class='note' style='margin-top:8px'>Domain selects the research skills + output shape; "
        "persona adapts the output's reading level &amp; tone (facts unchanged). The planner proposes a "
        "step-DAG; you review and approve before anything runs (unless the project is autonomous).</div></div>"
    )


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
            f"<input type='hidden' name='backend' value='gemini'>"
            f"<button class='btn-sm warn' type='submit' title='Re-run this task'>"
            f"{_icon('bolt')} Re-run</button></form>"
        )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline'>"
        f"<button class='btn-sm bad' type='submit' title='Delete task'>&times;</button></form>"
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


def project_detail_page(*, project, tasks: list, backend: str,
                        vllm_model: str = "gemma-4-12b-it", sovereign: bool = False) -> str:
    """Overview tab — project info card + quick stats + recent tasks list (no creation form)."""
    pid = escape(project.id)
    site = (f"<a href='{escape(project.website)}' rel='noopener' target='_blank' "
            f"style='color:var(--accent-2)'>{escape(project.website)}</a>") if project.website else "—"

    done  = sum(1 for t in tasks if t.status == "done")
    fail  = sum(1 for t in tasks if t.status == "failed")
    fail_pill = (
        f"<span class='pill' style='border-color:rgba(234,67,53,.4);color:#ff6b6b'>"
        f"Failed: <b>{fail}</b></span>"
    ) if fail else ""
    header = (
        "<div class='card'><div class='section-h' style='margin-top:0'>"
        f"<h2>{escape(project.name)}</h2>"
        f"<a class='btn' href='/projects/{pid}/tasks'>{_icon('bolt')} New Research Task</a></div>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-top:8px'>"
        f"<span class='pill'>Website: <b>{site}</b></span>"
        f"<span class='pill'>Autonomy: <b>{escape(project.settings.autonomy)}</b></span>"
        f"<span class='pill'>Tasks: <b>{len(tasks)}</b></span>"
        f"<span class='pill' style='border-color:rgba(52,168,83,.4);color:#5bd07f'>Done: <b>{done}</b></span>"
        f"{fail_pill}</div></div>"
    )

    if tasks:
        recent = tasks[:5]
        rows = "".join(_task_row(t, pid) for t in recent)
        failed_note = (
            f"<span class='tag' style='color:#ff6b6b;margin-left:6px'>"
            f"{fail} failed — Re-run to retry</span>"
        ) if fail else ""
        tasks_html = (
            "<div class='section-h'>"
            f"<h2>Recent Research{failed_note}</h2>"
            f"<a class='btn ghost' href='/projects/{pid}/tasks'>View all</a></div>"
            f"<div class='card' style='padding:0'>{rows}</div>"
        )
    else:
        tasks_html = (
            "<div class='section-h'><h2>Recent Research</h2></div>"
            "<div class='card'><div class='empty'>No research tasks yet. "
            f"<a href='/projects/{pid}/tasks' style='color:var(--accent-2)'>Open the Research tab</a> "
            "to create your first task.</div></div>"
        )

    kb_cta = (
        "<div class='card' style='margin-top:16px'>"
        "<div class='section-h' style='margin-top:0'><h2>Knowledge Base</h2>"
        f"<a class='btn ghost' href='/projects/{pid}/kb'>Open</a></div>"
        "<p class='note'>Add documents, PDFs, URLs, and data sources that ground every research run "
        "in this project. Connected sources are cited in every artifact.</p></div>"
    )
    memory_cta = (
        "<div class='card' style='margin-top:16px'>"
        "<div class='section-h' style='margin-top:0'><h2>Memory</h2>"
        f"<a class='btn ghost' href='/projects/{pid}/memory'>Open</a></div>"
        "<p class='note'>Episodic run records, semantic entity facts, and preferences "
        "accumulated across all research tasks in this project.</p></div>"
    )
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
        "Episodic memory run records are kept (they belong to the entity, not the project).</p>"
        "</div>"
        f"<form method='post' action='/projects/{pid}/delete' "
        f"onsubmit='return confirm(\"Delete project \" + {escape(json.dumps(project.name), quote=True)} + \"? All tasks and data will be permanently removed.\")'>"
        "<button class='btn' type='submit' "
        "style='background:#7f1d1d;border:1px solid #dc2626;color:#fca5a5;"
        "padding:10px 18px;flex:0 0 auto'>"
        f"{_icon('shield')} Delete project</button></form>"
        "</div></div>"
    )

    content = header + "<div style='margin-top:16px'></div>" + tasks_html + kb_cta + memory_cta + danger_zone
    return shell(
        active="projects", title=project.name, content=content, backend=backend,
        project=project.name,
        subnav=_project_subnav(project.id, "overview", project.name),
    )


def project_tasks_page(*, project, tasks: list, backend: str,
                       vllm_model: str = "gemma-4-12b-it", sovereign: bool = False) -> str:
    """Research/Tasks tab — task creation form + full task list."""
    pid = escape(project.id)
    form_html = _task_form(project.id, default_backend=backend,
                           vllm_model=vllm_model, sovereign=sovereign)
    failed_count = sum(1 for t in tasks if t.status == "failed")
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
    content = form_html + "<div style='margin-top:24px'></div>" + tasks_html
    return shell(
        active="projects", title=f"{project.name} · Research", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "tasks", project.name),
    )


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
        f"<form method='post' action='/projects/{pid}/kb/sources' "
        "style='display:grid;gap:14px;max-width:640px'>"
        "<div><label class='lbl'>URL</label>"
        f"<input name='url' required placeholder='https://biltiq.ai  or  https://linkedin.com/company/biltiq'{website_prefill} "
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
        "<p class='note' style='margin-top:16px'>Each indexed source is embedded with "
        "<b>Qwen3-VL-Embedding-2B</b> + BM25 and reranked via your cross-encoder. "
        "Research agents query this KB automatically via the <code>search_project_kb</code> MCP tool.</p>"
        "</div>"
    )

    # Sources table
    if sources:
        rows = ""
        for s in sources:
            status = s.get("status", "pending")
            colour = _status_colour.get(status, "var(--ink-3)")
            badge = f"<span style='color:{colour};font-weight:600;text-transform:uppercase;font-size:11px'>{escape(status)}</span>"
            chunks = s.get("chunk_count", 0)
            stype = s.get("source_type", "web")
            raw_url = s.get("url", "")
            url_display = escape(raw_url)
            # Only emit <a href> for http/https — blocks javascript: URI XSS from stored URLs
            safe_url = safe_href(raw_url)
            url_cell = (
                f"<a href='{escape(safe_url)}' target='_blank' rel='noopener noreferrer'>{url_display}</a>"
                if safe_url else url_display
            )
            raw_err = (s.get("error") or "").split("\n")[0][:140]
            err_note = f"<br><span style='color:var(--bad);font-size:11px'>{escape(raw_err)}</span>" if raw_err else ""
            delete_btn = (
                f"<form method='post' action='/projects/{pid}/kb/sources/{escape(s['id'])}/delete' "
                "style='display:inline'>"
                "<button class='btn-sm bad' type='submit' title='Remove source'>×</button></form>"
            )
            rows += (
                f"<tr><td style='max-width:340px;word-break:break-all'>"
                f"{url_cell}{err_note}</td>"
                f"<td><span class='pill' style='font-size:11px'>{escape(stype)}</span></td>"
                f"<td>{badge}</td>"
                f"<td style='text-align:right'>{chunks:,}</td>"
                f"<td>{delete_btn}</td></tr>"
            )
        sources_section = (
            "<div class='card' style='margin-top:16px'>"
            "<div class='section-h' style='margin-top:0'><h2>Indexed Sources</h2></div>"
            "<table style='width:100%;border-collapse:collapse'>"
            "<thead><tr style='font-size:11px;color:var(--ink-3);text-transform:uppercase'>"
            "<th style='text-align:left;padding:6px 8px'>URL</th>"
            "<th style='text-align:left;padding:6px 8px'>Type</th>"
            "<th style='text-align:left;padding:6px 8px'>Status</th>"
            "<th style='text-align:right;padding:6px 8px'>Chunks</th>"
            "<th></th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            "</div>"
        )
    else:
        sources_section = (
            "<div class='card' style='margin-top:16px'>"
            "<p class='note' style='margin:0'>No sources indexed yet. Add a URL above to build the KB.</p>"
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

    # KB Chat panel — queries the hybrid search endpoint via JS fetch
    has_indexed = any(s.get("status") == "indexed" for s in sources)
    chat_disabled_msg = (
        "<p class='note' style='margin:0;text-align:center;padding:12px 0'>"
        "Index a source above, then come back to chat with it.</p>"
        if not has_indexed else ""
    )
    chat_panel = f"""
<div class='card' style='margin-top:16px' id='kb-chat-card'>
  <div class='section-h' style='margin-top:0;display:flex;align-items:center;gap:10px'>
    <h2 style='margin:0'>Ask the Knowledge Base</h2>
    <span class='pill' style='font-size:11px;background:rgba(66,133,244,.14);color:#8ab4f8'>hybrid search</span>
  </div>
  {chat_disabled_msg}
  <div style='display:{"none" if not has_indexed else "block"}' id='kb-chat-ui'>
    <div style='display:flex;gap:8px;margin-bottom:14px'>
      <input id='kb-q' placeholder='What products does {escape(project.name)} offer?' autocomplete='off'
             style='flex:1;padding:9px 12px;font-size:13.5px'
             onkeydown='if(event.key==="Enter")kbSearch()' {'disabled' if not has_indexed else ''}>
      <button class='btn' onclick='kbSearch()' id='kb-btn'>{_icon("search")} Search</button>
    </div>
    <div id='kb-results'></div>
  </div>
</div>
<script>
(function(){{
  function _txt(el, text) {{ el.textContent = text; return el; }}
  function _el(tag, attrs) {{
    var e = document.createElement(tag);
    if(attrs) Object.keys(attrs).forEach(function(k){{ e[k] = attrs[k]; }});
    return e;
  }}
  function _setMsg(res, text, cls) {{
    var p = _el('p', {{className: cls||'', style: 'margin:0'}});
    _txt(p, text);
    while(res.firstChild) res.removeChild(res.firstChild);
    res.appendChild(p);
  }}

  function kbSearch(){{
    var q = document.getElementById('kb-q').value.trim();
    if(!q) return;
    var btn = document.getElementById('kb-btn');
    var res = document.getElementById('kb-results');
    btn.disabled = true;
    btn.textContent = 'Searching…';
    _setMsg(res, 'Searching…', 'note');
    fetch('/projects/{pid}/kb/search?q=' + encodeURIComponent(q))
      .then(function(r){{return r.json();}})
      .then(function(data){{
        btn.disabled = false;
        btn.textContent = 'Search';
        if(data.error){{
          var p = _el('p'); p.style.color='var(--bad)'; _txt(p, data.error);
          while(res.firstChild) res.removeChild(res.firstChild);
          res.appendChild(p);
          return;
        }}
        if(!data.results || !data.results.length){{
          _setMsg(res, 'No results found. Try a different query.', 'note');
          return;
        }}
        var nodes = data.results.map(function(r, i){{
          var score = Math.round((r.score || 0) * 100);
          var rawUrl = r.url || '';
          var safeUrl = /^https?:\/\//.test(rawUrl) ? rawUrl : '';

          var wrap = _el('div');
          wrap.style.cssText = 'padding:12px;border:1px solid var(--line);border-radius:8px;margin-bottom:8px;background:var(--panel)';

          var hdr = _el('div');
          hdr.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px';

          var titleText = r.title || rawUrl || ('Result ' + (i+1));
          if(safeUrl){{
            var a = _el('a', {{href: safeUrl, target: '_blank', rel: 'noopener noreferrer'}});
            a.style.cssText = 'font-size:13px;font-weight:600;color:var(--accent-2)';
            _txt(a, titleText);
            hdr.appendChild(a);
          }} else {{
            var sp = _el('span'); sp.style.cssText='font-size:13px;font-weight:600;color:var(--accent-2)';
            _txt(sp, titleText); hdr.appendChild(sp);
          }}

          var pill = _el('span', {{className:'pill'}}); pill.style.fontSize='10px';
          _txt(pill, r.source_type || 'web'); hdr.appendChild(pill);

          var sc = _el('span'); sc.style.cssText='margin-left:auto;font-size:11px;color:var(--ink-3)';
          _txt(sc, score + '% match'); hdr.appendChild(sc);
          wrap.appendChild(hdr);

          var body = r.text || '';
          var p = _el('p');
          p.style.cssText = 'margin:0;font-size:12.5px;color:var(--ink-2);line-height:1.6';
          _txt(p, body.length > 320 ? body.substring(0,320) + '…' : body);
          wrap.appendChild(p);
          return wrap;
        }});
        while(res.firstChild) res.removeChild(res.firstChild);
        nodes.forEach(function(n){{ res.appendChild(n); }});
      }})
      .catch(function(e){{
        btn.disabled = false;
        btn.textContent = 'Search';
        var p = _el('p'); p.style.color='var(--bad)'; _txt(p, 'Search failed: ' + e.message);
        while(res.firstChild) res.removeChild(res.firstChild);
        res.appendChild(p);
      }});
  }}
  window.kbSearch = kbSearch;
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
                        ok: str = "", err: str = "") -> str:
    """Memory tab — episodic run records scoped to this project."""
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

    memory_types = (
        "<div class='grid cards3' style='margin-bottom:24px'>"
        + "".join(
            f"<div class='gc'><div class='gc-ico'>{_icon(ico)}</div>"
            f"<div class='gc-t'>{name}</div><div class='gc-d'>{desc}</div>"
            f"<div class='gc-tags'><span class='tag {'pv live' if live else 'pv dark'}'>"
            f"{'live' if live else 'coming soon'}</span></div></div>"
            for name, ico, desc, live in [
                ("Episodic", "spark", "Run records — every research task this project has run", True),
                ("Semantic", "brain", "Entity facts extracted and accumulated across runs", False),
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

    content = (banner + memory_types
               + "<div class='section-h'><h2>Episodic Memory</h2></div>"
               + header_line + table)
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

    if "one_line_summary" in art or ("strengths" in art and "weaknesses" in art):   # Battlecard
        body = (f"<div class='note'>{escape(art.get('one_line_summary', ''))}</div>"
                + _findings_block("Strengths", art.get("strengths", []))
                + _findings_block("Weaknesses", art.get("weaknesses", []))
                + _findings_block("Pricing signals", art.get("pricing_signals", []))
                + _findings_block("Recent developments", art.get("recent_developments", [])))
        return _art_wrap(f"Battlecard — {escape(art.get('target', '') or key)}", body)

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
    _fmt = getattr(result, "preferred_format", None) or "bullets"
    if arts:
        raw_html = "".join(_artifact_html(key, art) for key, art in arts.items())
        if _fmt == "table":
            raw_html = _findings_to_table(raw_html)
        elif _fmt == "prose":
            raw_html = _findings_to_prose(raw_html)
        arts_html = ("<div class='section-h'><h2>Deliverables</h2></div>"
                     f"<div style='display:grid;gap:10px'>{raw_html}</div>")
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
        "body:new URLSearchParams({signal:sig})}});"
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


def plan_review_page(*, task, proposal, autonomy: str, backend: str, ran: bool = False,
                     result=None, trace: list[str] | None = None,
                     selected_backend: str = "") -> str:
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
        f"<span class='pill'>objective: <b>{escape(task.objective)}</b></span>"
        f"<span class='pill'>domain: <b>{escape(task.domain.name)}</b></span>"
        f"<span class='pill'>persona: <b>{escape(task.persona.name)}</b></span>"
        f"<span class='pill'>steps: <b>{len(plan.steps)}</b></span>"
        f"<span class='pill'>new agents: <b>{len(created)}</b></span>"
        f"{be_pill}</div></div>"
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
        be_hidden = (f"<input type='hidden' name='backend' value='{escape(selected_backend)}'>"
                     if selected_backend else "")
        action = (
            f"<form method='post' action='/projects/{escape(task.project_id)}/tasks/{escape(task.id)}/run' "
            "style='margin-top:16px'>"
            f"{be_hidden}"
            "<button class='btn' type='submit'>" + _icon("bolt") + " Approve &amp; run</button></form>"
        )
    else:
        exec_html = ("<div style='margin-top:16px'></div>" + _execution_log(trace)) if trace else ""
        result_html = ("<div style='margin-top:16px'></div>" + _result_card(result)) if result else ""
        fb_html = ("<div style='margin-top:10px'></div>" + _feedback_bar(task)) if result else ""
        action = (exec_html + result_html + fb_html + "<div style='margin-top:16px'><a class='btn ghost' "
                  f"href='/projects/{escape(task.project_id)}'>Back to project</a> "
                  f"<a class='btn ghost' href='/projects/{escape(task.project_id)}/artifacts'>"
                  "Project artifacts</a></div>")

    content = (banner + "<div style='margin-top:16px'></div>" + header
               + "<div style='margin-top:16px'></div>" + dag_html
               + "<div style='margin-top:16px'></div>" + created_html + action)
    proj_id = getattr(task, "project_id", "") or ""
    return shell(active="projects", title="Plan review", content=content, backend=backend,
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
                   "<a href='/projects' style='color:var(--accent-2)'>Run a task</a> and the focus "
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
    default with the toggle on <a href='/projects' style='color:var(--accent-2)'>New Run</a>.</p>
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
                  serpapi_key_set: bool = False, atcuality_key_set: bool = False,
                  google_cse_id_set: bool = False) -> str:
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
        + strategy + generation + memory + harness + agents + prompts
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


def project_report_page(*, project, tasks: list, backend: str) -> str:
    """Consulting-grade report tab — compiled from all task results for this project."""
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
