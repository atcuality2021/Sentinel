"""render.base — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from sentinel.artifacts.schemas import Boundary

# Chart.js from CDN — modern interactive charts without bundling. Demo runs online.
_CHARTJS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"

CSS = """
/* Dual-theme token contract. Components reference these names only; light is the default,
   dark is the legacy palette verbatim. Switching themes flips [data-theme] on <html>. */
:root,[data-theme="light"]{
  --bg:#f5f6f8; --panel:#ffffff; --panel-2:#f4f6f9; --rail:#ffffff; --ink:#161a20;
  --muted:#5f6b7a; --line:#e4e7ec; --public:#1a56db; --public-bg:#eaf1ff; --private:#b45309;
  --private-bg:#fdf2e3; --accent:#2563eb; --accent-2:#1d4ed8; --ok:#15803d; --bad:#dc2626;
  --chip:#eef1f5; --accent-soft:rgba(37,99,235,.10); --accent-line:#c7d6f5;
  --topbar-bg:rgba(255,255,255,.82); --shadow:0 1px 2px rgba(16,24,40,.04),0 1px 3px rgba(16,24,40,.06);
}
[data-theme="dark"]{
  --bg:#0b0e14; --panel:#151a23; --panel-2:#11151d; --rail:#0c0f16; --ink:#e8eaed;
  --muted:#9aa0a6; --line:#2a2f3a; --public:#4ea1ff; --public-bg:#11233d; --private:#ffb24d;
  --private-bg:#2e2410; --accent:#4285f4; --accent-2:#8ab4f8; --ok:#34a853; --bad:#ea4335;
  --chip:#1b212c; --accent-soft:rgba(66,133,244,.14); --accent-line:#2c4a7a;
  --topbar-bg:rgba(10,14,22,.82); --shadow:none;
}
*{box-sizing:border-box} html,body{margin:0;height:100%;overflow-x:hidden}
body{background:var(--bg);color:var(--ink);font:14.5px/1.55 -apple-system,BlinkMacSystemFont,
  "Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;
  transition:background .2s ease,color .2s ease}
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
  background:var(--topbar-bg);backdrop-filter:blur(8px);z-index:5}
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
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 22px;box-shadow:var(--shadow)}
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
.proj-subnav{border-bottom:1px solid var(--line);background:var(--topbar-bg);
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

/* ---- mobile: off-canvas sidebar drawer + responsive layout ---- */
/* The topbar hamburger and the scrim backdrop are hidden on desktop; they only
   appear at <=768px where the sidebar leaves the grid flow and slides over content. */
.mobileNavBtn{display:none}
.scrim{display:none}
@media(max-width:768px){
  /* shell becomes a single column; the sidebar overlays instead of taking a column */
  .shell,.shell.collapsed{grid-template-columns:1fr}
  .sidebar{position:fixed;top:0;left:0;height:100dvh;width:min(84vw,290px);z-index:60;
    transform:translateX(-100%);transition:transform .22s ease}
  .shell.mobile-open .sidebar{transform:translateX(0);box-shadow:0 18px 50px rgba(0,0,0,.6)}
  /* a phone always shows full labels in the drawer, even if desktop state was collapsed */
  .shell.collapsed .brand-text,.shell.collapsed .nav-label,
  .shell.collapsed .side-foot,.shell.collapsed .nav-group-label{display:revert}
  .shell.collapsed .side-top{justify-content:flex-start;padding:18px 16px 12px}
  .shell.collapsed .nav-item{justify-content:flex-start;padding:10px 12px}
  /* the in-drawer collapse toggle is meaningless on a phone — the hamburger + scrim drive it */
  .navToggle{display:none}
  /* backdrop behind the open drawer; tapping it closes the drawer (see _MOBILE_NAV_JS) */
  .scrim{position:fixed;inset:0;background:rgba(4,6,10,.55);z-index:55}
  .shell.mobile-open .scrim{display:block}
  .mobileNavBtn{display:inline-flex;align-items:center;justify-content:center;background:transparent;
    border:1px solid var(--line);color:var(--ink);width:40px;height:40px;border-radius:9px;
    cursor:pointer;flex:0 0 auto}
  .mobileNavBtn:hover{border-color:var(--accent-line)}
  /* tighten the chrome so content gets the width back */
  .topbar-inner{padding:12px 16px;gap:10px}
  .content{padding:18px 16px 56px}
  .crumb{font-size:12px}
  .proj-pill{display:none}              /* least-critical bar item — drop it on phones */
  .proj-subnav{top:53px}
  .proj-subnav-inner{padding:0 12px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  /* wide tables scroll horizontally instead of crushing their columns */
  .content table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
  /* per-task control cluster stacks under the objective instead of fighting for width */
  .task-row{grid-template-columns:1fr}
  .task-row .tr-actions{flex-wrap:wrap}
  .btn-sm{padding:8px 12px}             /* >=44px effective touch target */
  .proj-tab{padding:11px 12px}
  form.run,.set-grid,.note{max-width:100%}
}
@media(max-width:480px){
  .kpis{grid-template-columns:1fr}
  .row2{grid-template-columns:1fr}
  .hero h1{font-size:26px} .hero.left h1{font-size:21px} .hero p{font-size:14px}
  .topbar h1{font-size:15px}
  /* the topbar gets tight once the theme toggle is added — drop the redundant ghost button
     (Projects lives in the drawer) and the verbose backend pill so the crumb + toggle fit */
  .topbar-inner .btn.ghost{display:none}
  .topbar-inner .pill{display:none}
  .content{padding:16px 12px 48px}
  .rpt-cover{padding:28px 20px 24px} .rpt-cover h1{font-size:22px}
  .rpt-metrics,.acc-grid{grid-template-columns:1fr}
}

/* ==========================================================================
   REDESIGN DESIGN SYSTEM (ported from Open Design sentinel-redesign/tokens.css)
   One semantic token set themed by [data-theme]. Declared AFTER the legacy
   block so its component rules win for shared class names; legacy rules above
   still style un-migrated helper fragments. Light is the default.
   ========================================================================== */
:root,[data-theme="light"]{
  --surface:#ffffff; --surface-2:#f1f3f6; --rail-active:#eef2ff;
  --text:#161a20; --faint:#98a2b3; --line-strong:#d7dbe0;
  --accent:#4f46e5; --accent-text:#4338ca; --accent-weak:#eef2ff; --accent-ring:rgba(79,70,229,.28);
  --public:#2563eb; --public-bg:#eff5ff; --private:#b45309; --private-bg:#fff7ed;
  --ok:#15803d; --ok-bg:#effaf1; --bad:#dc2626; --bad-bg:#fef2f2; --warn:#b45309; --warn-bg:#fff7ed;
  --chip:#f1f3f6; --topbar-bg:rgba(255,255,255,.78);
  --shadow-sm:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.08);
  --shadow-md:0 4px 12px rgba(16,24,40,.08),0 2px 4px rgba(16,24,40,.05);
  --shadow-pop:0 12px 32px rgba(16,24,40,.16);
}
[data-theme="dark"]{
  --surface:#151a23; --surface-2:#11151d; --rail-active:#1a2233;
  --text:#e8eaed; --faint:#6b7280; --line-strong:#2f3744;
  --accent:#818cf8; --accent-text:#a5b4fc; --accent-weak:#1b2236; --accent-ring:rgba(129,140,248,.35);
  --public:#5aa9ff; --public-bg:#112138; --private:#ffb24d; --private-bg:#2c2310;
  --ok:#34d399; --ok-bg:#0f2a1e; --bad:#f87171; --bad-bg:#2c1416; --warn:#fbbf24; --warn-bg:#2c2310;
  --chip:#1b212c; --topbar-bg:rgba(11,14,20,.72);
  --shadow-sm:0 1px 2px rgba(0,0,0,.35); --shadow-md:0 6px 18px rgba(0,0,0,.45); --shadow-pop:0 16px 40px rgba(0,0,0,.6);
}
:root{
  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-pill:999px;
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px; --sp-6:32px; --sp-7:48px;
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; --sidebar-w:248px;
}
body{background:var(--bg);color:var(--text);font:14.5px/1.55 var(--font)}
svg{flex:none;vertical-align:middle}
h1,h2,h3{margin:0;font-weight:700;letter-spacing:-.01em} h1{font-size:26px} h2{font-size:16px}
.muted{color:var(--muted)} .faint{color:var(--faint)}
.mono{font-family:var(--mono);font-size:12.5px}
.eyebrow{font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
/* shell */
.shell{display:grid;grid-template-columns:var(--sidebar-w) 1fr;min-height:100vh}
.sidebar{background:var(--rail);border-right:1px solid var(--line);padding:var(--sp-4);
  display:flex;flex-direction:column;gap:var(--sp-2);position:sticky;top:0;height:100vh;overflow-y:auto}
.brand{display:flex;align-items:center;gap:10px;padding:4px 6px var(--sp-4);font-weight:700;font-size:16px}
.brand .logo{width:28px;height:28px;border-radius:8px;background:var(--accent);color:#fff;
  display:grid;place-items:center;font-weight:800;font-size:15px;box-shadow:var(--shadow-sm)}
.nav-group{margin-top:var(--sp-3)} .nav-group>.eyebrow{padding:0 8px var(--sp-2)}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:var(--r-sm);
  color:var(--muted);font-weight:500;cursor:pointer;border:none;transition:background .12s,color .12s}
.nav-item:hover{background:var(--surface-2);color:var(--text)}
.nav-item.active{background:var(--rail-active);color:var(--accent-text);font-weight:600}
.nav-item svg{width:18px;height:18px}
.side-foot{margin-top:auto;padding-top:var(--sp-4);color:var(--muted);font-size:11.5px;border-top:1px solid var(--line)}
/* topbar */
.main{display:flex;flex-direction:column;min-width:0}
.topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:var(--sp-3);
  padding:var(--sp-3) var(--sp-5);background:var(--topbar-bg);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line)}
