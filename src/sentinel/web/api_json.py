"""JSON REST API — thin adapter over the same stores the HTML routes use.

All routes are included in app.py under the /api prefix (app.include_router(router, prefix="/api")).
No business logic lives here: every handler delegates to stores or services.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

from sentinel.artifacts.schemas import Project, SavedPersona
from sentinel.config import get_config, set_config
from sentinel.kb import KBManager, KBSource, SourceType
from sentinel.kb.url_guard import validate_crawl_url
from sentinel.memory import RunStore
from sentinel.memory.schema import utcnow
from sentinel.memory.store import KBStore, PersonaStore, ProjectStore, SpecStore
from sentinel.web import settings as _settings

router = APIRouter()


def _kb_data_dir() -> str:
    return os.path.join(
        os.getenv("SENTINEL_DATA_DIR", os.path.expanduser("~/.sentinel")), "kb"
    )


# ── Dashboard ──────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def api_dashboard() -> JSONResponse:
    try:
        records = RunStore().list(20)
    except Exception:
        records = []
    return JSONResponse({
        "total_runs": len(records),
        "total_artifacts": len(records),
        "total_public_findings": sum(r.public for r in records),
        "total_private_findings": sum(r.private for r in records),
        "recent_runs": [
            {
                "id": r.id, "entity": r.entity, "target": r.target,
                "mode": r.mode, "backend": r.backend,
                "public": r.public, "private": r.private, "gaps": r.gaps,
                "project_id": r.project_id,
                "task_id": r.task_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in records[:10]
        ],
        "focus": [],
    })


# ── Projects ───────────────────────────────────────────────────────────────────
@router.get("/projects")
async def api_list_projects() -> JSONResponse:
    try:
        items = ProjectStore().list_projects()
    except Exception:
        items = []
    return JSONResponse([_proj_dict(p) for p in items])


@router.post("/projects")
async def api_create_project(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)

    store = ProjectStore()
    existing = store.get_project_by_name(name)
    if existing:
        return JSONResponse(_proj_dict(existing))

    proj = Project(
        id=uuid4().hex, name=name,
        website=(body.get("website") or "").strip() or None,
        description=(body.get("description") or "").strip(),
        context=(body.get("context") or "").strip(),
        created_at=utcnow().isoformat(),
    )
    try:
        store.save_project(proj)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    if proj.website:
        try:
            crawl_url = validate_crawl_url(proj.website)
            source = KBSource(project_id=proj.id, url=crawl_url, source_type=SourceType.WEB)
            KBStore().save({
                "id": source.id, "project_id": source.project_id, "url": source.url,
                "source_type": source.source_type.value, "status": "pending",
                "chunk_count": 0, "error": None,
            })

            async def _crawl(src_id: str, pid: str, u: str) -> None:
                result = await KBManager(_kb_data_dir()).add_source(pid, u, SourceType.WEB)
                KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

            background_tasks.add_task(_crawl, source.id, proj.id, crawl_url)
        except Exception:
            pass

    return JSONResponse(_proj_dict(proj), status_code=201)


@router.get("/projects/{project_id}")
async def api_get_project(project_id: str) -> JSONResponse:
    try:
        proj = ProjectStore().get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_proj_dict(proj))


@router.post("/projects/{project_id}/edit")
async def api_edit_project(project_id: str, request: Request) -> JSONResponse:
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return JSONResponse({"error": "not found"}, status_code=404)

    if body.get("name", "").strip():
        proj.name = body["name"].strip()
    if "website" in body:
        proj.website = body["website"].strip() or None
    if "description" in body:
        proj.description = body["description"].strip()
    if "context" in body:
        proj.context = body["context"].strip()
    store.save_project(proj)
    return JSONResponse(_proj_dict(proj))


@router.post("/projects/{project_id}/delete")
async def api_delete_project(project_id: str) -> JSONResponse:
    try:
        ProjectStore().delete_project(project_id)
    except Exception:
        pass
    return JSONResponse({"ok": True})


# ── Tasks ──────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/tasks")
async def api_list_tasks(project_id: str) -> JSONResponse:
    try:
        items = ProjectStore().tasks_for_project(project_id)
    except Exception:
        items = []
    return JSONResponse([_task_dict(t) for t in items])


@router.get("/projects/{project_id}/tasks/{task_id}")
async def api_get_task(project_id: str, task_id: str) -> JSONResponse:
    try:
        task = ProjectStore().get_task(task_id)
    except Exception:
        task = None
    if task is None or task.project_id != project_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_task_dict(task))


@router.get("/projects/{project_id}/tasks/{task_id}/plan")
async def api_get_task_plan(project_id: str, task_id: str) -> JSONResponse:
    """Return the plan DAG for a task: steps with depends_on, agent assignment, call kind, sub-steps.

    Used by the frontend PipelinePanel to render the Flow graph + Step table + timeline."""
    try:
        store = ProjectStore()
        task = store.get_task(task_id)
    except Exception:
        task = None
    if task is None or task.project_id != project_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    plan = store.plan_for_task(task_id)
    if plan is None:
        return JSONResponse({"steps": []})

    try:
        from sentinel.agent.modes.spec import SKILL_SPECS
    except Exception:
        SKILL_SPECS = {}

    _SUBSTEP_LABELS: dict[str, str] = {
        "planner":         "Planned search strategy — broke goal into targeted questions",
        "public_research": "Searched web — gathered public findings",
        "ecom_prices":     "Searched ecommerce — compared live prices across Flipkart & Amazon",
        "research":        "Searched web — gathered public findings",
        "synthesizer":     "Synthesised — assembled final structured output from all findings",
        "extractor":       "Extracted facts — structured raw search results into typed data",
        "dept_research":   "Researched department/sector — mapped capabilities to requirements",
        "synthesis":       "Synthesised proposal — compiled department findings into final plan",
        "competitor":      "Researched competitor — web search for profile, products, pricing",
        "compare":         "Compared entities — side-by-side analysis of gathered profiles",
        "self_profile":    "Profiled organisation — gathered public identity and product data",
        "client":          "Profiled client/account — gathered contact, deal, and context data",
    }

    steps_out = []
    for s in plan.steps:
        spec = SKILL_SPECS.get(s.capability)
        if spec is None:
            calls = "reasoner"
        else:
            tools = {st.tool for st in spec.steps}
            if "private" in tools:
                calls = "MCP · private"
            elif "search" in tools:
                calls = "web search · public"
            else:
                calls = "reasoner"

        sub_steps = []
        if spec:
            for ss in spec.steps:
                sub_key = ss.agent_key.split(".")[-1] if "." in ss.agent_key else ss.agent_key
                sub_steps.append({
                    "key": sub_key,
                    "label": _SUBSTEP_LABELS.get(sub_key, f"{sub_key} step"),
                })

        steps_out.append({
            "id": s.id,
            "capability": s.capability,
            "depends_on": s.depends_on,
            "agent_spec_id": s.agent_spec_id or "—",
            "is_new": not (s.agent_spec_id or "").startswith("seed-"),
            "calls": calls,
            "status": s.status,
            "sub_steps": sub_steps,
        })

    return JSONResponse({"steps": steps_out})


@router.post("/projects/{project_id}/tasks")
async def api_create_task(
    project_id: str, request: Request, background_tasks: BackgroundTasks
) -> JSONResponse:
    """Create a task, generate its plan, and run it in the background. Returns {task_id} immediately."""
    from sentinel.web.app import _approve_and_run, _persona_for, _cloud_allowed_for
    from sentinel.agent.registry import AgentRegistry
    from sentinel.agent.orchestrator_planner import plan_task
    from sentinel.artifacts.schemas import Task, Domain
    from sentinel.memory.schema import utcnow as _now

    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    objective = (body.get("objective") or "").strip()
    if not objective:
        return JSONResponse({"error": "objective is required"}, status_code=400)

    store = ProjectStore()
    proj = store.get_project(project_id)
    if proj is None:
        return JSONResponse({"error": "project not found"}, status_code=404)

    domain = (body.get("domain") or "market").strip()
    persona_name = (body.get("persona") or "auto").strip()
    context = (body.get("context") or "").strip()
    override_backend = (body.get("backend") or "").strip()

    task_persona = _persona_for(persona_name, domain=domain)

    # Reuse existing task with same objective+domain to avoid duplicates on re-plan
    existing = next(
        (t for t in store.tasks_for_project(project_id)
         if t.objective == objective
         and (t.domain.name if hasattr(t.domain, "name") else str(t.domain)) == domain),
        None,
    )
    if existing:
        task = existing
        task.persona = task_persona
        if context:
            task.context = context
    else:
        now = _now().isoformat()
        task = Task(
            id=f"task-{now}", project_id=project_id,
            objective=objective, domain=Domain(name=domain),
            persona=task_persona, created_at=now,
            context=context or None,
        )
    store.save_task(task)
    task_id = task.id

    async def _plan_and_run() -> None:
        from sentinel.llm.gateway import _is_vllm_error
        _store = ProjectStore()
        _task = _store.get_task(task_id)
        _proj = _store.get_project(project_id)
        if _task is None or _proj is None:
            return
        _cfg = get_config()
        _fallback = _cfg.backend.fallback  # "gemini" | "claude" | None
        _run_backend = override_backend  # may be "" meaning "use config default"

        _proj_ctx = (getattr(_proj, "context", None) or getattr(_proj, "description", None) or "").strip() or None
        try:
            proposal = await plan_task(_task, AgentRegistry(),
                                       cloud_allowed=_cloud_allowed_for(_proj),
                                       project_context=_proj_ctx)
        except Exception as exc:
            if _is_vllm_error(exc) and _fallback:
                # vLLM is down — retry planning on the fallback backend
                try:
                    proposal = await plan_task(_task, AgentRegistry(),
                                               backend=_fallback, cloud_allowed=True,
                                               project_context=_proj_ctx)
                    _run_backend = _fallback  # carry fallback through to execution
                except Exception as exc2:
                    _task.status = "failed"
                    _task.fail_reason = f"vLLM down; fallback also failed — {type(exc2).__name__}: {str(exc2)[:200]}"
                    try:
                        _store.save_task(_task)
                    except Exception:
                        pass
                    return
            else:
                _task.status = "failed"
                _task.fail_reason = f"{type(exc).__name__}: {str(exc)[:300]}"
                try:
                    _store.save_task(_task)
                except Exception:
                    pass
                return

        _task.status = "planned"
        _task.plan_id = proposal.plan.id
        _store.save_task(_task)
        _store.save_plan(proposal.plan)
        # _approve_and_run with background_tasks=None runs _execute_run inline
        await _approve_and_run(
            task_id,
            override_backend=_run_backend,
            extra_context="",
            background_tasks=None,
        )

    background_tasks.add_task(_plan_and_run)
    return JSONResponse({"task_id": task_id, "status": "created"}, status_code=201)


@router.post("/projects/{project_id}/kb/sources/{source_id}/retry")
async def api_retry_kb_source(
    project_id: str, source_id: str, background_tasks: BackgroundTasks
) -> JSONResponse:
    src = KBStore().get(source_id)
    if not src or src.get("project_id") != project_id:
        return JSONResponse({"error": "source not found"}, status_code=404)
    if src.get("url", "").startswith("artifact://"):
        return JSONResponse({"error": "artifact sources cannot be re-crawled"}, status_code=400)
    KBStore().update_status(source_id, "pending", 0, None)

    async def _crawl(src_id: str, pid: str, url: str, stype: str) -> None:
        result = await KBManager(_kb_data_dir()).add_source(pid, url, SourceType(stype))
        KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

    background_tasks.add_task(_crawl, source_id, project_id,
                               src["url"], src.get("source_type", "web"))
    return JSONResponse({"ok": True, "status": "pending"})


@router.post("/projects/{project_id}/tasks/{task_id}/run")
async def api_run_task(
    project_id: str, task_id: str, request: Request, background_tasks: BackgroundTasks
) -> JSONResponse:
    """Re-plan + run a task (same pipeline as task creation — always generates a fresh plan)."""
    from sentinel.web.app import _ACTIVE_RUNS, _approve_and_run

    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if task.project_id != project_id:
        return JSONResponse({"error": "not found"}, status_code=404)
    if _ACTIVE_RUNS.get(task_id, {}).get("state") == "running":
        return JSONResponse({"ok": True, "task_id": task_id, "already_running": True})

    try:
        body: dict = await request.json()
    except Exception:
        body = {}
    override_backend = (body.get("backend") or "").strip()

    async def _replan_and_run() -> None:
        from sentinel.llm.gateway import _is_vllm_error
        from sentinel.web.app import _approve_and_run, _cloud_allowed_for, _ACTIVE_RUNS
        from sentinel.agent.registry import AgentRegistry
        from sentinel.agent.orchestrator_planner import plan_task
        _store = ProjectStore()
        _task = _store.get_task(task_id)
        _proj = _store.get_project(project_id)
        if _task is None or _proj is None:
            return
        _run_backend = override_backend
        _proj_ctx = (getattr(_proj, "context", None) or getattr(_proj, "description", None) or "").strip() or None

        # Show a "planning" sentinel in _ACTIVE_RUNS so status.json always returns
        # something (steps=[]) and the frontend shows the warming-up skeleton instead
        # of the old plan's stale clock icons during the re-plan LLM call.
        _ACTIVE_RUNS[task_id] = {"plan": type("_FakePlan", (), {"steps": []})(),
                                 "state": "planning", "error": None}

        try:
            proposal = await plan_task(_task, AgentRegistry(),
                                       cloud_allowed=_cloud_allowed_for(_proj),
                                       project_context=_proj_ctx)
        except Exception as exc:
            cfg = get_config()
            _fallback = cfg.backend.fallback
            if _is_vllm_error(exc) and _fallback:
                try:
                    proposal = await plan_task(_task, AgentRegistry(),
                                               backend=_fallback, cloud_allowed=True,
                                               project_context=_proj_ctx)
                    _run_backend = _fallback
                except Exception as exc2:
                    _task.status = "failed"
                    _task.fail_reason = f"Re-plan failed — vLLM down; fallback also failed: {str(exc2)[:200]}"
                    _store.save_task(_task)
                    _ACTIVE_RUNS.pop(task_id, None)
                    return
            else:
                _task.status = "failed"
                _task.fail_reason = f"Re-plan failed: {type(exc).__name__}: {str(exc)[:300]}"
                _store.save_task(_task)
                _ACTIVE_RUNS.pop(task_id, None)
                return

        # Clear stale fail_reason from any previous run before saving
        _task.fail_reason = None
        _task.status = "planned"
        _task.plan_id = proposal.plan.id
        _store.save_task(_task)
        _store.save_plan(proposal.plan)
        # Pop the planning sentinel — _approve_and_run will set a proper "running" entry
        _ACTIVE_RUNS.pop(task_id, None)
        await _approve_and_run(task_id, override_backend=_run_backend,
                               extra_context="", background_tasks=None)

    background_tasks.add_task(_replan_and_run)
    return JSONResponse({"ok": True, "task_id": task_id})


@router.post("/projects/{project_id}/tasks/{task_id}/chat")
async def api_task_chat(project_id: str, task_id: str, request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None or task.project_id != project_id:
        return JSONResponse({"error": "not found"}, status_code=404)

    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    # Append to chat history and persist
    task.chat.append({"role": "user", "content": message})
    # Basic echo-back; the full streaming path lives in the HTML route (task_chat)
    reply = "Chat responses are available via the streaming endpoint at /projects/{id}/tasks/{taskId}/chat"
    task.chat.append({"role": "assistant", "content": reply})
    try:
        store.save_task(task)
    except Exception:
        pass
    return JSONResponse({"reply": reply, "chat": task.chat})


@router.post("/projects/{project_id}/tasks/{task_id}/feedback")
async def api_task_feedback(project_id: str, task_id: str, request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    signal = body.get("signal")
    if signal not in (1, -1):
        return JSONResponse({"error": "signal must be +1 or -1"}, status_code=400)

    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None or task.project_id != project_id:
        return JSONResponse({"error": "not found"}, status_code=404)

    try:
        from sentinel.memory.store import FeedbackStore
        FeedbackStore().save(
            project_id=project_id, task_id=task_id, run_id=task_id,
            entity=task.objective, signal=signal,
            note=(body.get("note") or "").strip() or None,
        )
    except Exception:
        pass
    return JSONResponse({"ok": True, "signal": signal})


@router.post("/projects/{project_id}/tasks/{task_id}/delete")
async def api_delete_task(project_id: str, task_id: str) -> JSONResponse:
    try:
        ProjectStore().delete_task(task_id)
    except Exception:
        pass
    return JSONResponse({"ok": True})


# ── Knowledge Base ─────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/kb")
async def api_get_kb(project_id: str) -> JSONResponse:
    try:
        sources = KBStore().list_for_project(project_id)
    except Exception:
        sources = []
    chunk_count = sum(s.get("chunk_count", 0) for s in sources)
    return JSONResponse({
        "sources": [
            {
                "id": s["id"], "url": s["url"], "source_type": s.get("source_type", "web"),
                "status": s.get("status", "pending"), "chunk_count": s.get("chunk_count", 0),
                "error": s.get("error"),
            }
            for s in sources
        ],
        "chunk_count": chunk_count,
    })


@router.post("/projects/{project_id}/kb/sources")
async def api_add_kb_source(
    project_id: str, request: Request, background_tasks: BackgroundTasks
) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    url = (body.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "url is required"}, status_code=400)

    try:
        crawl_url = validate_crawl_url(url)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    source = KBSource(project_id=project_id, url=crawl_url, source_type=SourceType.WEB)
    try:
        KBStore().save({
            "id": source.id, "project_id": source.project_id, "url": source.url,
            "source_type": source.source_type.value, "status": "pending",
            "chunk_count": 0, "error": None,
        })
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    async def _crawl(src_id: str, pid: str, u: str) -> None:
        result = await KBManager(_kb_data_dir()).add_source(pid, u, SourceType.WEB)
        KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

    background_tasks.add_task(_crawl, source.id, project_id, crawl_url)
    return JSONResponse({"id": source.id, "url": crawl_url, "status": "pending"}, status_code=201)


@router.get("/projects/{project_id}/kb/sources/{source_id}/chunks")
async def api_get_source_chunks(project_id: str, source_id: str) -> JSONResponse:
    try:
        from sentinel.kb.vector_store import get_chunks_by_source
        chunks = get_chunks_by_source(project_id, _kb_data_dir(), source_id)
        return JSONResponse(chunks)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/projects/{project_id}/kb/sources/{source_id}/delete")
async def api_delete_kb_source(project_id: str, source_id: str) -> JSONResponse:
    try:
        KBStore().delete(source_id, project_id)
    except Exception:
        pass
    return JSONResponse({"ok": True})


@router.get("/projects/{project_id}/kb/search")
async def api_kb_search(project_id: str, q: str = "") -> JSONResponse:
    if not q.strip():
        return JSONResponse([])
    try:
        from sentinel.kb.search import hybrid_search
        hits = hybrid_search(project_id, _kb_data_dir(), q.strip(), rerank_top_k=5)
        return JSONResponse([
            {"text": h.text, "source": h.url or h.title or "", "score": getattr(h, "score", 0.0)}
            for h in hits
        ])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/projects/{project_id}/kb/chat")
async def api_kb_chat(project_id: str, request: Request) -> JSONResponse:
    """Proxy to the existing HTML kb/chat handler which already accepts JSON."""
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return JSONResponse({"error": "project not found"}, status_code=404)

    try:
        from sentinel.kb.search import hybrid_search
        hits = hybrid_search(project_id, _kb_data_dir(), message, rerank_top_k=6)
        kb_context = "\n\n---\n\n".join(f"[{h.title or h.url}]\n{h.text}" for h in hits[:6])
    except Exception:
        kb_context = ""

    system = (
        f"You are a research assistant for the project '{proj.name}'. "
        "Answer questions using ONLY the knowledge base excerpts provided. "
        "Say 'not in the knowledge base' if the answer cannot be found.\n\n"
        + (f"KB excerpts:\n{kb_context}" if kb_context else "No KB content indexed yet.")
    )
    try:
        import litellm
        cfg = get_config()
        resp = await litellm.acompletion(
            model=f"gemini/{cfg.backend.gemini.model}",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": message}],
            max_tokens=1024, temperature=0.3, drop_params=True,
        )
        reply = resp.choices[0].message.content or ""
    except Exception as exc:
        reply = f"Could not generate answer: {exc}"
    return JSONResponse({"answer": reply, "sources_used": len(hits) if kb_context else 0})


# ── Memory ─────────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/memory")
async def api_get_memory(project_id: str) -> JSONResponse:
    try:
        episodes = RunStore().list(50, project_id=project_id)
    except Exception:
        episodes = []
    try:
        from sentinel.memory.store import MemoryStore
        facts = MemoryStore().list_semantic_facts(project_id)
    except Exception:
        facts = []
    return JSONResponse({
        "episodes": [
            {
                "id": r.id, "entity": r.entity, "target": r.target,
                "mode": r.mode, "backend": r.backend, "kind": r.kind,
                "public": r.public, "private": r.private, "gaps": r.gaps,
                "reference": r.reference,
                "finding_texts": r.finding_texts or [],
                "created_at": r.created_at.isoformat(),
            }
            for r in episodes
        ],
        "facts": [
            {
                "id": f.id, "entity": f.entity, "boundary": f.boundary,
                "content": f.content, "source_label": f.source_label,
                "strength": f.strength,
                "created_at": f.created_at.isoformat() if hasattr(f.created_at, "isoformat") else str(f.created_at),
            }
            for f in facts
        ],
    })


@router.post("/projects/{project_id}/memory/{run_id}/delete")
async def api_delete_memory_run(project_id: str, run_id: str) -> JSONResponse:
    try:
        from sentinel.memory.store import MemoryStore
        MemoryStore().delete_run(run_id)
    except Exception:
        pass
    return JSONResponse({"ok": True})


# ── Agents ─────────────────────────────────────────────────────────────────────
@router.get("/agents")
async def api_list_agents() -> JSONResponse:
    try:
        specs = SpecStore().list_specs()
    except Exception:
        specs = []
    return JSONResponse([
        {
            "id": s.id, "name": s.name, "capability": s.capability,
            "role": s.role if isinstance(s.role, str) else s.role.value,
            "model": None, "enabled": s.active,
            "eval_score": s.eval_score,
            "boundary": ",".join(b.value if hasattr(b, "value") else b for b in s.boundaries),
            "description": s.skill_prompt[:120] if s.skill_prompt else "",
            "capabilities": [s.capability],
            "tools": s.tools,
        }
        for s in specs
    ])


@router.post("/agents/{key}")
async def api_update_agent(key: str, request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    store = SpecStore()
    try:
        specs = store.list_specs()
        spec = next((s for s in specs if s.id == key), None)
    except Exception:
        spec = None
    if spec is None:
        return JSONResponse({"error": "not found"}, status_code=404)

    if "enabled" in body:
        spec.active = bool(body["enabled"])
    if "model" in body:
        pass  # model override not stored on AgentSpec; config-level change
    try:
        store.save_spec(spec)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True})


@router.post("/agents/{key}/delete")
async def api_delete_agent(key: str) -> JSONResponse:
    try:
        SpecStore().deactivate(key)
    except Exception:
        pass
    return JSONResponse({"ok": True})


# ── Personas ───────────────────────────────────────────────────────────────────
_BUILTIN_DEFAULTS = {
    "reading_level": "professional",
    "tone": "neutral",
    "format": "brief",
    "source_policy": "",
}

@router.get("/personas")
async def api_list_personas() -> JSONResponse:
    try:
        saved = PersonaStore().list()
    except Exception:
        saved = []

    # Merge saved overrides for built-ins so the frontend can show the effective profile
    try:
        from sentinel.artifacts.schemas import PERSONA_PROFILES
        saved_by_name = {p.name: p for p in saved}
        builtin_list = []
        for name, profile in PERSONA_PROFILES.items():
            override = saved_by_name.get(name)
            effective = {**_BUILTIN_DEFAULTS, **profile}
            builtin_list.append({
                "id": name,
                "name": name,
                "description": effective.get("description", ""),
                "reading_level": effective["reading_level"],
                "tone": effective["tone"],
                "format": effective["format"],
                "source_policy": effective.get("source_policy", ""),
                "built_in": True,
                "editable": name != "enterprise",
                # surface any override the user saved
                "has_override": override is not None,
            })
        # enterprise is always first
        builtin_list.sort(key=lambda b: (0 if b["name"] == "enterprise" else 1, b["name"]))
    except Exception:
        builtin_list = []

    # Custom saved personas (not matching a built-in name)
    custom = [_persona_dict(p) for p in saved if p.name not in PERSONA_PROFILES]
    return JSONResponse({"built_in": builtin_list, "custom": custom})


@router.post("/personas/create")
async def api_create_persona(request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)

    p = SavedPersona(
        id=uuid4().hex, name=name,
        description=(body.get("description") or "").strip(),
        reading_level=body.get("reading_level") or "professional",
        tone=body.get("tone") or "neutral",
        format=body.get("format") or "brief",
        source_policy=body.get("source_policy"),
        created_at=utcnow().isoformat(),
    )
    try:
        PersonaStore().save(p)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(_persona_dict(p), status_code=201)


@router.post("/personas/generate")
async def api_generate_persona(request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    description = (body.get("description") or "").strip()
    if not description:
        return JSONResponse({"error": "description is required"}, status_code=400)

    try:
        import json as _json, litellm
        prompt = (
            f"Generate a research persona for: {description}\n\n"
            "Return ONLY valid JSON with keys: name, reading_level, tone, format, source_policy (nullable).\n"
            "reading_level: one of professional/general public/technical/executive\n"
            "tone: one of neutral/technical/plain/strategic\n"
            "format: one of brief/report/bullets/table"
        )
        cfg = get_config()
        resp = await litellm.acompletion(
            model=f"gemini/{cfg.backend.gemini.model}",
            messages=[
                {"role": "system", "content": "You are a persona designer."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256, temperature=0.4, drop_params=True,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        data = _json.loads(raw)
    except Exception:
        data = {"name": description[:40], "reading_level": "professional",
                "tone": "neutral", "format": "brief", "source_policy": None}

    p = SavedPersona(
        id=uuid4().hex, name=data.get("name", description[:40]),
        description=description,
        reading_level=data.get("reading_level", "professional"),
        tone=data.get("tone", "neutral"),
        format=data.get("format", "brief"),
        source_policy=data.get("source_policy"),
        created_at=utcnow().isoformat(),
    )
    return JSONResponse(_persona_dict(p))


@router.post("/personas/{persona_id}/delete")
async def api_delete_persona(persona_id: str) -> JSONResponse:
    try:
        PersonaStore().delete(persona_id)
    except Exception:
        pass
    return JSONResponse({"ok": True})


# ── Focus ──────────────────────────────────────────────────────────────────────
@router.get("/focus")
async def api_list_focus() -> JSONResponse:
    try:
        records = RunStore().list(100)
    except Exception:
        records = []
    # Build a simple entity-frequency focus list from run history
    seen: dict[str, dict] = {}
    for r in records:
        if r.entity not in seen:
            seen[r.entity] = {
                "id": r.entity, "name": r.entity,
                "run_count": 0, "public_findings": 0,
                "private_signals": 0, "last_researched": r.created_at.isoformat(),
            }
        seen[r.entity]["run_count"] += 1
        seen[r.entity]["public_findings"] += r.public
        seen[r.entity]["private_signals"] += r.private
    return JSONResponse(list(seen.values())[:20])


# ── Artifacts ──────────────────────────────────────────────────────────────────
@router.get("/artifacts")
async def api_list_artifacts(project: str = "") -> JSONResponse:
    try:
        records = RunStore().list(50, project_id=project or None)
    except Exception:
        records = []
    return JSONResponse([
        {
            "id": r.id, "target": r.target, "type": r.kind or r.mode,
            "mode": r.mode, "backend": r.backend,
            "public_count": r.public, "private_count": r.private, "gaps": r.gaps,
            "created_at": r.created_at.isoformat(),
            "project_id": r.project_id,
            "task_id": r.task_id,
            "finding_texts": r.finding_texts or [],
            "reference": r.reference or "",
        }
        for r in records
    ])


# ── Settings ───────────────────────────────────────────────────────────────────
@router.get("/settings")
async def api_get_settings() -> JSONResponse:
    cfg = get_config()
    return JSONResponse({
        "backend": cfg.backend.default,
        "vllm_base_url": cfg.backend.vllm.api_base,
        "model": cfg.backend.gemini.model if cfg.backend.default == "gemini" else cfg.backend.vllm.model,
        "governance": cfg.governance.compliance_mode,
        "temperature": cfg.generation.temperature,
        "max_tokens": cfg.generation.max_output_tokens,
        "thinking_budget": None,
        "enable_web_search": True,
        "max_web_results": cfg.search.results,
        "enable_private_retrieval": False,
        "enable_kb": True,
        "enable_grading": cfg.strategy.enabled,
        "enable_gap_analysis": True,
        "gap_threshold": 3,
        "enable_citation": True,
        "enable_memory": cfg.memory.entity_memory,
        "enable_semantic_memory": cfg.memory.kb_context,
        "memory_ttl_days": cfg.memory.retention_days,
        "chroma_prefix": "sentinel",
        # Feature flags (agent pipeline capabilities)
        "two_tier": cfg.research.two_tier,
        "coordinator": cfg.coordinator.enabled,
        "strategy_overlay": cfg.strategy.enabled,
    })


@router.post("/settings")
async def api_update_settings(request: Request) -> JSONResponse:
    try:
        body: dict = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    cfg = get_config()
    try:
        if "backend" in body:
            cfg = _settings.apply_backends(
                cfg, default=body["backend"],
                gemini_model=body.get("model") or cfg.backend.gemini.model,
                vllm_model=body.get("model") or cfg.backend.vllm.model,
                vllm_api_base=body.get("vllm_base_url") or cfg.backend.vllm.api_base,
            )
        if "governance" in body:
            cfg = _settings.apply_governance(
                cfg, compliance_mode=body["governance"],
                audit_log=cfg.governance.audit_log,
                block_cloud_on_private=cfg.governance.block_cloud_on_private,
            )
        if "temperature" in body or "max_tokens" in body:
            from sentinel.web.settings import parse_generation, apply_generation
            gen_form = {
                "temperature": str(body.get("temperature", cfg.generation.temperature or "")),
                "max_output_tokens": str(body.get("max_tokens", cfg.generation.max_output_tokens or "")),
                "top_p": "", "top_k": "",
            }
            gen = parse_generation(gen_form, allow_blank=True)
            cfg = apply_generation(cfg, gen)
        if "max_web_results" in body:
            cfg = _settings.apply_search(
                cfg, provider=cfg.search.provider,
                results=str(body["max_web_results"]),
                onprem_fallback=cfg.search.onprem_fallback,
            )
        if "two_tier" in body:
            cfg.research.two_tier = bool(body["two_tier"])
        if "coordinator" in body:
            cfg.coordinator.enabled = bool(body["coordinator"])
        if "strategy_overlay" in body:
            cfg = _settings.apply_strategy(cfg, enabled=bool(body["strategy_overlay"]),
                                           playbook_dir=cfg.strategy.playbook_dir)
        set_config(cfg, persist=True)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True})


# ── Helpers ────────────────────────────────────────────────────────────────────
def _proj_dict(p: Project) -> dict:
    return {
        "id": p.id, "name": p.name, "website": p.website,
        "description": p.description, "context": p.context,
        "created_at": p.created_at,
    }


def _task_dict(t) -> dict:
    result = None
    if t.result is not None:
        try:
            payload = getattr(t.result, "dashboard_payload", {}) or {}
            # Build one artifact per domain output block, or one catch-all from the payload
            artifacts = []
            if payload:
                domain = t.domain.name if hasattr(t.domain, "name") else str(t.domain)
                # Canonical shape: payload["artifacts"] = {domain_name: content_dict}
                arts_dict = payload.get("artifacts") if isinstance(payload, dict) else None
                if isinstance(arts_dict, dict):
                    for art_key, content in arts_dict.items():
                        if isinstance(content, dict):
                            artifacts.append({
                                "type": art_key, "target": t.objective[:80],
                                "content": content,
                                "public_count": 0, "private_count": 0, "gaps": 0,
                            })
                elif isinstance(payload, dict):
                    # Fallback: payload IS the content (map/matrix/strategy shape)
                    artifacts.append({
                        "type": domain, "target": t.objective[:80],
                        "content": payload,
                        "public_count": 0, "private_count": 0, "gaps": 0,
                    })
            result = {
                "summary": getattr(t.result, "summary", "") or getattr(t.result, "one_line_summary", ""),
                "artifacts": artifacts,
                "citations": [
                    {
                        "label": s.label,
                        "url": s.url,
                        "boundary": s.boundary.value if hasattr(s.boundary, "value") else str(s.boundary),
                    }
                    for s in getattr(t.result, "citations", [])
                ],
                "grade": t.result.grade.model_dump() if getattr(t.result, "grade", None) else None,
            }
        except Exception:
            result = {"summary": "", "artifacts": [], "citations": [], "grade": None}
    return {
        "id": t.id, "project_id": t.project_id, "objective": t.objective,
        "domain": t.domain.name if hasattr(t.domain, "name") else str(t.domain),
        "persona": t.persona.name if hasattr(t.persona, "name") else str(t.persona),
        "status": t.status,
        "created_at": t.created_at,
        "result": result,
        "chat": t.chat or [],
        "fail_reason": getattr(t, "fail_reason", None),
    }


def _persona_dict(p: SavedPersona) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "reading_level": p.reading_level, "tone": p.tone, "format": p.format,
        "source_policy": p.source_policy,
    }
