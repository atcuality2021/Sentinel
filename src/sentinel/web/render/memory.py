"""render.memory — split from render.py (presentation only)."""

from __future__ import annotations
import html as _html
from html import escape

from sentinel.memory.schema import normalize_entity
from .base import _icon, _project_subnav, shell

# ── Source badge helpers (SENTINEL-023 Task 9) ────────────────────────────────
# Maps source_type string to (display label, extra tag).  The extra tag is only
# emitted when boundary is NOT already private — email always forces PRIVATE.
_SOURCE_BADGES: dict[str, tuple[str, str]] = {
    "website":  ("🌐 Website",  ""),
    "youtube":  ("▶ YouTube",   ""),
    "email":    ("✉ Email",     "PRIVATE"),
    "social":   ("📢 Social",   ""),
    "research": ("🔬 Research", ""),
}


def _source_badge(entry: object) -> str:
    """Return HTML badge(s) for a MemoryEntry's source_type and boundary."""
    source_type = (getattr(entry, "source_type", None) or "research")
    if source_type not in _SOURCE_BADGES:
        source_type = "research"
    label, extra = _SOURCE_BADGES[source_type]
    badge = (
        f"<span class='badge badge-{_html.escape(source_type)}'>"
        f"{_html.escape(label)}</span>"
    )
    boundary_val = getattr(getattr(entry, "boundary", None), "value", "")
    if boundary_val == "private" or source_type == "email":
        badge += " <span class='badge badge-private'>PRIVATE</span>"
    elif extra:
        badge += f" <span class='badge badge-private'>{_html.escape(extra)}</span>"
    return badge