.crumb{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
.crumb b{color:var(--text);font-weight:600} .crumb .sep{color:var(--faint)}
.spacer{flex:1}
.search{display:flex;align-items:center;gap:8px;background:var(--surface-2);border:1px solid var(--line);
  border-radius:var(--r-pill);padding:8px 16px;color:var(--muted);min-width:240px;font-size:13px;cursor:text}
.search:hover{border-color:var(--line-strong);color:var(--text)}
.search svg{width:16px;height:16px}
.search .kbd{margin-left:auto;font-size:11px;padding:1px 6px;border-radius:5px;border:1px solid var(--line);
  background:var(--surface);color:var(--faint)}
.icon-btn{width:38px;height:38px;border-radius:var(--r-sm);border:1px solid var(--line);background:var(--surface);
  display:grid;place-items:center;cursor:pointer;color:var(--muted);transition:color .12s,border-color .12s,transform .08s}
.icon-btn:active{transform:scale(.94)} .icon-btn svg{width:18px;height:18px}
.icon-btn:hover{color:var(--text);border-color:var(--line-strong)}
.mobile-only{display:none}
/* content */
.content{padding:var(--sp-6) var(--sp-6) var(--sp-7);max-width:1240px;width:100%;margin-inline:auto;
  animation:fade .26s ease both}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
a.card{transition:border-color .14s,box-shadow .14s,transform .14s}
a.card:hover{transform:translateY(-2px);box-shadow:var(--shadow-md);border-color:var(--line-strong)}
.page-head{display:flex;align-items:flex-start;gap:var(--sp-4);margin-bottom:var(--sp-5)}
.page-head .grow{flex:1;min-width:0} .page-head p{margin:6px 0 0;color:var(--muted)}
/* tabs */
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--line);margin-bottom:var(--sp-5);overflow-x:auto}
.tab{padding:10px 14px;color:var(--muted);font-weight:500;border-bottom:2px solid transparent;
  white-space:nowrap;cursor:pointer;display:flex;align-items:center;gap:7px}
