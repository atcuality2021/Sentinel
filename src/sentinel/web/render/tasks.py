"""render.tasks — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .base import _icon, _project_subnav, shell
from .personas import _task_form

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