def _memory_sources_form(entity: str) -> tuple[str, str]:
    """Memory Sources CRUD card: priority picker + per-source toggles + URL inputs.

    Returns (html, body_js) — same pattern as _account_donut so the caller can
    concatenate JS and pass it to shell(body_scripts=…).
    """
    slug = escape(entity.lower().replace(" ", "-"))

    html = (
        "<div class='card' id='ms-card' style='margin-top:18px'>"
        "<div class='card-head'><h2>Memory Sources</h2>"
        "<div class='inline' style='gap:8px'>"
        "<button class='btn ghost btn-sm' id='ms-crawl-btn' onclick='msCrawlNow()' "
        "style='padding:6px 12px'>Crawl Now</button>"
        "<button class='btn btn-sm' id='ms-save-btn' onclick='msSave()' "
        "style='padding:6px 12px'>Save</button>"
        "</div></div>"
        "<div class='stack' style='gap:12px'>"
        # ── priority pills ──────────────────────────────────────────────────
        "<div style='display:flex;align-items:center;justify-content:space-between;gap:12px'>"
        "<span style='font-size:12.5px;font-weight:600;color:var(--muted)'>Refresh priority</span>"
        "<div style='display:flex;gap:6px' id='ms-priority'>"
        "<button class='pill' id='ms-p-high' data-p='high' "
        "onclick='msSetPriority(this)'>High · 1 h</button>"
        "<button class='pill' id='ms-p-medium' data-p='medium' "
        "onclick='msSetPriority(this)'>Medium · 6 h</button>"
        "<button class='pill' id='ms-p-low' data-p='low' "
        "onclick='msSetPriority(this)'>Low · 24 h</button>"
        "</div></div>"
        "<div class='divider'></div>"
        # ── website ─────────────────────────────────────────────────────────
        "<div style='display:flex;align-items:center;gap:10px'>"
        "<label style='display:flex;align-items:center;gap:6px;width:170px;"
        "font-size:13px;cursor:pointer;flex-shrink:0'>"
        "<input type='checkbox' id='ms-en-website'> 🌐 Website</label>"
        "<input type='url' class='input' id='ms-inp-website' "
        "placeholder='https://company.com' style='flex:1;margin:0'></div>"
        # ── email (PRIVATE) ─────────────────────────────────────────────────
        "<div style='display:flex;align-items:center;gap:10px'>"
        "<label style='display:flex;align-items:center;gap:6px;width:170px;"
        "font-size:13px;cursor:pointer;flex-shrink:0'>"
        "<input type='checkbox' id='ms-en-email'> ✉ Email "
        "<span class='badge private' style='font-size:10px;padding:1px 5px'>PRIVATE</span>"
        "</label>"
        "<input type='text' class='input' id='ms-inp-email' "
        "placeholder='from:company.com' style='flex:1;margin:0'></div>"
        # ── youtube ─────────────────────────────────────────────────────────
        "<div style='display:flex;align-items:center;gap:10px'>"
        "<label style='display:flex;align-items:center;gap:6px;width:170px;"
        "font-size:13px;cursor:pointer;flex-shrink:0'>"
        "<input type='checkbox' id='ms-en-youtube'> ▶ YouTube</label>"
        "<input type='text' class='input' id='ms-inp-youtube' "
        "placeholder='@ChannelHandle' style='flex:1;margin:0'></div>"
        # ── social ──────────────────────────────────────────────────────────
        "<div style='display:flex;align-items:center;gap:10px'>"
        "<label style='display:flex;align-items:center;gap:6px;width:170px;"
        "font-size:13px;cursor:pointer;flex-shrink:0'>"
        "<input type='checkbox' id='ms-en-social'> 📢 Social</label>"
        "<input type='text' class='input' id='ms-inp-social' "
        "placeholder='twitter:@handle, linkedin:company' style='flex:1;margin:0'></div>"
        # ── status bar ──────────────────────────────────────────────────────
        "<div class='divider'></div>"
        "<div id='ms-status' style='font-size:12px;color:var(--muted);min-height:16px'></div>"
        "</div></div>"
    )

    js = f"""<script>
(function(){{
  var SLUG='{slug}';
  var _p='medium';
  function _status(msg,ok){{
    var el=document.getElementById('ms-status');
    if(el){{el.textContent=msg;el.style.color=ok?'var(--ok)':'var(--bad)';}}
  }}
  function _pillActive(val){{
    ['high','medium','low'].forEach(function(k){{
      var b=document.getElementById('ms-p-'+k);
      if(!b)return;
      if(k===val){{b.style.background='var(--accent)';b.style.color='#fff';b.style.borderColor='var(--accent)';}}
      else{{b.style.background='';b.style.color='';b.style.borderColor='';}}
    }});
  }}
  function msSetPriority(btn){{_p=btn.getAttribute('data-p');_pillActive(_p);}}
  window.msSetPriority=msSetPriority;
  function _load(){{
    fetch('/api/memory/source-config/'+SLUG)
      .then(function(r){{return r.json();}})
      .then(function(d){{
        _p=d.priority||'medium';_pillActive(_p);
        var en=d.sources_enabled||['website'];
        ['website','email','youtube','social'].forEach(function(s){{
          var cb=document.getElementById('ms-en-'+s);if(cb)cb.checked=en.indexOf(s)!==-1;
        }});
        var w=document.getElementById('ms-inp-website');if(w)w.value=d.website_url||'';
        var e=document.getElementById('ms-inp-email');if(e)e.value=d.email_filter||'';
        var y=document.getElementById('ms-inp-youtube');if(y)y.value=d.youtube_channel||'';
        var sc=document.getElementById('ms-inp-social');if(sc)sc.value=d.social_handles||'';
        _status('Config loaded',true);
      }}).catch(function(){{_status('Could not load config',false);}});
  }}
  function msSave(){{
    var en=['website','email','youtube','social'].filter(function(s){{
      var cb=document.getElementById('ms-en-'+s);return cb&&cb.checked;
    }});
    var w=document.getElementById('ms-inp-website')||{{}};
    var em=document.getElementById('ms-inp-email')||{{}};
    var yt=document.getElementById('ms-inp-youtube')||{{}};
    var sc=document.getElementById('ms-inp-social')||{{}};
    var payload={{priority:_p,sources_enabled:en,website_url:w.value||'',
      email_filter:em.value||'',youtube_channel:yt.value||'',social_handles:sc.value||''}};
    var btn=document.getElementById('ms-save-btn');if(btn)btn.disabled=true;
    _status('Saving…',true);
    fetch('/api/memory/source-config/'+SLUG,{{
      method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)
    }}).then(function(r){{
      if(!r.ok)return r.json().then(function(e){{throw new Error(e.detail||r.status);}});
      return r.json();
    }}).then(function(){{_status('Saved ✓',true);}})
    .catch(function(e){{_status('Error: '+e.message,false);}})
    .finally(function(){{if(btn)btn.disabled=false;}});
  }}
  window.msSave=msSave;
  function msCrawlNow(){{
    var btn=document.getElementById('ms-crawl-btn');if(btn)btn.disabled=true;
    _status('Queueing crawl…',true);
    fetch('/api/memory/crawl-now/'+SLUG,{{method:'POST'}})
      .then(function(r){{
        if(!r.ok)return r.json().then(function(e){{throw new Error(e.detail||r.status);}});
        return r.json();
      }}).then(function(d){{_status('Crawl queued — '+(d.enqueued||0)+' job(s) ✓',true);}})
      .catch(function(e){{_status('Error: '+e.message,false);}})
      .finally(function(){{if(btn)btn.disabled=false;}});
  }}
  window.msCrawlNow=msCrawlNow;
  if(document.readyState==='loading'){{document.addEventListener('DOMContentLoaded',_load);}}
  else{{_load();}}
}})();
</script>"""

    return html, js


