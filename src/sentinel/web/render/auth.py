"""render.auth — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import _THEME_INIT_JS

# --------------------------------------------------------------------------- #
# Auth pages — login + first-boot setup (no shell wrapper, standalone HTML)
# --------------------------------------------------------------------------- #
# These pages are standalone (no sidebar shell) and do not link the main CSS,
# so _AUTH_CSS carries a minimal, self-contained slice of the design system:
# the theme tokens (light default + dark) plus the auth classes
# (.auth-wrap/.auth-card/.card/.brand/.logo/.field/.input/.btn/.muted/.faint),
# mirroring the canonical definitions in base.py. Light is the default and the
# choice persists via the 'sentinel-theme' localStorage key (theme-init script).
_AUTH_CSS = """
<style>
:root,[data-theme="light"]{--bg:#f5f6f8;--surface:#ffffff;--surface-2:#f1f3f6;--text:#161a20;
  --muted:#5f6b7a;--faint:#98a2b3;--line:#e4e7ec;--line-strong:#d7dbe0;
  --accent:#4f46e5;--accent-weak:#eef2ff;--accent-ring:rgba(79,70,229,.28);
  --bad:#dc2626;--bad-bg:#fef2f2;--r-sm:8px;--r-lg:16px;
  --shadow-md:0 4px 12px rgba(16,24,40,.08),0 2px 4px rgba(16,24,40,.05)}
[data-theme="dark"]{--bg:#0b0e14;--surface:#151a23;--surface-2:#11151d;--text:#e8eaed;
  --muted:#9aa0a6;--faint:#6b7280;--line:#2a2f3a;--line-strong:#2f3744;
  --accent:#818cf8;--accent-weak:#1b2236;--accent-ring:rgba(129,140,248,.35);
  --bad:#f87171;--bad-bg:#2c1416;
  --shadow-md:0 6px 18px rgba(0,0,0,.45)}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);
  font:14.5px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h2{margin:0;font-size:16px;font-weight:700;letter-spacing:-.01em}
.muted{color:var(--muted)} .faint{color:var(--faint)}
.auth-wrap{min-height:100vh;display:grid;place-items:center;padding:16px;
  background:radial-gradient(900px 500px at 50% -10%,var(--accent-weak),var(--bg))}
.auth-card{width:100%;max-width:380px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);
  padding:32px 28px;box-shadow:var(--shadow-md)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:18px}
.brand .logo{width:28px;height:28px;border-radius:8px;background:var(--accent);color:#fff;
  display:grid;place-items:center;font-weight:800;font-size:15px}
.icon-btn{background:var(--surface);border:1px solid var(--line);color:var(--muted);width:34px;height:34px;
  border-radius:var(--r-sm);display:grid;place-items:center;cursor:pointer;font-size:16px}
.icon-btn:hover{color:var(--text);border-color:var(--line-strong)}
.field{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}
.field label{font-size:12.5px;font-weight:600;color:var(--text)}
.field .hint{font-size:12px;color:var(--muted);font-weight:400}
.input{width:100%;padding:10px 12px;font:inherit;font-size:13.5px;background:var(--surface);
  color:var(--text);border:1px solid var(--line-strong);border-radius:var(--r-sm);outline:none;
  transition:border-color .12s,box-shadow .12s}
.input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring)}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:11px 16px;border:0;
  border-radius:var(--r-sm);font:inherit;font-size:14px;font-weight:600;color:#fff;
  background:var(--accent);cursor:pointer}
.btn:hover{filter:brightness(1.06)}
.err{background:var(--bad-bg);border:1px solid var(--bad);color:var(--bad);border-radius:var(--r-sm);
  padding:10px 14px;font-size:13px;margin-bottom:16px}
</style>
"""

# Top-right theme toggle: flips [data-theme] on <html> and persists to
# 'sentinel-theme' localStorage so the no-FOUC init script restores it.
_THEME_TOGGLE = (
    "<button class='icon-btn' style='position:fixed;top:18px;right:18px' aria-label='Toggle theme' "
    "onclick=\"(function(){var d=document.documentElement,"
    "n=d.getAttribute('data-theme')==='dark'?'light':'dark';d.setAttribute('data-theme',n);"
    "try{localStorage.setItem('sentinel-theme',n)}catch(e){}})()\">◐</button>"
)


def login_page(*, next_url: str = "", err: str = "") -> str:
    err_html = f"<div class='err'>{escape(err)}</div>" if err else ""
    next_field = f"<input type='hidden' name='next' value='{escape(next_url)}'>" if next_url else ""
    return f"""<!doctype html><html lang='en' data-theme='light'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<script>{_THEME_INIT_JS}</script>
<title>Sign in · Sentinel</title>{_AUTH_CSS}</head>
<body>{_THEME_TOGGLE}
<div class='auth-wrap'><div class='auth-card card'>
<div class='brand' style='justify-content:center;padding-bottom:8px'><span class='logo'>S</span> Sentinel</div>
<p class='muted' style='text-align:center;margin-top:0'>Sign in to your sovereign instance</p>
{err_html}
<form method='post' action='/login'>
{next_field}
<div class='field' style='margin-top:20px'>
<label for='pw'>Password</label>
<input class='input' type='password' id='pw' name='password' autofocus required placeholder='••••••••'>
</div>
<button class='btn' style='width:100%' type='submit'>Sign in</button>
</form>
<p class='faint' style='text-align:center;font-size:12px;margin-bottom:0;margin-top:18px'>Session expires after 12 hours · sessions are httpOnly</p>
</div></div></body></html>"""


def setup_page(*, err: str = "") -> str:
    err_html = f"<div class='err'>{escape(err)}</div>" if err else ""
    return f"""<!doctype html><html lang='en' data-theme='light'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<script>{_THEME_INIT_JS}</script>
<title>First-boot setup · Sentinel</title>{_AUTH_CSS}</head>
<body>{_THEME_TOGGLE}
<div class='auth-wrap'><div class='auth-card card'>
<div class='brand' style='justify-content:center;padding-bottom:8px'><span class='logo'>S</span> Sentinel</div>
<h2 style='text-align:center'>Welcome — set your password</h2>
<p class='muted' style='text-align:center;margin-top:4px'>This is the first boot of this instance.</p>
{err_html}
<form method='post' action='/setup'>
<div class='field' style='margin-top:20px'>
<label for='pw'>Password <span class='hint'>min 8 characters</span></label>
<input class='input' type='password' id='pw' name='password' autofocus required placeholder='••••••••'>
</div>
<div class='field'>
<label for='pw2'>Confirm password</label>
<input class='input' type='password' id='pw2' name='confirm' required placeholder='••••••••'>
</div>
<button class='btn' style='width:100%' type='submit'>Create password &amp; continue</button>
</form>
</div></div></body></html>"""
