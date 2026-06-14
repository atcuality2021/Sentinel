"""render.kb — split from render.py (presentation only)."""

from __future__ import annotations
from html import escape
from sentinel.kb.url_guard import safe_href

from .base import _icon, _project_subnav, shell

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