.tab:hover{color:var(--text)} .tab.active{color:var(--accent-text);border-bottom-color:var(--accent);font-weight:600}
.tab svg{width:16px;height:16px}
/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:var(--sp-5);box-shadow:var(--shadow-sm)}
.card.pad-sm{padding:var(--sp-4)}
.card-head{display:flex;align-items:center;gap:var(--sp-3);margin-bottom:var(--sp-4)} .card-head h2{flex:1}
.grid{display:grid;gap:var(--sp-4)}
.cols-2{grid-template-columns:repeat(2,1fr)} .cols-3{grid-template-columns:repeat(3,1fr)}
.cols-4{grid-template-columns:repeat(4,1fr)}
.split{display:grid;grid-template-columns:2fr 1fr;gap:var(--sp-4)}
/* kpi */
.kpi{display:flex;flex-direction:column;gap:6px}
.kpi .label{font-size:12px;color:var(--muted);font-weight:500}
.kpi .value{font-size:30px;font-weight:700;letter-spacing:-.02em;line-height:1}
.kpi .delta{font-size:12px;font-weight:600} .kpi .delta.up{color:var(--ok)} .kpi .delta.down{color:var(--bad)}
.kpi-icon{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;
  background:var(--accent-weak);color:var(--accent-text);margin-bottom:4px}
