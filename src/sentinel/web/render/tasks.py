"""render.tasks — split from render.py (presentation only)."""

from __future__ import annotations
import json
from html import escape

from .base import _icon, _project_subnav, shell
from .personas import _task_form

def _task_status_badge(status: str, degraded: bool = False) -> str:
    """Colour-coded status badge. Degraded done→partial (amber).

    Uses the new design-system `.badge.ok|warn|bad|neutral` classes. The literal
    status labels (``created``/``done``/``failed``…) and the legacy colour hex
    hooks (``5bd07f`` for done, ``ff6b6b`` for failed) are preserved so existing
    assertions and any colour-sniffing keep working.
    """
    if status == "done" and degraded:
        return "<span class='badge warn'>partial</span>"
    _map = {
        "created":  ("neutral", "created", ""),
        "planned":  ("neutral", "planned", ""),
        "running":  ("warn",    "running…", ""),
        "done":     ("ok",      "done", "#5bd07f"),
        "failed":   ("bad",     "failed", "#ff6b6b"),
        "rejected": ("bad",     "rejected", ""),
    }
    cls, label, hex_hook = _map.get(status, ("neutral", status, ""))
    style = f" style='--st:{hex_hook}'" if hex_hook else ""
    return f"<span class='badge {cls}'{style}>{escape(label)}</span>"


# Optional steering prompt that rides a re-run: lands in task.context → _plan_seeds →
# every agent's vertical_context. Compact inline input so the task rows stay one-line.
_RERUN_CTX = (
    "<input class='input' name='context' placeholder='guidance for better results (optional)' "
    "style='font-size:11px;padding:2px 6px;height:24px;width:210px;width:auto;"
    "vertical-align:middle;margin-right:4px'>"
)

_RERUN_SEL = (
    "<select class='input' name='backend' style='font-size:11px;padding:2px 4px;height:24px;"
    "width:auto;vertical-align:middle'>"
    "<option value=''>auto</option>"
    "<option value='gemini'>☁ Gemini</option>"
    "<option value='vllm'>🔒 vLLM 12B</option>"
    "<option value='vllm-26b'>🔒 vLLM 26B</option>"
    "</select>"
)


def _task_row(task, pid: str, show_full_obj: bool = False) -> str:
    """Task table row: objective link, domain, status, action buttons.

    Emits a ``<tr>`` for the new `.table` markup; the page wraps these in
    ``<table class='table'>``.
    """
    tid = escape(task.id)
    obj = task.objective or ""
    display_obj = obj if show_full_obj else (obj[:110] + "…" if len(obj) > 110 else obj)
    status = task.status
    has_result = bool(getattr(task, "result", None))
    degraded = has_result and getattr(task.result, "degraded", False) if has_result else False

    domain = escape(task.domain.name)
    badge = _task_status_badge(status, degraded)

    # artifact count chip (folded next to the badge)
    art_chip = ""
    if has_result:
        arts = getattr(task.result, "artifacts", []) or []
        if arts:
            cls = "warn" if degraded else "ok"
            label = (
                f"{len(arts)} artifact{'s' if len(arts) != 1 else ''} produced"
                if degraded else
                f"{len(arts)} artifact{'s' if len(arts) != 1 else ''}"
            )
            art_chip = f"<span class='badge {cls}'>{label}</span>"

    # action buttons
    view_btn = (
        f"<a class='btn sm ok' href='/projects/{pid}/tasks/{tid}'>"
        f"{_icon('doc')} View</a>"
        if has_result else
        f"<a class='btn sm ghost' href='/projects/{pid}/tasks/{tid}'>"
        f"{_icon('doc')} Details</a>"
    )
    retry_btn = ""
    if status in ("failed", "done"):
        retry_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn sm warn' type='submit' title='Re-run this task' style='margin-left:4px'>"
            f"{_icon('bolt')} Re-run</button></form>"
        )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn sm danger' type='submit'>Delete</button></form>"
    )

    return (
        f"<tr>"
        f"<td><a href='/projects/{pid}/tasks/{tid}'><b>{escape(display_obj)}</b></a></td>"
        f"<td class='muted'>{domain}</td>"
        f"<td><span class='inline'>{badge}{art_chip}</span></td>"
        f"<td><span class='inline'>{view_btn}{retry_btn}{del_btn}</span></td>"
        f"</tr>"
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
        chips = "".join(f"<span class='pill'>{m}</span>" for m in metrics[:5])
        metrics_html = f"<div class='inline' style='margin-top:8px'>{chips}</div>"

    summary_html = (
        f"<p class='muted' style='margin:8px 0 0;font-size:13px;line-height:1.5'>{summary}</p>"
        if summary else ""
    )

    rerun_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/run' style='display:inline'>"
        f"{_RERUN_CTX}{_RERUN_SEL}"
        f"<button class='btn sm ghost' type='submit' title='Run this task again' style='margin-left:4px'>"
        f"{_icon('bolt')} Re-run</button></form>"
    )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline;margin-left:4px'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn sm danger' type='submit'>Delete</button></form>"
    )
    return (
        f"<div class='card pad-sm' style='margin-bottom:10px'>"
        f"<div class='row-between' style='align-items:flex-start'>"
        f"<div style='flex:1;min-width:0'>"
        f"<a href='/projects/{pid}/tasks/{tid}' style='font-weight:600;font-size:14px;"
        f"line-height:1.4'>{obj}</a>"
        f"<div class='inline' style='margin-top:6px'>"
        f"<span class='pill'>{escape(domain)}</span>"
        f"<span class='badge ok'>done</span>"
        f"</div>"
        f"{summary_html}"
        f"{metrics_html}"
        f"</div>"
        f"<div class='stack' style='flex-shrink:0;align-items:flex-end'>"
        f"<a class='btn sm ok' href='/projects/{pid}/tasks/{tid}'>{_icon('doc')} View</a>"
        f"<div class='inline'>{rerun_btn}{del_btn}</div>"
        f"</div>"
        f"</div></div>"
    )