def project_memory_page(*, project, records: list, backend: str,
                        ok: str = "", err: str = "",
                        semantic_facts: list = None) -> str:
    """Memory tab — episodic run records scoped to this project."""
    semantic_facts = semantic_facts or []
    pid = escape(project.id)
    banner = ""
    if ok:
        banner = f"<div class='card pad-sm' style='margin-bottom:16px;color:var(--ok)'>{escape(ok)}</div>"
    elif err:
        banner = f"<div class='card pad-sm' style='margin-bottom:16px;color:var(--bad)'>{escape(err)}</div>"

    def _row(r) -> str:
        ts = str(r.created_at or "")[:16]
        n_findings = len(getattr(r, "finding_texts", []) or [])
        run_id = escape(str(r.id))
        return (
            f"<tr>"
            f"<td><b>{escape(r.entity)}</b></td>"
            f"<td><span class='pill'>{escape(r.mode)}</span></td>"
            f"<td>{escape(r.backend)}</td>"
            f"<td class='num'>{n_findings}</td>"
            f"<td class='muted mono'>{ts}</td>"
            f"<td><form method='post' "
            f"action='/projects/{pid}/memory/{run_id}/delete' "
            f"onsubmit=\"return confirm('Remove this run from episodic memory?')\">"
            f"<button type='submit' class='btn sm danger'>Delete</button>"
            f"</form></td>"
            f"</tr>"
        )

    # ── Episodic runs card (left, 2fr) — every research run scoped to project ──
    if records:
        rows_html = "".join(_row(r) for r in records)
        header_pill = f"<span class='pill'>{len(records)} record(s)</span>"
        episodic_card = (
            "<div class='card'>"
            f"<div class='card-head'><h2>Episodic runs</h2>{header_pill}</div>"
            "<div class='table-wrap'><table class='table'><thead><tr>"
            "<th>Target</th><th>Mode</th><th>Provenance</th>"
            "<th class='num'>Findings</th><th>When</th><th></th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div>"
            "<p class='note' style='margin:14px 0 0'>"
            "Deleting removes the record from episodic recall; "
            "accumulated entity facts are unaffected.</p></div>"
        )
    else:
        episodic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Episodic runs</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('spark')}</div>"
            "No run records for this project yet. "
            "Complete a research task to populate episodic memory.</div></div>"
        )

    # ── Semantic facts card (right, 1fr) — live heads as a scannable stack ──
    if semantic_facts:
        def _fact_inline(f) -> str:
            label = escape(f.source_label) if getattr(f, "source_label", "") else ""
            src = f" <span class='muted' style='font-size:11.5px'>· {label}</span>" if label else ""
            return (
                "<div class='inline'>"
                "<span class='badge ok'>live</span>"
                + _source_badge(f) +
                "<span style='font-size:13px'>"
                f"<b>{escape(f.entity)}</b> — {escape(f.content)}{src}</span>"
                "</div>"
            )
        sem_rows = "<div class='divider'></div>".join(
            _fact_inline(f) for f in semantic_facts
        )
        semantic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Semantic facts</h2>"
            "<span class='pill'>live heads</span></div>"
            f"<div class='stack'>{sem_rows}</div></div>"
        )
    else:
        semantic_card = (
            "<div class='card'>"
            "<div class='card-head'><h2>Semantic facts</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('brain')}</div>"
            "No entity facts accumulated yet.</div></div>"
        )

    entity_slug = normalize_entity(project.name)
    sources_html, sources_js = _memory_sources_form(entity_slug)

    right_col = semantic_card + sources_html
    content = (
        banner
        + "<div class='split' style='align-items:start'>"
        + episodic_card
        + f"<div class='stack'>{right_col}</div>"
        + "</div>"
    )
    return shell(
        active="projects", title=f"{project.name} · Memory", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "memory", project.name),
        body_scripts=sources_js,
    )