.kpi-icon svg{width:20px;height:20px}
/* buttons */
.btn{display:inline-flex;align-items:center;gap:8px;justify-content:center;padding:9px 16px;
  border-radius:var(--r-sm);font-size:13.5px;font-weight:600;border:1px solid transparent;cursor:pointer;
  transition:filter .12s,background .12s;background:var(--accent);color:#fff;box-shadow:var(--shadow-sm)}
.btn:hover{filter:brightness(1.06)} .btn svg{width:16px;height:16px}
.btn.ghost{background:var(--surface);color:var(--text);border-color:var(--line-strong);box-shadow:none}
.btn.ghost:hover{background:var(--surface-2);filter:none}
.btn.danger{background:var(--bad)} .btn.sm{padding:6px 11px;font-size:12.5px}
/* pills + badges */
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:var(--r-pill);
  background:var(--chip);color:var(--muted);font-size:12px;font-weight:600;border:1px solid var(--line)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:var(--r-pill);
  font-size:11px;font-weight:700;letter-spacing:.02em;text-transform:uppercase}
.badge.public{color:var(--public);background:var(--public-bg)}
.badge.private{color:var(--private);background:var(--private-bg)}
.badge.ok{color:var(--ok);background:var(--ok-bg)} .badge.bad{color:var(--bad);background:var(--bad-bg)}
.badge.warn{color:var(--warn);background:var(--warn-bg)} .badge.neutral{color:var(--muted);background:var(--chip)}
/* tables */
.table{width:100%;border-collapse:collapse;font-size:13.5px}
.table th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);
  font-weight:600;padding:0 12px 10px;border-bottom:1px solid var(--line)}
.table td{padding:13px 12px;border-bottom:1px solid var(--line)}
.table tr:last-child td{border-bottom:none} .table tr:hover td{background:var(--surface-2)}
.table .num{text-align:right;font-variant-numeric:tabular-nums}
.table-wrap{overflow-x:auto}
/* forms */
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:var(--sp-4)}
.field label{font-size:12.5px;font-weight:600;color:var(--text)} .field .hint{font-size:12px;color:var(--muted)}
.input,.field select,.field textarea{width:100%;padding:10px 12px;font:inherit;font-size:13.5px;
  background:var(--surface);color:var(--text);border:1px solid var(--line-strong);border-radius:var(--r-sm);
  outline:none;transition:border-color .12s,box-shadow .12s}
.input:focus,.field select:focus,.field textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring)}
.field textarea{resize:vertical;min-height:90px}
.seg{display:inline-flex;background:var(--surface-2);border:1px solid var(--line);border-radius:var(--r-sm);padding:3px;gap:3px}
.seg button{border:none;background:none;padding:7px 14px;border-radius:6px;font:inherit;font-weight:600;
  font-size:12.5px;color:var(--muted);cursor:pointer}
.seg button.on{background:var(--surface);color:var(--accent-text);box-shadow:var(--shadow-sm)}
.toggle{width:40px;height:23px;border-radius:var(--r-pill);background:var(--line-strong);position:relative;
  cursor:pointer;transition:background .15s;flex:none;display:inline-block}