def _pending_task_row(task, pid: str) -> str:
    """Compact table row for a task that hasn't produced a result yet."""
    tid = escape(task.id)
    obj = escape(task.objective or "")
    domain = task.domain.name if task.domain else ""
    status = task.status
    badge = _task_status_badge(status, False)
    run_btn = ""
    if status in ("planned", "created"):
        run_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn sm' type='submit' style='margin-left:4px'>{_icon('bolt')} Run</button></form>"
        )
    elif status == "failed":
        run_btn = (
            f"<form method='post' action='/projects/run-plan' style='display:inline'>"
            f"<input type='hidden' name='task_id' value='{tid}'>"
            f"{_RERUN_CTX}{_RERUN_SEL}"
            f"<button class='btn sm warn' type='submit' style='margin-left:4px'>{_icon('bolt')} Retry</button></form>"
        )
    del_btn = (
        f"<form method='post' action='/projects/{pid}/tasks/{tid}/delete' style='display:inline;margin-left:6px'"
        f" onsubmit='return confirm(\"Delete this task and all its data?\")'>"
        f"<button class='btn sm danger' type='submit'>Delete</button></form>"
    )
    return (
        f"<tr>"
        f"<td><a href='/projects/{pid}/tasks/{tid}'><b>{obj}</b></a></td>"
        f"<td class='muted'>{escape(domain)}</td>"
        f"<td>{badge}</td>"
        f"<td><span class='inline'>{run_btn}{del_btn}</span></td>"
        f"</tr>"
    )


