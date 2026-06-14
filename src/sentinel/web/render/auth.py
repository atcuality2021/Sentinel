"""render.auth — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape

from .base import _THEME_INIT_JS

# --------------------------------------------------------------------------- #
# Auth pages — login + first-boot setup (no shell wrapper, standalone HTML)
# --------------------------------------------------------------------------- #
_AUTH_CSS = """
<style>
:root,[data-theme="light"]{--abg:#f5f6f8;--abox:#ffffff;--aline:#e4e7ec;--aink:#161a20;
  --amut:#5f6b7a;--ainset:#f4f6f9;--aacc:#2563eb;--ashadow:0 8px 40px rgba(16,24,40,.12)}
[data-theme="dark"]{--abg:#0b0e14;--abox:#151a23;--aline:#2a2f3a;--aink:#e8eaed;
  --amut:#9aa0a6;--ainset:#11151d;--aacc:#4285f4;--ashadow:0 8px 48px rgba(0,0,0,.55)}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--abg);color:var(--aink);
  font:14.5px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px}
.box{background:var(--abox);border:1px solid var(--aline);border-radius:18px;padding:40px 36px;
  width:100%;max-width:400px;box-shadow:var(--ashadow)}
.logo{display:flex;align-items:center;gap:12px;margin-bottom:28px}
.logo-mark{width:38px;height:38px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;background:linear-gradient(135deg,#4285f4,#a142f4);
  color:#fff;font-weight:800;font-size:18px;flex:0 0 auto}
.logo-text{font-size:20px;font-weight:700;letter-spacing:.2px}
h2{font-size:16px;font-weight:600;margin:0 0 6px}
.sub{color:var(--amut);font-size:13px;margin:0 0 24px}
label{font-size:11.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--amut);
  display:block;margin-bottom:6px}
input[type=password]{width:100%;background:var(--ainset);border:1px solid var(--aline);color:var(--aink);
  padding:11px 13px;border-radius:10px;font-size:14.5px;margin-bottom:16px}
input[type=password]:focus{outline:none;border-color:var(--aacc)}
.btn-full{width:100%;background:var(--aacc);color:#fff;border:0;padding:13px;border-radius:10px;
  font-size:15px;font-weight:600;cursor:pointer;margin-top:4px}
.btn-full:hover{filter:brightness(1.1)}
.err{background:rgba(220,38,38,.10);border:1px solid rgba(220,38,38,.35);color:#dc2626;border-radius:8px;
  padding:10px 14px;font-size:13px;margin-bottom:16px}
.foot{color:var(--amut);font-size:12px;text-align:center;margin-top:18px}
</style>
"""


def login_page(*, next_url: str = "", err: str = "") -> str:
    err_html = f"<div class='err'>{escape(err)}</div>" if err else ""
    next_field = f"<input type='hidden' name='next' value='{escape(next_url)}'>" if next_url else ""
    return f"""<!doctype html><html lang='en' data-theme='light'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<script>{_THEME_INIT_JS}</script>
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
    return f"""<!doctype html><html lang='en' data-theme='light'><head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<script>{_THEME_INIT_JS}</script>
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