.toggle::after{content:"";position:absolute;top:2px;left:2px;width:19px;height:19px;border-radius:50%;
  background:#fff;transition:left .15s;box-shadow:var(--shadow-sm)}
.toggle.on{background:var(--accent)} .toggle.on::after{left:19px}
.row-between{display:flex;align-items:center;justify-content:space-between;gap:var(--sp-4)}
/* charts */
.donut{width:132px;height:132px;border-radius:50%;position:relative;flex:none}
.donut::after{content:"";position:absolute;inset:22px;background:var(--surface);border-radius:50%}
.donut .center{position:absolute;inset:0;display:grid;place-items:center;text-align:center;z-index:1}
.donut .center b{font-size:22px} .donut .center span{font-size:11px;color:var(--muted)}
.legend{display:flex;flex-direction:column;gap:9px}
.legend .row{display:flex;align-items:center;gap:9px;font-size:13px}
.legend .sw{width:11px;height:11px;border-radius:3px;flex:none}
.legend .val{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--muted)}
.bars{display:flex;align-items:flex-end;gap:12px;height:130px;padding-top:8px}
.bars .bar{flex:1;background:var(--accent);border-radius:6px 6px 0 0;min-height:4px;position:relative;opacity:.85}
.bars .bar span{position:absolute;top:-20px;left:0;right:0;text-align:center;font-size:11px;color:var(--muted)}
.bars .bar small{position:absolute;bottom:-20px;left:0;right:0;text-align:center;font-size:11px;color:var(--muted)}
.spark{display:flex;align-items:flex-end;gap:3px;height:40px} .spark i{flex:1;background:var(--accent-weak);border-radius:2px}
/* timeline */
.timeline{display:flex;flex-direction:column}
.tl-step{display:grid;grid-template-columns:28px 1fr;gap:14px;padding-bottom:var(--sp-4);position:relative}
.tl-step::before{content:"";position:absolute;left:13px;top:26px;bottom:-4px;width:2px;background:var(--line)}
.tl-step:last-child::before{display:none}
.tl-dot{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:var(--surface-2);
  border:2px solid var(--line-strong);color:var(--muted);z-index:1}
.tl-step.done .tl-dot{background:var(--ok-bg);border-color:var(--ok);color:var(--ok)}
.tl-step.running .tl-dot{background:var(--accent-weak);border-color:var(--accent);color:var(--accent-text);
  animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 var(--accent-ring)}50%{box-shadow:0 0 0 6px transparent}}
.tl-body{padding-top:2px} .tl-body .t{font-weight:600} .tl-body .m{font-size:12.5px;color:var(--muted);margin-top:2px}
.tl-body .agent{font-family:var(--mono);font-size:11.5px;color:var(--accent-text)}
/* DAG */
.dag{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.dag .node{background:var(--surface);border:1px solid var(--line-strong);border-radius:var(--r-md);
  padding:10px 14px;box-shadow:var(--shadow-sm);min-width:120px}
.dag .node .cap{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.dag .node .nm{font-weight:600;font-size:13px;margin-top:3px}
.dag .node.dashed{border-style:dashed;opacity:.65;box-shadow:none} .dag .arrow{color:var(--faint)}
/* misc */
.empty{text-align:center;padding:var(--sp-7) var(--sp-4);color:var(--muted)}
.empty .ico{width:48px;height:48px;margin:0 auto var(--sp-3);color:var(--faint)}
.divider{height:1px;background:var(--line);margin:var(--sp-4) 0}
.stack{display:flex;flex-direction:column;gap:var(--sp-3)}
.inline{display:flex;align-items:center;gap:var(--sp-2);flex-wrap:wrap}
.scrim{display:none}
/* auth */
.auth-wrap{min-height:100vh;display:grid;place-items:center;padding:var(--sp-4);
  background:radial-gradient(900px 500px at 50% -10%,var(--accent-weak),var(--bg))}
.auth-card{width:100%;max-width:380px}
/* responsive */
@media (max-width:980px){.split{grid-template-columns:1fr}.cols-4{grid-template-columns:repeat(2,1fr)}.cols-3{grid-template-columns:1fr}}
@media (max-width:760px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:fixed;z-index:50;width:280px;transform:translateX(-100%);transition:transform .22s ease}
  .shell.nav-open .sidebar{transform:translateX(0);box-shadow:var(--shadow-pop)}
  .shell.nav-open .scrim{display:block;position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:40}
  .mobile-only{display:grid}
  .search{display:none}
  .cols-2,.cols-4{grid-template-columns:1fr}
  .content{padding:var(--sp-4)}
}
@media (max-width:460px){h1{font-size:22px}.page-head{flex-wrap:wrap}.topbar{padding:var(--sp-3) var(--sp-4)}.btn{padding:8px 13px}}
@media (min-width:1700px){:root{--sidebar-w:276px}body{font-size:15px}.content{max-width:1520px}}
@media (min-width:2400px){:root{--sidebar-w:320px}body{font-size:16.5px}.content{max-width:1960px;padding:44px 56px 72px}h1{font-size:30px}.kpi .value{font-size:34px}}
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
        "target": "<circle cx='12' cy='12' r='9'/><circle cx='12' cy='12' r='4.5'/><circle cx='12' cy='12' r='1'/>",
        "sun": "<circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19'/>",
        "moon": "<path d='M21 12.8A8 8 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8z'/>",
    }.get(name, "")
    return (
        f"<svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>{p}</svg>"
    )