def project_detail_page(*, project, tasks: list, backend: str,
                        vllm_model: str = "gemma-4-12b-it", sovereign: bool = False,
                        ok: str = "", err: str = "",
                        kb_source_count: int = 0) -> str:
    """Overview tab — project CRUD, context, quick-add source, built/building tasks."""
    pid = escape(project.id)
    site = (f"<a href='{escape(project.website)}' rel='noopener' target='_blank'>"
            f"{escape(project.website)}</a>") if project.website else "—"

    done_tasks  = [t for t in tasks if t.status == "done"]
    pending     = [t for t in tasks if t.status not in ("done",)]
    fail_count  = sum(1 for t in tasks if t.status == "failed")
    running     = sum(1 for t in tasks if t.status == "running")
    planned     = sum(1 for t in tasks if t.status in ("planned", "created"))

    flash = ""
    if ok:
        flash = f"<div class='card pad-sm' style='margin-bottom:12px;border-color:var(--ok)'>{escape(ok)}</div>"
    elif err:
        flash = f"<div class='card pad-sm' style='margin-bottom:12px;border-color:var(--bad)'>{escape(err)}</div>"

    # ── Edit project form (toggled by button, hidden by default) ──────────────
    _proj_desc = escape(getattr(project, "description", "") or "")
    _proj_ctx  = escape(getattr(project, "context", "") or "")
    _proj_site = escape(project.website or "")
    edit_form = (
        f"<div id='proj-edit-panel' style='display:none;margin-top:12px'>"
        f"<form method='post' action='/projects/{pid}/edit' style='max-width:600px'>"
        f"<div class='field'><label>Project name</label>"
        f"<input class='input' name='name' value='{escape(project.name)}'></div>"
        f"<div class='field'><label>Website / primary source URL</label>"
        f"<input class='input' name='website' value='{_proj_site}' "
        f"placeholder='https://example.com'></div>"
        f"<div class='field'><label>Description</label>"
        f"<input class='input' name='description' value='{_proj_desc}' "
        f"placeholder='What is this project researching?'></div>"
        f"<div class='field'><label>Agent context "
        f"<span class='hint'>— prepended to every research task in this project</span></label>"
        f"<textarea name='context' rows='3' "
        f"placeholder='e.g. Focus on the Indian market. Prioritise recent data from 2024-2025. "
        f"This research is for an enterprise pitch deck.'>"
        f"{_proj_ctx}</textarea></div>"
        f"<div class='inline'>"
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
    proj_desc = getattr(project, "description", "") or ""
    head_sub = escape(proj_desc) if proj_desc else (
        f"{escape(project.website)}" if project.website else "Research project"
    )

    proj_ctx = getattr(project, "context", "") or ""
    ctx_pill = (
        f"<span class='pill' title='{escape(proj_ctx[:200])}'>📋 Agent context set</span>"
    ) if proj_ctx else ""

    header = (
        f"{flash}"
        f"<div class='page-head'>"
        f"<div class='grow'><h1>{escape(project.name)}</h1><p>{head_sub}</p></div>"
        f"{ctx_pill}"
        f"<button id='proj-edit-btn' type='button' class='btn ghost' onclick='_toggleEdit()'>"
        f"✏ Edit</button>"
        f"<a class='btn' href='/projects/{pid}/tasks'>{_icon('bolt')} New Research Task</a>"
        f"</div>"
        f"{edit_form}"
    )

    # ── KPI cards ──────────────────────────────────────────────────────────────
    fail_delta = f" · {fail_count} failed" if fail_count else ""
    kpis = (
        "<div class='grid cols-3' style='margin-bottom:24px'>"
        f"<div class='card kpi'><div class='value'>{len(tasks)}</div>"
        f"<div class='label'>Tasks</div>"
        f"<div class='delta'>{len(done_tasks)} done · {running} running · {planned} planned{fail_delta}</div></div>"
        f"<div class='card kpi'><div class='value'>{kb_source_count}</div>"
        f"<div class='label'>KB sources</div>"
        f"<div class='delta{' up' if kb_source_count else ''}'>"
        f"{'indexed' if kb_source_count else 'none yet'}</div></div>"
        f"<a class='card kpi' href='/projects/{pid}/report' style='text-decoration:none'>"
        f"<div class='value'>{len(done_tasks)}</div>"
        f"<div class='label'>Deliverables</div>"
        f"<div class='delta'>view full report</div></a>"
        "</div>"
    )

    # ── Quick-add source (compact inline form) ────────────────────────────────
    quick_source = (
        f"<div class='card'>"
        f"<div class='card-head'><h2>Add sources for the agent to use</h2></div>"
        f"<div class='grid cols-2'>"

        # ── Left: URL input (type auto-inferred server-side) ──
        f"<div class='field'>"
        f"<label>🔗 Paste a URL</label>"
        f"<form method='post' action='/projects/{pid}/kb/sources' class='inline'>"
        f"<input type='hidden' name='redirect' value='overview'>"
        f"<input class='input' name='url' placeholder='Website, article, or PDF link…' style='flex:1;min-width:0'>"
        f"<button class='btn' type='submit'>{_icon('bolt')} Add</button>"
        f"</form>"
        f"<span class='hint'>Type is detected automatically — web, PDF, or social</span>"
        f"</div>"

        # ── Right: File upload (multiple files) ──
        f"<div class='field'>"
        f"<label>📄 Upload files <span class='hint'>&nbsp;·&nbsp;PDF, TXT, MD</span></label>"
        f"<form method='post' action='/projects/{pid}/kb/upload' enctype='multipart/form-data' class='inline'>"
        f"<input type='hidden' name='redirect' value='overview'>"
        f"<input class='input' type='file' name='files' multiple accept='.pdf,.txt,.md' "
        f"style='flex:1;min-width:0'>"
        f"<button class='btn' type='submit'>{_icon('bolt')} Upload</button>"
        f"</form>"
        f"<span class='hint'>Select one or more files to index into the Knowledge Base</span>"
        f"</div>"

        f"</div>"
        f"<p class='muted' style='margin:10px 0 0;font-size:13px'>Need to chat with your sources? "
        f"<a href='/projects/{pid}/kb'>Open the full Knowledge Base</a></p>"
        f"</div>"
    )

    # ── Split: project context (right) is folded into the overview body ────────
    site_row = (
        f"<div class='row-between'><span class='muted'>Website</span><span>{site}</span></div>"
        if project.website else ""
    )
    context_card = (
        f"<div class='card'>"
        f"<div class='card-head'><h2>Project context</h2></div>"
        + (f"<p class='muted' style='font-size:13px;margin-top:0'>{escape(proj_desc)}</p>"
           if proj_desc else
           "<p class='muted' style='font-size:13px;margin-top:0'>No description yet.</p>")
        + "<div class='divider'></div>"
        f"<div class='stack'>"
        f"{site_row}"
        f"<div class='row-between'><span class='muted'>Completed</span>"
        f"<span class='badge ok'>{len(done_tasks)}</span></div>"
        f"<div class='row-between'><span class='muted'>In progress / planned</span>"
        f"<span class='badge neutral'>{len(pending)}</span></div>"
        + (f"<div class='row-between'><span class='muted'>Failed</span>"
           f"<span class='badge bad'>{fail_count}</span></div>" if fail_count else "")
        + (f"<div class='row-between'><span class='muted'>Agent context</span>"
           f"<span class='badge ok'>set</span></div>" if proj_ctx else "")
        + "</div></div>"
    )

    # ── What has been built (completed tasks with actual findings) ─────────────
    if done_tasks:
        brief_cards = "".join(_result_brief_card(t, pid) for t in done_tasks)
        built_inner = (
            f"<div class='card-head'><h2>What we have built</h2>"
            f"<a class='btn sm ghost' href='/projects/{pid}/artifacts'>All artifacts</a></div>"
            + brief_cards
        )
    else:
        built_inner = (
            "<div class='card-head'><h2>What we have built</h2></div>"
            "<p class='muted' style='font-size:13px;margin-top:0'>No completed deliverables yet.</p>"
        )
    built_card = f"<div class='card'>{built_inner}</div>"

    overview_split = (
        f"<div class='split' style='align-items:start;margin-top:24px'>"
        f"{built_card}{context_card}</div>"
    )

    # ── What we are building (pending / in-progress tasks) ────────────────────
    if pending:
        p_rows = "".join(_pending_task_row(t, pid) for t in pending)
        building_html = (
            "<div class='card' style='margin-top:24px'>"
            "<div class='card-head'><h2>What we are building</h2>"
            f"<a class='btn sm ghost' href='/projects/{pid}/tasks'>Manage</a></div>"
            f"<div class='table-wrap'><table class='table'>"
            "<thead><tr><th>Objective</th><th>Domain</th><th>Status</th><th></th></tr></thead>"
            f"<tbody>{p_rows}</tbody></table></div>"
            "</div>"
        )
    else:
        building_html = ""

    # ── Empty state ────────────────────────────────────────────────────────────
    if not tasks:
        building_html = (
            "<div class='card' style='margin-top:24px'>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('search')}</div>"
            "<div style='font-weight:600;margin-bottom:8px'>No research tasks yet</div>"
            "<p style='max-width:400px;margin:0 auto 16px'>Add your first research task — "
            "define what you want to investigate, choose a domain, and the agent pipeline does the rest.</p>"
            f"<a class='btn' href='/projects/{pid}/tasks'>{_icon('bolt')} Create first task</a>"
            "</div></div>"
        )

    # ── Quick-links row ────────────────────────────────────────────────────────
    _kb_count_label = (
        f"{kb_source_count} source{'s' if kb_source_count != 1 else ''} indexed"
        if kb_source_count else "No sources yet"
    )
    quicklinks = (
        "<div class='grid cols-3' style='margin-top:24px'>"
        f"<a class='card' href='/projects/{pid}/kb' style='text-align:center;text-decoration:none'>"
        f"<div style='color:var(--accent-text);margin-bottom:6px'>{_icon('book')}</div>"
        "<div style='font-weight:600;font-size:13px'>Knowledge Base</div>"
        f"<p class='muted' style='margin:4px 0 0;font-size:12px'>{_kb_count_label}</p></a>"
        f"<a class='card' href='/projects/{pid}/memory' style='text-align:center;text-decoration:none'>"
        f"<div style='color:var(--accent-text);margin-bottom:6px'>{_icon('brain')}</div>"
        "<div style='font-weight:600;font-size:13px'>Memory</div>"
        "<p class='muted' style='margin:4px 0 0;font-size:12px'>Facts &amp; episodic records</p></a>"
        f"<a class='card' href='/projects/{pid}/report' style='text-align:center;text-decoration:none'>"
        f"<div style='color:var(--accent-text);margin-bottom:6px'>{_icon('doc')}</div>"
        "<div style='font-weight:600;font-size:13px'>Report</div>"
        "<p class='muted' style='margin:4px 0 0;font-size:12px'>Full compiled report</p></a>"
        "</div>"
    )

    # ── Danger zone ────────────────────────────────────────────────────────────
    danger_zone = (
        "<div class='card' style='margin-top:32px;border-color:var(--bad)'>"
        "<div class='card-head'>"
        "<h2 style='color:var(--bad);font-size:13px;text-transform:uppercase;"
        "letter-spacing:.1em'>⚠ Danger Zone</h2></div>"
        "<div class='row-between' style='flex-wrap:wrap'>"
        "<div>"
        "<div style='font-weight:650;font-size:14px;margin-bottom:6px'>Delete this project</div>"
        "<p class='muted' style='margin:0;max-width:520px;font-size:13px'>Permanently removes the project, "
        "all its tasks, plans, and KB sources. "
        "Episodic memory run records are kept.</p>"
        "</div>"
        f"<form method='post' action='/projects/{pid}/delete' "
        f"onsubmit='return confirm(\"Delete project \" + {escape(json.dumps(project.name), quote=True)} + \"? All tasks and data will be permanently removed.\")'>"
        "<button class='btn danger' type='submit'>"
        f"{_icon('shield')} Delete project</button></form>"
        "</div></div>"
    )

    content = (header + kpis + quick_source + overview_split
               + building_html + quicklinks + danger_zone)
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

    head_sub = (
        escape(getattr(project, "description", "") or "")
        or (escape(project.website) if project.website else "Research tasks")
    )
    page_head = (
        f"<div class='page-head'>"
        f"<div class='grow'><h1>{escape(project.name)}</h1><p>{head_sub}</p></div>"
        f"<a class='btn ghost' href='/projects/{pid}'>Overview</a>"
        f"</div>"
    )

    # When tasks already exist, collapse the form behind a toggle button so the
    # task list is immediately visible on load.
    if tasks:
        form_block = (
            "<div style='margin-bottom:24px'>"
            "<button type='button' class='btn ghost' "
            "onclick=\"var p=document.getElementById('new-task-panel');"
            "p.style.display=p.style.display==='none'?'block':'none'\">"
            "＋ New research task</button>"
            "<div id='new-task-panel' style='display:none;margin-top:12px'>"
            f"{form_html}</div></div>"
        )
    else:
        form_block = form_html + "<div style='margin-top:24px'></div>"

    if tasks:
        rows = "".join(_task_row(t, pid, show_full_obj=True) for t in tasks)
        failed_note = (
            f"<span class='badge bad'>{failed_count} failed</span>"
        ) if failed_count else ""
        tasks_html = (
            "<div class='card'>"
            f"<div class='card-head'><h2>Tasks</h2>"
            f"<span class='pill'>{len(tasks)}</span>{failed_note}</div>"
            f"<div class='table-wrap'><table class='table'>"
            "<thead><tr><th>Objective</th><th>Domain</th><th>Status</th><th></th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
            "</div>"
        )
    else:
        tasks_html = (
            "<div class='card'>"
            "<div class='card-head'><h2>Tasks</h2></div>"
            "<div class='empty'>"
            f"<div class='ico'>{_icon('search')}</div>"
            "No tasks yet — create one above.</div>"
            "</div>"
        )
    content = page_head + form_block + tasks_html
    return shell(
        active="projects", title=f"{project.name} · Research", content=content,
        backend=backend, project=project.name,
        subnav=_project_subnav(project.id, "tasks", project.name),
    )