# Grouped navigation. Two intents: Workspace (where research happens — projects, accounts, focus)
# and Configure (the agent platform's knobs — agents, personas, prompts, settings). Each item:
# (key, label, icon, href). The key matches the page's ``active`` marker.
_NAV_GROUPS = [
    ("Workspace", [
        ("dashboard", "Dashboard", "grid", "/"),
        ("projects", "Projects", "plan", "/projects"),
        ("accounts", "Accounts", "users", "/accounts"),
        ("focus", "Focus", "target", "/focus"),
    ]),
    ("Configure", [
        ("agents", "Agents", "agent", "/agents"),
        ("personas", "Personas", "users", "/personas"),
        ("prompts", "Prompts", "doc", "/settings/prompts"),
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
                f"<span>{label}</span></a>"
            )
        blocks.append(
            f"<div class='nav-group'><div class='eyebrow'>{group}</div>{''.join(rows)}</div>"
        )
    return (
        "<aside class='sidebar'>"
        "<div class='brand'><span class='logo'>S</span> Sentinel</div>"
        f"{''.join(blocks)}"
        "<div class='side-foot'>Sovereign Intelligence Agent<br>Public &amp; private signal, "
        "separated by design.<br><a href='/logout' style='color:var(--muted);font-size:11px;"
        "margin-top:6px;display:inline-block'>Sign out</a></div>"
        "</aside>"
    )


# The redesign sidebar does not collapse (only the mobile drawer slides). Kept as a no-op so the
# shell() script reference stays valid without a dead localStorage flag forcing a collapsed rail.
_COLLAPSE_JS = ""

# Mobile drawer: the topbar hamburger toggles `.nav-open` on the shell (which slides the
# fixed-position sidebar in via CSS); tapping the scrim or any nav link closes it again. No
# localStorage — a phone drawer should always start closed on each page load.
_MOBILE_NAV_JS = """
(function(){var s=document.getElementById('shell');if(!s)return;
function close(){s.classList.remove('nav-open');}
var mb=document.getElementById('mobileNavToggle');
if(mb)mb.addEventListener('click',function(){s.classList.toggle('nav-open');});
var sc=document.getElementById('navScrim');if(sc)sc.addEventListener('click',close);
s.querySelectorAll('.sidebar a').forEach(function(a){a.addEventListener('click',close);});
window.addEventListener('keydown',function(e){if(e.key==='Escape')close();});})();
"""

# Theme toggle: light is the default; the choice persists in localStorage 'sentinel-theme'. The
# no-FOUC init (set in <head> before paint) reads the same key, so a reload keeps the chosen theme
# without a flash. The toggle button swaps its own sun/moon glyph to mirror the *next* theme.
_THEME_INIT_JS = (
    "(function(){try{var t=localStorage.getItem('sentinel-theme');"
    "if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}})();"
)
_SUN_PATH = ("<circle cx='12' cy='12' r='4'/><path d='M12 2v2M12 20v2M2 12h2M20 12h2"
             "M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19'/>")
_MOON_PATH = "<path d='M21 12.8A8 8 0 1 1 11.2 3 6.5 6.5 0 0 0 21 12.8z'/>"
_THEME_JS = (
    "(function(){var b=document.getElementById('themeToggle');if(!b)return;"
    "var SUN=\"%s\",MOON=\"%s\";"
    "function paint(t){b.innerHTML=\"<svg width='18' height='18' viewBox='0 0 24 24' fill='none' \""
    "+\"stroke='currentColor' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'>\""
    "+(t==='dark'?SUN:MOON)+\"</svg>\";}"
    "paint(document.documentElement.getAttribute('data-theme')||'light');"
    "b.addEventListener('click',function(){"
    "var cur=document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light';"
    "var next=cur==='dark'?'light':'dark';"
    "document.documentElement.setAttribute('data-theme',next);"
    "try{localStorage.setItem('sentinel-theme',next);}catch(e){}paint(next);});})();"
) % (_SUN_PATH, _MOON_PATH)

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
        f"<a class='tab {'active' if key == active_tab else ''}' href='{hrefs[key]}'>"
        f"{_icon(icon)}{label}</a>"
        for key, label, icon in _PROJECT_TABS
    )
    return f"<div class='tabs'>{tabs}</div>"


def shell(*, active: str, title: str, content: str, backend: str, head_extra: str = "",
          body_scripts: str = "", project: str = "sovereign", subnav: str = "") -> str:
    """Wrap a content fragment in the full dashboard shell.

    ``project`` labels the top-bar pill.
    ``subnav`` is an optional horizontal tab strip (rendered below the topbar, sticky).
    """
    backend_pill = (
        f"<span class='pill'><span class='dot' style='background:"
        f"{'var(--private)' if backend=='vllm' else 'var(--ok)'}'></span>"
        f"Backend: <b>{escape(backend)}</b></span>"
    )
    return (
        "<!doctype html><html lang='en' data-theme='light'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<script>{_THEME_INIT_JS}</script>"
        "<link rel='icon' href=\"data:image/svg+xml,"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        "<rect x='5' y='5' width='22' height='22' rx='6' fill='%234f46e5'/></svg>\">"
        f"<title>{escape(title)} · Sentinel</title><style>{CSS}</style>{head_extra}</head>"
        "<body><div class='shell' id='shell'>"
        f"{_sidebar(active)}"
        "<div class='scrim' id='navScrim'></div>"
        "<div class='main'>"
        "<header class='topbar'>"
        "<button class='icon-btn mobile-only' id='mobileNavToggle' aria-label='Open menu'>"
        f"{_icon('menu')}</button>"
        "<div class='crumb'><span>Sentinel</span><span class='sep'>/</span>"
        f"<b>{escape(title)}</b></div>"
        "<div class='spacer'></div>"
        "<label class='search'>" + _icon("search") +
        "<input type='search' placeholder='Search projects, entities…' "
        "style='border:none;background:none;outline:none;padding:0;font:inherit;"
        "color:var(--text);flex:1;min-width:0'><span class='kbd'>⌘K</span></label>"
        f"<span class='pill proj-pill'>{_icon('shield')} project: {escape(project)}</span>"
        f"{backend_pill}"
        "<button class='icon-btn' id='themeToggle' aria-label='Toggle light/dark theme' "
        f"title='Toggle theme'>{_icon('moon')}</button>"
        "</header>"
        f"{subnav}"
        f"<div class='content'>{content}</div>"
        "</div>"
        "</div>"
        f"{_LOADER_HTML}"
        f"<script>{_COLLAPSE_JS}{_MOBILE_NAV_JS}{_THEME_JS}{_LOADER_JS}</script>{body_scripts}</body></html>"
    )


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def _kpi(cls: str, label: str, value, icon: str) -> str:
    return (
        f"<div class='card kpi {cls}'><div class='kpi-icon'>{_icon(icon)}</div>"
        f"<div class='label'>{escape(label)}</div>"
        f"<div class='value'>{value}</div></div>"
    )


# --------------------------------------------------------------------------- #
# Finding / gap fragments
# --------------------------------------------------------------------------- #
def _badge(b) -> str:
    # b may be a Boundary enum or a plain string after JSON round-trip
    val = b.value if isinstance(b, Boundary) else str(b)
    cls = "public" if val == Boundary.PUBLIC.value else "private"
    return f"<span class='badge {cls}'>{val}</span>"
