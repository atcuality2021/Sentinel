"""FastAPI app — the Sentinel dashboard.

A thin presentation layer over the orchestrator. Routes render the dashboard shell
(sidebar + charts), the run form, artifact pages, and the backend/architecture views.
Runs are kept in a small in-memory store so the dashboard charts populate live during a
demo session — no database required (and intentionally non-persistent).

No business logic lives here: ``/run`` calls ``orchestrator.run_async`` and hands the
artifact to the renderer. Boundary separation, gateway swap, and provenance come from core.
"""

from __future__ import annotations

import os
from urllib.parse import quote
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from urllib.parse import urlparse
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

try:  # load .env (GOOGLE_API_KEY, backend config) if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from sentinel.agent.autonomy import gate_proposal
from sentinel.agent.orchestrator import run_async
from sentinel.agent.orchestrator_planner import PlanProposal, plan_task
from sentinel.agent.registry import AgentRegistry
from sentinel.artifacts.schemas import Domain, Persona, Project, Task
from sentinel.config import get_config, set_config
from sentinel.memory import DataBoundary, MemoryStore, RunStore, normalize_entity
from sentinel.memory.schema import utcnow
from sentinel.kb import KBManager, KBSource, SourceType
from sentinel.kb.url_guard import validate_crawl_url
from sentinel.memory.store import KBStore, ProjectStore
from sentinel.priority import PriorityStore, compute_account_priority
from sentinel.tools.private.workspace_mcp import private_boundary_configured
from sentinel.web import render
from sentinel.web import settings as settings_helpers
from sentinel.web import auth as _auth

app = FastAPI(title="Sentinel — Sovereign Intelligence Agent", docs_url="/api/docs")

_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("SENTINEL_CORS_ORIGINS", "http://localhost:3001,http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from sentinel.web.api_json import router as _api_router  # noqa: E402
app.include_router(_api_router, prefix="/api")

# ---- Auth constants ----
_COOKIE = "sentinel_session"
# Routes that bypass auth: login/setup/logout, plus /healthz — uptime probes (systemd, nginx,
# GCP LB) don't follow auth redirects, so a gated health check reads as "down" (found in e2e
# 2026-06-11: /healthz returned 307 → /login). It returns a constant "ok", no data to protect.
_PUBLIC_PATHS = {"/login", "/logout", "/setup", "/healthz", "/favicon.ico"}


def _safe_next(n: str) -> str:
    """Validate a post-login redirect target to prevent open-redirect attacks.

    Only local paths (starting with single '/') are accepted; anything that
    looks like a scheme, netloc, or protocol-relative URL falls back to '/'.
    """
    if not n:
        return "/"
    if not n.startswith("/") or n.startswith("//") or n.startswith("/\\"):
        return "/"
    p = urlparse(n)
    if p.scheme or p.netloc:
        return "/"
    return n

# ---- Auth middleware: intercepts every request before routing ----
@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    # SENTINEL_DISABLE_AUTH=1 skips all auth checks (test environments only)
    if os.getenv("SENTINEL_DISABLE_AUTH") == "1":
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    cfg = get_config()
    # No password set yet → force setup
    if not cfg.auth.password_hash:
        return RedirectResponse("/setup", status_code=307)

    token = request.cookies.get(_COOKIE)
    if not _auth.is_valid_session(token):
        # JSON API callers get 401 instead of an HTML redirect
        if path.startswith("/api/"):
            from fastapi.responses import JSONResponse as _J
            return _J({"error": "unauthenticated"}, status_code=401)
        next_url = quote(path + ("?" + str(request.url.query) if request.url.query else ""))
        return RedirectResponse(f"/login?next={next_url}", status_code=307)

    return await call_next(request)


# ---- Setup (first-boot password creation) ----
@app.get("/setup", response_class=HTMLResponse)
async def setup_get(err: str = "") -> str:
    if get_config().auth.password_hash:
        return RedirectResponse("/", status_code=307)
    return render.setup_page(err=err)

@app.post("/setup", response_class=HTMLResponse)
async def setup_post(
    password: str = Form(...),
    confirm: str = Form(...),
) -> str:
    cfg = get_config()
    if cfg.auth.password_hash:
        return RedirectResponse("/", status_code=307)
    if len(password) < 8:
        return render.setup_page(err="Password must be at least 8 characters.")
    if password != confirm:
        return render.setup_page(err="Passwords do not match.")
    cfg = cfg.model_copy(deep=True)
    cfg.auth.password_hash = _auth.hash_password(password)
    set_config(cfg, persist=True)
    resp = RedirectResponse("/", status_code=303)
    token = _auth.create_session()
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="strict", max_age=43200)
    return resp


# ---- Login ----
@app.get("/login", response_class=HTMLResponse)
async def login_get(next: str = "", err: str = "") -> str:
    if _auth.is_valid_session(None):  # already logged in
        return RedirectResponse(_safe_next(next), status_code=307)
    return render.login_page(next_url=next, err=err)

@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    password: str = Form(...),
    next: str = Form(""),
) -> str:
    ip = request.client.host if request.client else "unknown"
    if not _auth.check_rate_limit(ip):
        return render.login_page(next_url=next,
                                 err="Too many attempts. Wait 5 minutes and try again.")
    cfg = get_config()
    if not cfg.auth.password_hash:
        return RedirectResponse("/setup", status_code=307)
    if not _auth.verify_password(password, cfg.auth.password_hash):
        return render.login_page(next_url=next, err="Incorrect password.")
    resp = RedirectResponse(_safe_next(next), status_code=303)
    token = _auth.create_session()
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="strict", max_age=43200)
    return resp


# ---- Logout ----
@app.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    token = request.cookies.get(_COOKIE)
    _auth.delete_session(token)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(_COOKIE)
    return resp


# --------------------------------------------------------------------------- #
# Durable run store (SENTINEL-002): the dashboard reads from SQLite, so runs and
# charts survive a process restart (AC-1). The orchestrator writes the records.
# --------------------------------------------------------------------------- #
def _runs(limit: int | None = None, *, project_id: str | None = None) -> list:
    store = RunStore()
    if limit:
        return store.list(limit, project_id=project_id)
    return store.all(project_id=project_id)


def _resolve_project(pid: str) -> tuple[str | None, str]:
    """Map a ``?project=<id>`` param to (filter_id, pill_label) for SENTINEL-012 scoping.

    A blank or unknown id ⇒ ``(None, "sovereign")`` so a stale/bad link degrades to the unscoped
    view rather than an empty page. Fail-soft on a store error (NFR-6)."""
    pid = (pid or "").strip()
    if not pid:
        return None, "sovereign"
    try:
        proj = ProjectStore().get_project(pid)
    except Exception:
        return None, "sovereign"
    return (proj.id, proj.name) if proj is not None else (None, "sovereign")


def _when(rec) -> str:
    # created_at is tz-aware UTC; show local wall-clock for the operator.
    return rec.created_at.astimezone().strftime("%H:%M:%S")


def _project_by_entity(records: list) -> dict[str, str]:
    """{entity: project_id} from run records (newest first), so entity-keyed views (focus list)
    can deep-link to the entity's project instead of the thin account page. First (= most
    recent) project wins; entities whose runs predate project scoping are simply absent."""
    out: dict[str, str] = {}
    for r in records:
        if r.project_id and r.entity not in out:
            out[r.entity] = r.project_id
    return out


def _stats(records: list) -> dict:
    return {
        "runs": len(records),
        "artifacts": len(records),
        "public": sum(r.public for r in records),
        "private": sum(r.private for r in records),
    }


def _charts(records: list) -> dict:
    return {
        "provenance": {
            "public": sum(r.public for r in records),
            "private": sum(r.private for r in records),
        },
        "modes": {
            "competitor": sum(r.mode == "competitor" for r in records),
            "client": sum(r.mode == "client" for r in records),
        },
        "backends": {
            "gemini": sum(r.backend == "gemini" for r in records),
            "vllm": sum(r.backend == "vllm" for r in records),
        },
    }


def _active() -> str:
    """The active default backend — read from the ONE center (the config store), not env.

    What the UI shows now equals what a run uses: ``_build.resolve_model`` resolves against
    ``cfg.backend.default`` too. ``SENTINEL_LLM_BACKEND`` only *seeds* this on first boot.
    """
    return get_config().backend.default


def _vllm_model() -> str:
    # Settings (sentinel.config.yaml) is the source of truth for model ids; env only seeds it.
    return get_config().backend.vllm.model


def _key_set(var: str) -> bool:
    """Whether a secret env var holds a real value. Treat empty / the 'not-needed' placeholder
    as unset, so the Settings/Backends pill is honest about an authenticated endpoint."""
    return os.getenv(var, "").strip().lower() not in ("", "not-needed", "none")


def _focus_scores(*, persist: bool = False, project_id: str | None = None) -> list:
    """Deterministic priority score per researched entity, highest first (SENTINEL-010).

    The operator view passes the full ``{PUBLIC,PRIVATE}`` boundary set — a public-only export
    would pass ``{PUBLIC}`` and the same code drops private reasons (AC-10), no separate path.
    Fail-soft per entity (NFR-6): one entity that errors is skipped, the list still renders.
    """
    cfg = get_config()
    if not cfg.priority.enabled:
        return []
    allowed = {DataBoundary.PUBLIC, DataBoundary.PRIVATE}
    store = PriorityStore() if persist else None
    scores = []
    try:
        summaries = RunStore().entities(project_id=project_id)
    except Exception:  # store error → empty focus list, never a 500
        return []
    for s in summaries:
        try:
            score = compute_account_priority(s.entity, allowed_boundaries=allowed, config=cfg)
            if store is not None:
                store.save(score)   # snapshot for audit (AC-11)
            scores.append(score)
        except Exception:  # a single bad entity never sinks the whole list
            continue
    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


def _summary_for(key: str, runs: list):
    """Build the header summary for an account detail page. Reuses the same aggregation as the
    index (AC-6 consistency). Falls back to a minimal summary for a memory-only entity (no runs)."""
    from sentinel.memory import EntitySummary
    from sentinel.memory.schema import utcnow

    if runs:
        return EntitySummary.from_runs(key, runs)
    return EntitySummary(entity=key, display_name=key, runs=0, last_run_at=utcnow(),
                         public=0, private=0, modes=[], kinds=[])


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


# The brand mark, served at the path browsers probe when a page declares no usable icon.
# The layout's inline data-URI icon is malformed on some browsers (unencoded '<'), and the
# login/setup pages declare none — both fall back here, which 404'd on every page load
# (found in e2e 2026-06-11). SVG at /favicon.ico is fine for every modern browser.
_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<rect x='5' y='5' width='22' height='22' rx='6' fill='#4285f4'/>"
    "<text x='16' y='23' font-size='17' font-family='sans-serif' font-weight='700'"
    " fill='#fff' text-anchor='middle'>S</text></svg>"
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    records = _runs()
    recent = [
        {"target": r.target, "entity": r.entity, "mode": r.mode, "backend": r.backend,
         "public": r.public, "private": r.private, "when": _when(r),
         "project_id": r.project_id}
        for r in records[:8]
    ]
    try:
        focus = _focus_scores()[:5]
    except Exception:  # the dashboard never 500s on a scoring hiccup (NFR-6)
        focus = []
    return render.dashboard_page(
        stats=_stats(records), charts=_charts(records), recent=recent, backend=_active(),
        focus=focus, project_by_entity=_project_by_entity(records),
    )


@app.get("/focus", response_class=HTMLResponse)
async def focus(project: str = "") -> str:
    """Ranked focus list (SENTINEL-010). Computes + persists a snapshot per entity (AC-11).

    Optional ``?project=<id>`` scopes the list to one project's entities (SENTINEL-012 AC-10)."""
    cfg = get_config()
    pid, pill = _resolve_project(project)
    if not cfg.priority.enabled:
        return render.focus_page(scores=[], backend=_active(), enabled=False, project=pill)
    try:
        scores = _focus_scores(persist=True, project_id=pid)
    except Exception:  # fail-soft to the empty state (NFR-6)
        scores = []
    try:
        proj_map = _project_by_entity(_runs(project_id=pid))
    except Exception:  # link resolution is best-effort; account fallback still works
        proj_map = {}
    return render.focus_page(scores=scores, backend=_active(), enabled=True, project=pill,
                             project_by_entity=proj_map)


@app.get("/new", response_class=HTMLResponse)
async def new_run() -> str:
    return render.form_page(
        default_backend=_active(),
        private_configured=private_boundary_configured(),
        vllm_model=_vllm_model(),
        sovereign=get_config().governance.compliance_mode == "on_prem_required",
    )


_ROLE_META = {
    # role → (visual kind, tier label, what it does)
    "planner": ("tool", "Gemma-12B · tool-caller", "decomposes the target into 3–5 research questions"),
    "public_research": ("tool", "Gemini · grounded search", "runs web search → cited public findings"),
    "private_research": ("private", "Gemma-12B · scoped MCP", "reads the private workspace over MCP"),
    "extractor": ("tool", "Gemma-12B · tool-caller", "distils findings into typed per-source notes"),
    "synthesizer": ("reason", "Gemma-26B · reasoner", "writes the structured artifact"),
    "strategist": ("reason", "Gemma-26B · reasoner", "adds an assessment + prioritized action plan"),
}


def _agents_view(cfg) -> tuple[list, dict]:
    """Introspect the real specs + config into a per-mode node list for the Agents page.

    Shows the full architecture — including dark (flagged-off) stages — so the page documents
    what *would* run: the extractor (two-tier), the private-research step (boundary), and the
    strategist (strategy overlay) appear dashed when their flag is off.
    """
    from sentinel.agent.modes.spec import CLIENT_SPEC, COMPETITOR_SPEC

    private_on = private_boundary_configured()
    two_tier = cfg.research.two_tier
    strat_on = cfg.strategy.enabled

    def role_of(key: str) -> str:
        ac = cfg.agents.get(key)
        return ac.role if ac else "synthesizer"

    def node(name: str, role: str, out: str, *, dark: bool, flag: str = "") -> dict:
        kind, tier, desc = _ROLE_META.get(role, ("tool", "", ""))
        return {"name": name, "role": role, "kind": kind, "tier": tier,
                "desc": desc, "out": out, "dark": dark, "flag": flag}

    modes = []
    for spec, title in ((COMPETITOR_SPEC, "Competitor Intelligence"),
                        (CLIENT_SPEC, "Account Intelligence")):
        mode = spec.name.split("_", 1)[1]
        nodes = []
        for step in spec.steps:
            if step.role == "synthesize":  # the extractor sits right before synthesis (two-tier)
                nodes.append(node(spec.extractor_name or f"{mode}_extractor", "extractor",
                                  "extractions", dark=not two_tier, flag="two-tier"))
            nodes.append(node(step.name, role_of(step.agent_key), step.output_key,
                              dark=(step.tool == "private" and not private_on),
                              flag="private boundary" if step.tool == "private" else ""))
        nodes.append(node(f"{mode}_strategist", "strategist", "strategy",
                          dark=not strat_on, flag="strategy overlay"))
        modes.append({"mode": mode, "title": title,
                      "artifact": spec.output_schema.__name__, "nodes": nodes})

    flags = {"two_tier": two_tier, "strategy": strat_on, "private": private_on,
             "coordinator": cfg.coordinator.enabled}
    return modes, flags


def _agents_html(*, ok: str = "", err: str = "") -> str:
    cfg = get_config()
    modes, flags = _agents_view(cfg)
    return render.agents_page(
        modes=modes, flags=flags, backend=_active(),
        agents_cfg=dict(cfg.agents), ok=ok, err=err,
    )


@app.get("/agents", response_class=HTMLResponse)
async def agents(ok: str = "", err: str = "") -> str:
    """The agent roster + pipeline flow graph (introspected from the live specs + config)."""
    return _agents_html(ok=ok, err=err)


@app.post("/agents", response_class=HTMLResponse)
async def agents_create(
    key: str = Form(...),
    role: str = Form("synthesizer"),
    model: str = Form(""),
) -> RedirectResponse:
    from urllib.parse import quote as _q
    try:
        cfg = settings_helpers.create_agent(get_config(), key, role, model or None)
        set_config(cfg, persist=True)
    except ValueError as exc:
        return RedirectResponse(f"/agents?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/agents?ok={_q(f'Agent {key.strip()} created.')}", status_code=303)


@app.post("/agents/{key}", response_class=HTMLResponse)
async def agents_update(
    key: str,
    enabled: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    max_output_tokens: str = Form(""),
    top_p: str = Form(""),
    top_k: str = Form(""),
) -> RedirectResponse:
    from urllib.parse import quote as _q
    # Backend is implicit in the model choice: gemini-* → pin Gemini; gemma-* → vLLM; blank → default
    model = model.strip()
    pin_gemini = model.startswith("gemini-")
    form = {"temperature": temperature, "max_output_tokens": max_output_tokens,
            "top_p": top_p, "top_k": top_k}
    try:
        gen = settings_helpers.parse_generation(form, allow_blank=True)
        cfg = settings_helpers.apply_agent(
            get_config(), key, enabled=bool(enabled), model=model,
            pin_gemini=pin_gemini, gen=gen,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return RedirectResponse(f"/agents?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/agents?ok={_q(f'Agent {key} saved.')}", status_code=303)


@app.post("/agents/{key}/delete", response_class=HTMLResponse)
async def agents_delete(key: str) -> RedirectResponse:
    from urllib.parse import quote as _q
    try:
        cfg = settings_helpers.delete_agent(get_config(), key)
        set_config(cfg, persist=True)
    except ValueError as exc:
        return RedirectResponse(f"/agents?err={_q(str(exc))}", status_code=303)
    return RedirectResponse(f"/agents?ok={_q(f'Agent {key} deleted.')}", status_code=303)


@app.get("/artifacts", response_class=HTMLResponse)
async def artifacts(project: str = "") -> str:
    pid, pill = _resolve_project(project)  # optional project scope (SENTINEL-012 AC-10)
    items = [
        {"target": r.target, "entity": r.entity, "kind": r.kind, "public": r.public,
         "private": r.private, "backend": r.backend, "reference": r.reference, "when": _when(r),
         "project_id": r.project_id}
        for r in _runs(project_id=pid)
    ]
    return render.artifacts_page(artifacts=items, backend=_active(), project=pill)


@app.get("/backends", response_class=HTMLResponse)
async def backends() -> RedirectResponse:
    return RedirectResponse("/settings", status_code=301)


# --------------------------------------------------------------------------- #
# Accounts — purge only. GET /accounts and GET /accounts/{entity} removed 2026-06-15;
# memory source config moved to the project Memory tab. The POST purge is kept for
# data-subject right-to-deletion; it redirects to /projects (AC-8: POST-only, no GET delete).
# --------------------------------------------------------------------------- #
@app.post("/accounts/{entity}/purge")
async def account_purge(entity: str) -> RedirectResponse:
    key = normalize_entity(entity)
    try:
        MemoryStore().purge_entity(key)
    except Exception:  # nothing to surface on the redirect target if it failed; stay fail-soft
        pass
    # 303 → the browser re-GETs /projects, so a refresh can't re-trigger the POST (AC-8).
    return RedirectResponse(url="/projects?ok=Entity+memory+purged.", status_code=303)


# --------------------------------------------------------------------------- #
# Projects (SENTINEL-012) — the organising construct above runs. Step 6 ships the
# shell: create + list + open. Task definition and the orchestrated value chain
# (map → compare → strategy) arrive in Phase 2. All reads fail-soft (NFR-6).
# --------------------------------------------------------------------------- #
@app.get("/projects", response_class=HTMLResponse)
async def projects(ok: str = "") -> str:
    try:
        items = ProjectStore().list_projects()
    except Exception:  # a store error degrades to the empty/create state, never a 500
        items = []
    return render.projects_page(projects=items, backend=_active(), ok=ok)


@app.post("/projects")
async def create_project(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    website: str = Form(""),
    objective: str = Form(""),
    context: str = Form(""),
    client_url: str = Form(""),
) -> RedirectResponse:
    name = name.strip()
    if not name:
        return RedirectResponse(url="/projects", status_code=303)
    store = ProjectStore()
    existing = store.get_project_by_name(name)
    if existing:
        return RedirectResponse(url=f"/projects/{existing.id}", status_code=303)
    proj = Project(
        id=uuid4().hex, name=name, website=website.strip() or None,
        context=context.strip(),
        created_at=utcnow().isoformat(),
    )
    try:
        store.save_project(proj)
    except Exception:
        return RedirectResponse(url="/projects?ok=Could+not+save+project.", status_code=303)

    # Auto-seed KB with the project website so crawl starts immediately
    if proj.website:
        try:
            crawl_url = validate_crawl_url(proj.website)
            source = KBSource(project_id=proj.id, url=crawl_url, source_type=SourceType.WEB)
            KBStore().save({
                "id": source.id, "project_id": source.project_id, "url": source.url,
                "source_type": source.source_type.value, "status": "pending",
                "chunk_count": 0, "error": None,
            })

            async def _auto_crawl(src_id: str, pid: str, u: str) -> None:
                result = await KBManager(_kb_data_dir()).add_source(pid, u, SourceType.WEB)
                KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

            background_tasks.add_task(_auto_crawl, source.id, proj.id, crawl_url)
        except Exception:
            pass  # invalid URL or store error — don't block project creation

    objective = objective.strip()
    client_url = client_url.strip()
    if objective:
        # Thread context + client_url through to the plan route, which owns task-context
        # persistence and the client-site KB crawl (PRG — no logic duplicated here).
        url = f"/projects/{proj.id}/plan?objective={quote(objective)}"
        if context.strip():
            url += f"&context={quote(context.strip())}"
        if client_url:
            url += f"&client_url={quote(client_url)}"
        return RedirectResponse(url=url, status_code=303)
    # No objective: still seed the KB with the client/target site so it's ready for the
    # first task (same fail-soft auto-crawl as the project website above).
    if client_url:
        try:
            crawl_url = validate_crawl_url(client_url)
            source = KBSource(project_id=proj.id, url=crawl_url, source_type=SourceType.WEB)
            KBStore().save({
                "id": source.id, "project_id": source.project_id, "url": source.url,
                "source_type": source.source_type.value, "status": "pending",
                "chunk_count": 0, "error": None,
            })

            async def _auto_crawl_client(src_id: str, pid: str, u: str) -> None:
                result = await KBManager(_kb_data_dir()).add_source(pid, u, SourceType.WEB)
                KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

            background_tasks.add_task(_auto_crawl_client, source.id, proj.id, crawl_url)
        except Exception:
            pass  # invalid URL or store error — don't block project creation
    return RedirectResponse(url=f"/projects/{proj.id}", status_code=303)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: str, ok: str = "", err: str = "") -> str:
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    try:
        tasks = store.tasks_for_project(project_id)
    except Exception:
        tasks = []
    try:
        kb_source_count = len(KBStore().list_for_project(project_id))
    except Exception:
        kb_source_count = 0
    return render.project_detail_page(
        project=proj, tasks=tasks, backend=_active(),
        vllm_model=_vllm_model(),
        sovereign=get_config().governance.compliance_mode == "on_prem_required",
        ok=ok, err=err,
        kb_source_count=kb_source_count,
    )


@app.post("/projects/{project_id}/delete")
async def delete_project_route(project_id: str) -> RedirectResponse:
    """Delete a project and all its tasks/plans. Redirects to the projects list."""
    try:
        ProjectStore().delete_project(project_id)
    except Exception:
        pass
    return RedirectResponse(url="/projects?ok=Project+deleted.", status_code=303)


@app.post("/projects/{project_id}/edit")
async def edit_project(
    project_id: str,
    name: str = Form(""),
    website: str = Form(""),
    description: str = Form(""),
    context: str = Form(""),
) -> RedirectResponse:
    """Update project name, website, description, and agent context."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return RedirectResponse(f"/projects/{project_id}?err=Project+not+found", status_code=303)
    if name.strip():
        proj.name = name.strip()
    proj.website = website.strip() or None
    proj.description = description.strip()
    proj.context = context.strip()
    store.save_project(proj)
    return RedirectResponse(f"/projects/{project_id}?ok=Project+updated", status_code=303)


@app.get("/projects/{project_id}/tasks", response_class=HTMLResponse)
async def project_tasks(project_id: str) -> str:
    """Research tab — task creation form + full task list for this project."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    try:
        tasks = store.tasks_for_project(project_id)
    except Exception:
        tasks = []
    try:
        from sentinel.memory.store import PersonaStore
        saved_personas = PersonaStore().list()
    except Exception:
        saved_personas = []  # library is an enhancement — the form must render without it
    return render.project_tasks_page(
        project=proj, tasks=tasks, backend=_active(),
        vllm_model=_vllm_model(),
        sovereign=get_config().governance.compliance_mode == "on_prem_required",
        saved_personas=saved_personas,
    )


def _kb_data_dir():
    from pathlib import Path
    import os
    return Path(os.getenv("SENTINEL_DATA_DIR", "data"))


@app.get("/projects/{project_id}/kb", response_class=HTMLResponse)
async def project_kb(project_id: str, ok: str = "", err: str = "") -> str:
    """Knowledge Base tab — shows indexed sources and crawl form."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    sources = KBStore().list_for_project(project_id)
    return render.project_kb_page(project=proj, sources=sources, backend=_active(), ok=ok, err=err)


def _infer_source_type(url: str) -> str:
    """Auto-detect source type from URL so users don't need a type dropdown."""
    low = url.lower()
    if any(d in low for d in ("linkedin.com", "youtube.com", "twitter.com", "instagram.com", "crunchbase.com")):
        return "social"
    if low.endswith(".pdf") or "/pdf/" in low:
        return "document"
    return "web"


@app.post("/projects/{project_id}/kb/sources")
async def project_kb_add_source(
    project_id: str,
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    source_type: str = Form("auto"),
    redirect: str = Form("kb"),
) -> RedirectResponse:
    """Start a background crawl + index job for the given URL."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return RedirectResponse(f"/projects/{project_id}/kb?err=Project+not+found", status_code=303)

    # SSRF guard — validate scheme and resolve hostname before storing or crawling
    try:
        url = validate_crawl_url(url)
    except ValueError as exc:
        return RedirectResponse(
            f"/projects/{project_id}/kb?err={quote(str(exc), safe='')}",
            status_code=303,
        )

    resolved_type = source_type if source_type in ("web", "social", "document") else _infer_source_type(url)
    kb_store = KBStore()
    source = KBSource(
        project_id=project_id,
        url=url,
        source_type=SourceType(resolved_type),
    )
    kb_store.save({
        "id": source.id,
        "project_id": source.project_id,
        "url": source.url,
        "source_type": source.source_type.value,
        "status": "pending",
        "chunk_count": 0,
        "error": None,
    })

    async def _run_crawl(src_id: str, pid: str, crawl_url: str, stype: str) -> None:
        manager = KBManager(_kb_data_dir())
        result = await manager.add_source(
            pid, crawl_url, SourceType(stype),
        )
        KBStore().update_status(
            src_id, result.status.value, result.chunk_count, result.error,
        )

    background_tasks.add_task(_run_crawl, source.id, project_id, url, source.source_type.value)
    ok_msg = quote(f"Indexing {url} in background", safe="")
    dest = f"/projects/{project_id}/?ok={ok_msg}" if redirect == "overview" else f"/projects/{project_id}/kb?ok={ok_msg}"
    return RedirectResponse(dest, status_code=303)


@app.post("/projects/{project_id}/kb/sources/{source_id}/delete")
async def project_kb_delete_source(project_id: str, source_id: str) -> RedirectResponse:
    """Remove a KB source record (does not delete vector data for now)."""
    KBStore().delete(source_id, project_id)
    return RedirectResponse(f"/projects/{project_id}/kb?ok=Source+removed", status_code=303)


@app.post("/projects/{project_id}/kb/sources/{source_id}/retry")
async def project_kb_retry_source(
    project_id: str, source_id: str, background_tasks: BackgroundTasks
) -> RedirectResponse:
    """Re-queue a failed KB source for crawling and indexing."""
    src = KBStore().get(source_id)
    if not src or src.get("project_id") != project_id:
        return RedirectResponse(f"/projects/{project_id}/kb?err=Source+not+found", status_code=303)
    if src.get("url", "").startswith("artifact://"):
        return RedirectResponse(
            f"/projects/{project_id}/kb?err=Artifact+sources+cannot+be+re-crawled", status_code=303
        )
    KBStore().update_status(source_id, "pending", 0, None)

    async def _run_crawl(src_id: str, pid: str, crawl_url: str, stype: str) -> None:
        manager = KBManager(_kb_data_dir())
        result = await manager.add_source(pid, crawl_url, SourceType(stype))
        KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)

    background_tasks.add_task(_run_crawl, source_id, project_id, src["url"], src.get("source_type", "web"))
    return RedirectResponse(
        f"/projects/{project_id}/kb?ok=Re-indexing+started", status_code=303
    )


@app.post("/projects/{project_id}/kb/sources/artifact")
async def project_kb_add_artifact(
    project_id: str,
    run_id: str = Form(...),
) -> RedirectResponse:
    """Ingest a completed research artifact back into this project's KB.

    Fetches the run's finding_texts (boundary-tagged facts), joins them into a
    single document, and indexes it via KBManager.add_text() so future research
    tasks can ground against prior findings via search_project_kb.
    """
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return RedirectResponse(f"/projects/{project_id}/kb?err=Project+not+found", status_code=303)

    run = RunStore().get(run_id)
    if run is None or run.project_id != project_id:
        return RedirectResponse(f"/projects/{project_id}/kb?err=Run+not+found", status_code=303)

    # Primary: boundary-tagged finding sentences from the run record.
    text = "\n\n".join(run.finding_texts) if run.finding_texts else ""

    # Fallback: if findings are empty (e.g. partial run), pull structured content from the
    # matching task's dashboard_payload so even partial artifacts are indexable.
    if not text.strip():
        try:
            tasks = store.tasks_for_project(project_id)
            match = next((t for t in tasks if t.objective == run.target and t.result), None)
            if match and match.result:
                r = match.result
                parts: list[str] = []
                if r.summary:
                    parts.append(r.summary)
                if r.persona_rendered:
                    parts.append(r.persona_rendered)
                payload = r.dashboard_payload or {}
                arts = payload.get("artifacts") or payload
                if isinstance(arts, dict):
                    for v in arts.values():
                        if isinstance(v, dict):
                            for fld in ("one_line_summary", "financial_summary", "description",
                                        "overview", "findings"):
                                val = v.get(fld)
                                if val and isinstance(val, str):
                                    parts.append(val)
                            products = v.get("products") or []
                            for p in (products if isinstance(products, list) else []):
                                if isinstance(p, dict):
                                    for fld in ("name", "description", "differentiators"):
                                        val = p.get(fld)
                                        if val and isinstance(val, str):
                                            parts.append(val)
                text = "\n\n".join(p for p in parts if p.strip())
        except Exception:
            pass

    if not text.strip():
        return RedirectResponse(
            f"/projects/{project_id}/kb?err=No+content+to+ingest+for+this+run",
            status_code=303,
        )

    label = run.target[:120]
    manager = KBManager(_kb_data_dir())
    source = manager.add_text(project_id, text, label)

    from urllib.parse import quote as _q
    kb_store = KBStore()
    kb_store.save({
        "id": source.id,
        "project_id": project_id,
        "url": source.url,
        "source_type": source.source_type.value,
        "status": source.status.value,
        "chunk_count": source.chunk_count,
        "error": source.error,
    })

    if source.status.value == "indexed":
        msg = f"ok=Artifact+indexed+({source.chunk_count}+chunks)"
    else:
        msg = f"err={_q(source.error or 'indexing failed', safe='')}"
    return RedirectResponse(f"/projects/{project_id}/kb?{msg}", status_code=303)


from fastapi.responses import JSONResponse  # noqa: E402

@app.get("/projects/{project_id}/kb/search")
async def kb_search(project_id: str, q: str = "") -> JSONResponse:
    """Hybrid KB search — BM25 + vector + rerank. Returns top-5 chunks as JSON."""
    if not q.strip():
        return JSONResponse({"results": []})
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return JSONResponse({"error": "project not found"}, status_code=404)
    try:
        from sentinel.kb.search import hybrid_search
        hits = hybrid_search(project_id, _kb_data_dir(), q.strip(), rerank_top_k=5)
        return JSONResponse({"results": [r.to_dict() for r in hits]})
    except Exception as exc:
        return JSONResponse({"error": str(exc), "results": []})


@app.post("/projects/{project_id}/kb/upload")
async def project_kb_upload(
    project_id: str,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(default=[]),
    redirect: str = Form("kb"),
) -> RedirectResponse:
    """Upload one or more PDF/TXT/MD files, extract text, and index into the project KB."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return RedirectResponse(f"/projects/{project_id}/kb?err=Project+not+found", status_code=303)

    dest_base = f"/projects/{project_id}/" if redirect == "overview" else f"/projects/{project_id}/kb"

    _MAX_BYTES = 100 * 1024 * 1024  # 100 MB per file hard cap

    def _extract_and_ingest(pid: str, raw: bytes, ext: str, lbl: str, src_id: str) -> None:
        """Run in background — CPU-heavy extraction never blocks the request loop."""
        try:
            if ext == "pdf":
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                KBStore().update_status(src_id, "error", 0, "No text could be extracted")
                return
            result = KBManager(_kb_data_dir()).add_text(pid, text, lbl)
            KBStore().update_status(src_id, result.status.value, result.chunk_count, result.error)
        except Exception as exc:
            KBStore().update_status(src_id, "error", 0, str(exc)[:200])

    queued: list[str] = []
    for file in files:
        filename = (file.filename or "").strip()
        if not filename:
            continue
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ("pdf", "txt", "md"):
            continue

        # Read bytes async — non-blocking even for large files
        raw_bytes = await file.read()
        if not raw_bytes:
            continue
        if len(raw_bytes) > _MAX_BYTES:
            continue  # silently skip files over 100 MB

        label = filename.rsplit(".", 1)[0][:80]
        kb_store = KBStore()
        source_rec = KBSource(
            project_id=project_id,
            url=f"upload://{label}",
            source_type=SourceType.DOCUMENT,
        )
        # Register immediately so UI shows "pending" — extraction happens in background
        kb_store.save({
            "id": source_rec.id,
            "project_id": project_id,
            "url": f"upload://{label}",
            "source_type": "document",
            "status": "pending",
            "chunk_count": 0,
            "error": None,
        })
        background_tasks.add_task(_extract_and_ingest, project_id, raw_bytes, ext, label, source_rec.id)
        queued.append(filename)

    if not queued:
        return RedirectResponse(
            f"{dest_base}?err=No+valid+files+found+(PDF,+TXT,+MD+up+to+100+MB)",
            status_code=303,
        )
    names = ", ".join(queued[:3]) + ("…" if len(queued) > 3 else "")
    ok_msg = quote(f"Queued {len(queued)} file(s) for indexing: {names} — refresh in a moment to see status", safe="")
    return RedirectResponse(f"{dest_base}?ok={ok_msg}", status_code=303)


@app.post("/projects/{project_id}/kb/chat")
async def project_kb_chat(project_id: str, request: Request) -> JSONResponse:
    """KB conversational chat — searches the KB, then synthesises a grounded answer via LLM."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    if not message:
        return JSONResponse({"error": "empty message"}, status_code=400)

    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return JSONResponse({"error": "project not found"}, status_code=404)

    # Search KB for relevant context
    hits: list = []
    kb_context = ""
    try:
        from sentinel.kb.search import hybrid_search
        hits = hybrid_search(project_id, _kb_data_dir(), message, rerank_top_k=6)
        if hits:
            kb_context = "\n\n---\n\n".join(
                f"[{h.title or h.url}]\n{h.text}" for h in hits[:6]
            )
    except Exception:
        pass

    proj_name = proj.name if proj else "this project"
    system_prompt = (
        f"You are a research assistant for the project '{proj_name}'. "
        "Answer questions using ONLY the knowledge base excerpts provided below. "
        "Be specific, cite the source title when referencing a fact, and say 'not in the knowledge base' "
        "if the answer cannot be found in the provided excerpts.\n\n"
        + (f"KNOWLEDGE BASE:\n{kb_context}" if kb_context else
           "KNOWLEDGE BASE: (empty — no sources indexed yet)")
    )

    messages = [{"role": "system", "content": system_prompt}]
    for turn in (history or [])[-10:]:  # last 10 turns for context
        if isinstance(turn, dict) and turn.get("role") in ("user", "assistant"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": message})

    try:
        import litellm as _litellm
        resp = await _litellm.acompletion(
            model=f"gemini/{get_config().backend.gemini.model}",
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
            drop_params=True,
        )
        answer = resp.choices[0].message.content or ""
    except Exception as exc:
        answer = f"Could not generate answer: {exc}"

    return JSONResponse({"answer": answer, "sources_used": len(hits) if kb_context else 0})


@app.get("/projects/{project_id}/memory", response_class=HTMLResponse)
async def project_memory(project_id: str, ok: str = "", err: str = "") -> str:
    """Memory tab — episodic run records scoped to this project."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    try:
        records = RunStore().all(project_id=project_id)
    except Exception:
        records = []
    try:
        from sentinel.memory.store import MemoryStore
        semantic_facts = MemoryStore().list_semantic_facts(project_id)
    except Exception:
        semantic_facts = []
    return render.project_memory_page(
        project=proj, records=records, backend=_active(), ok=ok, err=err,
        semantic_facts=semantic_facts,
    )


@app.post("/projects/{project_id}/memory/{run_id}/delete")
async def project_memory_delete(project_id: str, run_id: str) -> RedirectResponse:
    """Delete a single episodic run record from project memory.

    project_id is passed to the store so only runs belonging to this project can be deleted
    (IDOR guard — a crafted URL using another project's run_id returns not-found, not a delete).
    """
    try:
        deleted = RunStore().delete_run(run_id, project_id=project_id)
        msg = f"ok=Run+{run_id[:8]}…+deleted." if deleted else f"err=Run+{run_id[:8]}+not+found."
    except Exception as exc:
        msg = f"err={type(exc).__name__}"
    return RedirectResponse(url=f"/projects/{project_id}/memory?{msg}", status_code=303)


@app.get("/projects/{project_id}/report", response_class=HTMLResponse)
async def project_report(project_id: str) -> str:
    """Report tab — consulting-grade output compiled from all task results for this project."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    tasks = [
        {"id": t.id, "objective": t.objective, "status": t.status,
         "result": t.result.model_dump() if t.result else None}
        for t in store.tasks_for_project(project_id)
    ]
    return render.project_report_page(project=proj, tasks=tasks, backend=_active())


@app.get("/projects/{project_id}/artifacts", response_class=HTMLResponse)
async def project_artifacts(project_id: str) -> str:
    """Artifacts tab — all run outputs scoped to this project."""
    store = ProjectStore()
    try:
        proj = store.get_project(project_id)
    except Exception:
        proj = None
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    items = [
        {"target": r.target, "entity": r.entity, "kind": r.kind, "public": r.public,
         "private": r.private, "backend": r.backend, "reference": r.reference, "when": _when(r),
         "run_id": r.id, "finding_texts": r.finding_texts}
        for r in _runs(project_id=project_id)
    ]
    return render.artifacts_page(
        artifacts=items, backend=_active(),
        project=proj.name, project_id=project_id,
    )


# --------------------------------------------------------------------------- #
# Plan review + autonomy gate (SENTINEL-012 Step 16). The planner proposes a DAG;
# the project's `autonomy` setting decides whether it runs. `propose` (default) shows
# the review screen and executes NOTHING; `autonomous` runs on the spot. The Approve
# button on the review screen is the human's explicit opt-in to run a proposed plan.
# --------------------------------------------------------------------------- #
def _cloud_allowed_for(proj) -> bool:
    """A project may pin `on_prem_required`; otherwise inherit the session default (cloud_ok)."""
    return (proj.settings.compliance or "cloud_ok") != "on_prem_required"


def _run_policy(cloud_allowed: bool) -> dict:
    """Resolve the backend + search provider an orchestrated run should use, honouring governance
    (so a sovereign project gets vllm + a non-cloud search provider, and a cloud_ok project uses the
    configured default — e.g. duckduckgo when that's set). Without this the DAG silently defaulted to
    Gemini search regardless of config."""
    from sentinel.agent.governance import effective_backend, effective_search_provider

    cfg = get_config()
    resolved_backend = effective_backend(cfg) if cloud_allowed else "vllm"
    return {
        "backend": resolved_backend,
        "search_provider": effective_search_provider(cfg, allow_cloud=cloud_allowed, backend=resolved_backend),
    }


def _extract(objective: str, patterns: list[str], fallback: str) -> str:
    """First regex group-1 match across ``patterns`` (case-insensitive), trimmed; else ``fallback``.
    Deterministic and fail-soft — a no-match never raises, it just yields the fallback."""
    import re

    for pat in patterns:
        m = re.search(pat, objective, re.I)
        if m and m.group(1).strip(" .,\"'"):
            return m.group(1).strip(" .,\"'")
    return fallback


def _plan_seeds(task, plan, project=None) -> dict:
    """Per-step research targets (capability-aware) — the fix that makes multi-step output substantive.

    Seeding *every* step with the raw objective made the ``competitor`` step research the whole sentence
    ('…compare against a competitor') and ask for a name. Instead: the **self side** (``self_profile``)
    researches OUR org; the **rival side** (``competitor``/``client``) researches the named entity pulled
    from the objective; reasoners (``compare``/strategy) read upstream state, so the objective is enough.
    Every step also carries the full objective as ``vertical_context``. All extraction is fail-soft."""
    obj = task.objective
    # Our org for the self side: prefer a name in the objective ("Profile BiltIQ AI"), else the
    # project's website host (the canonical 'us' identity — this is what makes Website meaningful),
    # else the project name. Falls back to the objective only if none resolve.
    site = (getattr(project, "website", None) or "").strip()
    host = site.split("//", 1)[-1].split("/", 1)[0].lstrip("www.") if site else ""
    def _cap(s: str | None, max_words: int = 4) -> str | None:
        """Truncate an extracted phrase to the entity name — strips leading articles, then
        stops at the first preposition/descriptor that signals a phrase boundary."""
        if not s:
            return s
        words = s.split()
        _LEAD = {"and", "the", "a", "an"}
        _STOP = {"for", "in", "at", "under", "with", "by", "from", "to", "of", "on",
                 "over", "via", "available", "currently", "based", "across"}
        while words and words[0].lower() in _LEAD:
            words = words[1:]
        clean: list[str] = []
        for w in words[:max_words]:
            if clean and w.lower() in _STOP:
                break
            clean.append(w)
        return " ".join(clean) if clean else " ".join(words[:max_words])

    org = _cap(_extract(
        obj,
        [r"\b(?:profile|research|analy(?:se|ze)|assess|about)\s+(.+?)"
         r"(?:\s+(?:and|,|vs\.?|versus|against|compared?\b|to\b)|$)"],
        host or getattr(project, "name", None) or obj,
    ))
    # Topic-word guard: "Research AI based government solutions…" extracts org="AI" — a subject
    # area, not an organisation — and the agents then faithfully profile the wrong entity (live
    # 2026-06-11: a run researched Google's AI products instead of the user's org). When the
    # extracted "org" is a generic tech/topic token, fall back to the project's own identity.
    _GENERIC_TOPICS = {
        "ai", "ml", "iot", "ar", "vr", "genai", "llm", "llms", "saas", "crm", "erp",
        "digital", "software", "technology", "tech", "data", "cloud", "cyber",
        "cybersecurity", "blockchain", "automation", "analytics",
        "best", "top", "new", "latest", "leading", "modern",
    }
    if org and org.lower() in _GENERIC_TOPICS:
        org = _cap(host or getattr(project, "name", None) or obj)
    rival = _cap(_extract(
        obj,
        [r"\b(?:against|vs\.?|versus|compared?\s+(?:to|with)|competitor[s]?:?)\s+(.+?)(?:\s+(?:and|,|\.)|$)"],
        None,  # None = no rival found (don't fall back to full objective)
    ))
    # When no specific rival is named, synthesize a focused target from the org identity so the
    # competitor synthesizer gets a concrete anchor instead of the full multi-sentence objective.
    # Use org only when it looks like a company name (≤3 words, not a phrase extracted from obj).
    if rival is None or rival == obj:
        _org_words = (org or "").split()
        if org and org != obj and len(_org_words) <= 3:
            rival = f"{org} top competitor"
        else:
            rival = "top competitor in the market"
    # inject_org_prefs: when the config flag is on, enrich every step's vertical_context with
    # the project name and website so the synthesizer knows WHO we are researching FOR.
    # The existing prompt templates already surface vertical_context — no prompt edits needed.
    cfg_mem = getattr(get_config(), "memory", None)
    inject_prefs = getattr(cfg_mem, "inject_org_prefs", True) if cfg_mem else True
    org_ctx = ""
    if inject_prefs and project is not None:
        proj_name = getattr(project, "name", "") or ""
        if proj_name:
            org_ctx = f"\n\nProject context: researching on behalf of '{proj_name}'"
            if site:
                org_ctx += f" ({site})"

    # Task context > project context, both appended to vertical_context.
    task_ctx = getattr(task, "context", None) or ""
    proj_ctx = getattr(project, "context", None) or "" if project is not None else ""
    combined_ctx = (task_ctx or proj_ctx).strip()
    extra_ctx = f"\n\nAdditional context: {combined_ctx}" if combined_ctx else ""

    out = {}
    for s in plan.steps:
        if s.capability == "self_profile":
            target = org
        elif s.capability in ("competitor", "client"):
            target = rival
        elif s.capability == "govt_dept_research":
            # Decode dept slug from step ID: "research_dept_flood_management" → "flood management"
            slug = s.id.removeprefix("research_dept_").replace("_", " ")
            target = f"{slug} — {obj}"
        elif s.capability == "govt_synthesis":
            target = obj
        else:
            target = obj
        seed = {"target": target, "vertical_context": obj + org_ctx + extra_ctx}
        if site:
            seed["website"] = site
        out[s.id] = seed
    return out


def _grade_sample() -> bool:
    """Whether to model-grade a production run (§10.4, TD-3). Dark by default — grading calls the
    live judge, so it's opt-in via ``SENTINEL_GRADE_SAMPLE=1`` to avoid surprise demo latency."""
    return os.getenv("SENTINEL_GRADE_SAMPLE", "").strip().lower() in {"1", "true", "yes", "on"}


def _extract_finding_texts(result) -> list[str]:
    """Extract plain-text findings from a Result's dashboard_payload.

    Walks every artifact dict in the payload and collects string-typed leaf values
    from known text fields (strengths, weaknesses, positioning, description, etc.)
    so the RunRecord.finding_texts is populated for Memory/KB reuse even when the
    artifact uses a domain-specific schema (not Battlecard/AccountBrief).
    """
    _TEXT_FIELDS = (
        "text", "description", "positioning", "financial_summary", "overview",
        "assessment", "rationale", "content", "summary",
    )
    _LIST_TEXT_FIELDS = (
        "strengths", "weaknesses", "differentiators", "opportunities", "risks",
        "key_findings", "recommendations", "recent_developments", "pricing_signals",
    )
    texts: list[str] = []
    payload = result.dashboard_payload or {}
    arts = payload.get("artifacts") or payload
    if not isinstance(arts, dict):
        return texts

    for art in arts.values():
        if not isinstance(art, dict):
            continue
        for field in _TEXT_FIELDS:
            val = art.get(field)
            if val and isinstance(val, str):
                texts.append(val)
        for field in _LIST_TEXT_FIELDS:
            items = art.get(field) or []
            for item in (items if isinstance(items, list) else []):
                if isinstance(item, str) and item:
                    texts.append(item)
                elif isinstance(item, dict):
                    t = item.get("text") or item.get("description") or ""
                    if t:
                        texts.append(t)
        for product in (art.get("products") or []):
            if not isinstance(product, dict):
                continue
            for field in _TEXT_FIELDS:
                val = product.get(field)
                if val and isinstance(val, str):
                    texts.append(val)
            for field in _LIST_TEXT_FIELDS:
                items = product.get(field) or []
                for item in (items if isinstance(items, list) else []):
                    if isinstance(item, str) and item:
                        texts.append(item)

    return [t for t in texts if t.strip()]


def _persist_run(task, result, backend: str) -> None:
    """Persist an orchestrated Result to the durable RunStore (ADR-0003) so it surfaces on the
    project's artifacts/dashboard — the run is otherwise ephemeral. Mapped onto the existing
    RunRecord shape (no schema change): citations split by boundary, missing steps as gaps."""
    from sentinel.artifacts.schemas import Boundary
    from sentinel.memory.schema import RunRecord

    public = sum(1 for c in result.citations if c.boundary == Boundary.PUBLIC)
    private = sum(1 for c in result.citations if c.boundary == Boundary.PRIVATE)
    # Account entity: the extracted org name from a self_profile-style artifact. When no artifact
    # carries an org (product_research, govt multi-dept, etc.), fall back to the PROJECT name — the
    # raw objective used to land here and turned the Accounts/focus pages into a junk list of full
    # sentences ("i want new laptop under 500000 inr…" as an "account", e2e audit 2026-06-12). An
    # account is an organisation's accumulated memory; a sentence is not an organisation.
    _payload = result.dashboard_payload or {}
    _org = ""
    if isinstance(_payload.get("map"), dict):
        _org = str(_payload["map"].get("org") or "")
    elif "artifacts" in _payload:
        _sp = next((v for v in (_payload["artifacts"] or {}).values()
                    if isinstance(v, dict) and "org" in v), None)
        _org = str(_sp.get("org") or "") if _sp else ""
    if _org.strip() and _org.strip() != task.objective:
        _entity = _org.strip()
    else:
        _proj = ProjectStore().get_project(task.project_id)
        _entity = (_proj.name if _proj and _proj.name else task.objective)
    rec = RunRecord(
        entity=_entity, target=_entity, mode="orchestrated", backend=backend,
        kind=task.domain.name, public=public, private=private, gaps=len(result.missing_inputs),
        reference=", ".join(result.artifacts), sources=list(result.citations),
        project_id=task.project_id,
        task_id=task.id,
        finding_texts=_extract_finding_texts(result),
    )
    RunStore().save(rec)
    # G-06: save entity relations from compare/competitor artifacts (fail-soft).
    try:
        from sentinel.memory.schema import EntityRelation
        from sentinel.memory.store import MemoryStore
        artifacts = (result.dashboard_payload or {}).get("artifacts", {})
        store = MemoryStore()
        if "compare" in artifacts:
            cm = artifacts["compare"]
            subj = str(cm.get("subject") or "").strip()
            rival = str(cm.get("rival") or "").strip()
            if subj and rival:
                store.upsert_relation(EntityRelation(
                    from_entity=subj, rel_type="competitor", to_entity=rival,
                    project_id=task.project_id,
                ))
        if "competitor" in artifacts:
            bc = artifacts["competitor"]
            rival = str(bc.get("target") or "").strip()
            us = str(task.objective).split(" and ")[0].replace("Profile ", "").strip()
            if rival and us:
                store.upsert_relation(EntityRelation(
                    from_entity=us, rel_type="competitor", to_entity=rival,
                    project_id=task.project_id,
                ))
        # HIGH-05: domain artifacts → warm entity graph so get_related() is non-empty on
        # subsequent runs for the same entity.  field map mirrors each domain's schema.
        _DOMAIN_ENTITY_FIELDS = {
            "software": "target",
            "finance": "target",
            "academic": "topic",
            "nutrition": "topic",
            "travel": "destination",
        }
        for _art_key, _field in _DOMAIN_ENTITY_FIELDS.items():
            if _art_key not in artifacts:
                continue
            _art = artifacts[_art_key]
            if not isinstance(_art, dict):
                continue
            _entity = str(_art.get(_field) or "").strip()
            if not _entity:
                continue
            store.upsert_relation(EntityRelation(
                from_entity=_entity,
                rel_type=f"{_art_key}_profile",
                to_entity=task.objective,
                project_id=task.project_id,
            ))
            if _art_key == "software":
                for _alt in (_art.get("alternatives") or []):
                    _alt_s = str(_alt).strip()
                    if _alt_s and _alt_s.lower() != _entity.lower():
                        store.upsert_relation(EntityRelation(
                            from_entity=_entity,
                            rel_type="competitor",
                            to_entity=_alt_s,
                            project_id=task.project_id,
                        ))
    except Exception:
        pass

    # Auto-ingest research artifacts into the KB per artifact type so each appears
    # as a labelled, searchable entry on the Knowledge tab (fail-soft always).
    import threading as _threading

    def _artifact_to_text(art_key: str, art: dict) -> str:
        """Flatten an artifact dict into readable text for KB embedding."""
        lines: list[str] = [f"## {art_key.upper().replace('_', ' ')}"]
        if art_key == "self_profile":
            lines.append(f"Organization: {art.get('org', '')}")
            for p in art.get("products", []):
                lines.append(f"\nProduct: {p.get('name', '')} ({p.get('category', '')})")
                if p.get("description"):
                    lines.append(f"Description: {p['description']}")
                if p.get("price_range"):
                    lines.append(f"Price range: {p['price_range']}")
                specs = p.get("specs") or {}
                if isinstance(specs, dict):
                    lines.extend(f"{k}: {v}" for k, v in specs.items())
                elif isinstance(specs, list):
                    lines.extend(f"Spec: {s}" for s in specs)
                st = p.get("strengths") or []
                if st:
                    lines.append("Strengths: " + (", ".join(st) if isinstance(st, list) else str(st)))
            for field in ("positioning", "pricing_signals", "recent_momentum"):
                if art.get(field):
                    lines.append(f"\n{field.replace('_', ' ').title()}: {art[field]}")
        elif art_key == "competitor":
            lines.append(f"Competitor: {art.get('target', '')}")
            lines.append(f"Summary: {art.get('one_line_summary', '')}")
            for field in ("positioning", "strengths", "pricing_signals", "recent_momentum"):
                val = art.get(field)
                if val:
                    lines.append(f"{field.replace('_', ' ').title()}: {str(val)[:600]}")
            bc = art.get("battle_card") or art.get("battlecard") or {}
            if isinstance(bc, dict):
                for k, v in bc.items():
                    lines.append(f"Battle card — {k}: {str(v)[:300]}")
        elif art_key in ("compare", "comparison_matrix"):
            lines.append(f"Subject: {art.get('subject', '')}  vs  Rival: {art.get('rival', '')}")
            for axis in art.get("axes", []):
                lines.append(f"\n### {axis.get('axis', '')}")
                lines.append(f"Ours: {axis.get('ours', '')}")
                lines.append(f"Rival: {axis.get('rival') or axis.get('theirs', '')}")
                lines.append(f"Verdict: {axis.get('verdict', '')} — {axis.get('win_rationale') or axis.get('note', '')}")
            if art.get("recommendation"):
                lines.append(f"\nRecommendation: {art['recommendation']}")
            if art.get("assessment"):
                lines.append(f"\nAssessment: {art['assessment']}")
        elif art_key == "govt_proposal":
            lines.append(f"Client: {art.get('client', '')}  |  Vendor: {art.get('vendor', '')}")
            lines.append(f"Summary: {art.get('one_line_summary', '')}")
            if art.get("executive_summary"):
                lines.append(f"\nExecutive Summary:\n{art['executive_summary']}")
            for f_name in ("client_challenges", "vendor_capabilities"):
                for f in art.get(f_name, []):
                    if isinstance(f, dict):
                        lines.append(f"{f_name.replace('_', ' ').title()}: {f.get('text', '')}")
            for dm in art.get("department_mappings", []):
                if isinstance(dm, dict):
                    lines.append(f"\nDepartment: {dm.get('department', '')}")
                    lines.append(f"  Challenge: {dm.get('challenge', '')}")
                    lines.append(f"  Solution: {dm.get('solution', '')}")
                    lines.append(f"  Impact: {dm.get('impact', '')}")
            if art.get("competitive_advantage"):
                lines.append(f"\nCompetitive Advantage: {art['competitive_advantage']}")
            if art.get("pilot_plan"):
                lines.append(f"\nPilot Plan: {art['pilot_plan']}")
        elif art_key == "product_research":
            lines.append(f"Criteria: {art.get('criteria', '')}")
            lines.append(f"Summary: {art.get('one_line_summary', '')}")
            lines.append(f"Winner: {art.get('winner', '')} — {art.get('winner_rationale', '')}")
            for p in art.get("products_found", []):
                if isinstance(p, dict):
                    lines.append(
                        f"\nProduct: {p.get('name', '')} ({p.get('brand', '')}) — "
                        f"₹{p.get('price', '?')} — RAM: {p.get('ram', '')} / "
                        f"Storage: {p.get('storage', '')} — Score: {p.get('score', '')}/10"
                    )
                    pros = p.get("pros") or []
                    cons = p.get("cons") or []
                    if pros:
                        lines.append(f"  Pros: {', '.join(pros) if isinstance(pros, list) else pros}")
                    if cons:
                        lines.append(f"  Cons: {', '.join(cons) if isinstance(cons, list) else cons}")
            if art.get("value_ranking"):
                lines.append(f"\nValue ranking: " + " > ".join(art["value_ranking"]))
            if art.get("assessment"):
                lines.append(f"\nAssessment: {art['assessment']}")
        else:
            def _flat(d: dict, prefix: str = "") -> list[str]:
                out: list[str] = []
                for k, v in d.items():
                    key = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, (str, int, float)):
                        out.append(f"{key}: {v}")
                    elif isinstance(v, list):
                        for item in v[:5]:
                            if isinstance(item, str):
                                out.append(f"{key}: {item}")
                            elif isinstance(item, dict):
                                out.extend(_flat(item, key))
                    elif isinstance(v, dict):
                        out.extend(_flat(v, key))
                return out
            lines.extend(_flat(art))
        return "\n".join(lines)

    def _auto_kb_ingest() -> None:
        try:
            from sentinel.kb import SourceType
            arts = (result.dashboard_payload or {}).get("artifacts") or {}
            if not arts:
                # Fallback to finding_texts if no per-artifact data
                text = "\n\n".join(rec.finding_texts) if rec.finding_texts else ""
                if not text.strip():
                    return
                manager = KBManager(_kb_data_dir())
                source = manager.add_text(task.project_id, text, _entity[:120], SourceType.ARTIFACT)
                KBStore().save({
                    "id": source.id, "project_id": task.project_id, "url": source.url,
                    "source_type": source.source_type.value, "status": source.status.value,
                    "chunk_count": source.chunk_count, "error": source.error,
                })
                return
            manager = KBManager(_kb_data_dir())
            for art_key, art in arts.items():
                if not isinstance(art, dict):
                    continue
                text = _artifact_to_text(art_key, art)
                if not text.strip():
                    continue
                org = art.get("org") or art.get("target") or art.get("subject") or _entity
                label = f"{art_key}: {org}"
                source = manager.add_text(task.project_id, text, label, SourceType.ARTIFACT)
                KBStore().save({
                    "id": source.id, "project_id": task.project_id, "url": source.url,
                    "source_type": source.source_type.value, "status": source.status.value,
                    "chunk_count": source.chunk_count, "error": source.error,
                })
        except Exception:
            pass  # KB ingestion is always fail-soft

    _threading.Thread(target=_auto_kb_ingest, daemon=True).start()

    # Minimal Semantic memory: extract key facts from structured artifact fields and
    # store them as MemoryType.SEMANTIC_FACT entries scoped to this project.
    try:
        from sentinel.memory.store import MemoryStore as _MemStore
        _artifacts = (result.dashboard_payload or {}).get("artifacts") or {}
        _mem = _MemStore()
        for _art_key, _art in _artifacts.items():
            if not isinstance(_art, dict):
                continue
            if _art_key == "product_research":
                winner = str(_art.get("winner") or "").strip()
                rationale = str(_art.get("winner_rationale") or "").strip()
                summary = str(_art.get("one_line_summary") or "").strip()
                if winner:
                    fact = f"Winner: {winner}"
                    if rationale:
                        fact += f" — {rationale[:120]}"
                    _mem.write_semantic_fact(task.project_id, winner, fact, "product_research")
                if summary:
                    _mem.write_semantic_fact(task.project_id, task.objective[:80], summary, "product_research")
            elif _art_key == "govt_proposal":
                client = str(_art.get("client") or "").strip()
                one_line = str(_art.get("one_line_summary") or "").strip()
                if client and one_line:
                    _mem.write_semantic_fact(task.project_id, client, one_line, "govt_proposal")
            elif _art_key == "self_profile":
                org = str(_art.get("org") or "").strip()
                products = [p.get("name", "") for p in (_art.get("products") or [])
                            if isinstance(p, dict) and p.get("name")]
                if org and products:
                    _mem.write_semantic_fact(
                        task.project_id, org,
                        f"{org} products: {', '.join(products[:5])}", "self_profile",
                    )
            elif _art_key == "compare":
                winner = str(_art.get("winner") or _art.get("winner_entity") or "").strip()
                subject = str(_art.get("subject") or "").strip()
                rival = str(_art.get("rival") or "").strip()
                if winner and subject:
                    _mem.write_semantic_fact(
                        task.project_id, subject,
                        f"{winner} wins vs {rival}" if rival else f"Winner: {winner}",
                        "compare",
                    )
    except Exception:
        pass  # semantic extraction is always fail-soft


def _plan_is_stale(task, plan) -> bool:
    """True when a saved plan no longer matches what the deterministic template would now produce for a
    recognised objective — e.g. a lopsided ``[competitor, competitor]`` chain minted before the template
    landed (the duplicate-battlecard bug). Returns False for novel objectives the template doesn't
    recognise (``_template_plan`` → None), so genuinely dynamic plans are never second-guessed."""
    from sentinel.agent.orchestrator_planner import _template_plan

    expected = _template_plan(task)
    if expected is None:
        return False
    return [s.capability for s in plan.steps] != [s.capability for s in expected.steps]


def _persona_for(name: str, *, reading_level: str = "", tone: str = "",
                 format: str = "", source_policy: str = "", domain: str = "") -> Persona:
    """Build the full audience profile from the form: built-in registry profile (student → K-12
    study guide, doctor → peer-reviewed-only clinical brief, …) OR a saved persona from the library
    (/personas) resolved by name, + non-blank per-task overrides from the customise-persona fields.
    ``auto`` lets the agent pick from the domain (DOMAIN_DEFAULT_PERSONA) — marked on the Persona so
    the UI can show the pick was the agent's. Unknown/blank names degrade to the default enterprise
    reader rather than 500-ing (the form constrains the options, but a hand-typed query must degrade
    safely)."""
    from sentinel.artifacts.schemas import auto_persona_name, persona_for
    from sentinel.memory.store import PersonaStore

    auto = (name or "").strip().lower() == "auto"
    if auto:
        name = auto_persona_name(domain)
    try:
        extra = PersonaStore().profiles_by_name()
    except Exception:  # the library is an enhancement — its absence must never block planning
        extra = {}
    p = persona_for(name, reading_level=reading_level, tone=tone,
                    format=format, source_policy=source_policy, extra_profiles=extra)
    if auto:
        p.auto_selected = True
    return p


@app.get("/projects/{project_id}/plan", response_class=HTMLResponse)
async def plan_review(project_id: str, objective: str = "", domain: str = "market",
                      persona: str = "enterprise", backend: str = "",
                      user_id: str = "", context: str = "",
                      client_url: str = "",
                      reading_level: str = "", tone: str = "",
                      format: str = "", source_policy: str = "") -> str:
    proj = ProjectStore().get_project(project_id)
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    objective = objective.strip()
    if not objective:
        return render.error_page("An objective is required to plan a task.", backend=_active())
    store = ProjectStore()
    dom = domain.strip() or "market"
    # The full audience profile: named registry/library profile + any customise-persona overrides
    # (AC-17); "auto" resolves from the domain and is flagged as the agent's pick.
    task_persona = _persona_for(persona, reading_level=reading_level, tone=tone,
                                format=format, source_policy=source_policy, domain=dom)
    # Reuse an existing task with the same objective+domain instead of piling up duplicates on every
    # re-plan (the Tasks list stays meaningful). A fresh objective makes a new task.
    task = next((t for t in store.tasks_for_project(project_id)
                 if t.objective == objective and t.domain.name == dom), None)
    if task is None:
        now = utcnow().isoformat()
        task = Task(id=f"task-{now}", project_id=project_id, objective=objective,
                    domain=Domain(name=dom), persona=task_persona, created_at=now,
                    user_id=user_id.strip() or None,
                    context=context.strip() or None)
    else:
        task.persona = task_persona
        if user_id.strip():
            task.user_id = user_id.strip()
        if context.strip():
            task.context = context.strip()
    cloud_allowed = _cloud_allowed_for(proj)

    # KB enrichment: if a client_url was supplied, start a background crawl so agents have
    # real content from the client's site before the plan runs.  The crawl runs in parallel
    # with plan generation — by the time the user hits "Approve", it's usually done.
    if client_url.strip():
        try:
            _client_url_clean = validate_crawl_url(client_url.strip())
            kb_store = KBStore()
            _existing = [s for s in kb_store.list_for_project(project_id)
                         if s.get("url") == _client_url_clean]
            if not _existing:
                from sentinel.kb.schema import KBSource as _KBS, SourceType as _ST
                _src = _KBS(project_id=project_id, url=_client_url_clean,
                            source_type=_ST.WEB)
                kb_store.save({
                    "id": _src.id, "project_id": project_id, "url": _client_url_clean,
                    "source_type": "web", "status": "pending", "chunk_count": 0, "error": None,
                })
                import asyncio as _asyncio
                import threading as _t2

                async def _crawl_client(src_id: str, pid: str, u: str) -> None:
                    result = await KBManager(_kb_data_dir()).add_source(pid, u, SourceType.WEB)
                    KBStore().update_status(src_id, result.status.value,
                                            result.chunk_count, result.error)

                def _run_crawl(src_id: str, pid: str, u: str) -> None:
                    _asyncio.run(_crawl_client(src_id, pid, u))

                _t2.Thread(target=_run_crawl, args=(_src.id, project_id, _client_url_clean),
                           daemon=True).start()
        except Exception:
            pass  # KB enrichment is always fail-soft

    # Validate and apply user-chosen backend, honouring sovereignty (never allow cloud when blocked).
    backend = backend.strip().lower()
    if backend not in ("gemini", "vllm"):
        backend = ""
    if backend == "gemini" and not cloud_allowed:
        backend = "vllm"  # governance override: can't allow cloud when project is on_prem_required
    try:
        proposal = await plan_task(task, AgentRegistry(), cloud_allowed=cloud_allowed)
        task.status = "planned"             # the plan exists now (reflected in the Tasks list)
        task.plan_id = proposal.plan.id
        store.save_task(task)
        store.save_plan(proposal.plan)  # persist so Approve can reload the exact plan (no re-plan)
        trace: list[str] = []           # the execution log: which step ran on which agent, fail-soft notes
        policy = _run_policy(cloud_allowed)
        if backend:
            policy["backend"] = backend
        from sentinel.agent.governance import effective_search_provider as _esp
        policy["search_provider"] = _esp(get_config(), allow_cloud=cloud_allowed, backend=policy["backend"])
        outcome = await gate_proposal(
            proposal, autonomy=proj.settings.autonomy, seeds=_plan_seeds(task, proposal.plan, proj),
            cfg=get_config(), cloud_allowed=cloud_allowed, trace=trace, **policy,
            persona=task.persona, grade=_grade_sample(), grade_objective=task.objective,
            project_id=task.project_id,
            user_id=task.user_id or None,
            handoff_id=task.handoff_id or None,
        )
        if outcome.ran and outcome.result is not None:
            task.status = "failed" if outcome.result.degraded else "done"   # honest run state
            task.result = outcome.result    # persist on the task so it lives at the task's own URL
            store.save_task(task)
            _persist_run(task, outcome.result, policy["backend"])
    except Exception as exc:  # a live demo surfaces the failure rather than a blank 500
        return render.error_page(f"{type(exc).__name__}: {exc}", backend=_active())
    # PRG: carry the backend choice in the redirect so task_detail can pre-fill the approve form.
    be_qs = f"&backend={quote(backend)}" if backend else ""
    return RedirectResponse(
        url=f"/projects/{project_id}/tasks/{quote(task.id)}?from_plan=1{be_qs}", status_code=303)


@app.get("/projects/{project_id}/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(project_id: str, task_id: str, backend: str = "",
                      from_plan: str = "", client_url: str = "") -> str:
    """The canonical per-task page (PRG target): its plan DAG + assigned agents + call boundaries,
    the Approve & run control, and — once run — the persisted Result + execution trace. Both planning
    (GET /plan) and running (POST .../run) redirect here, so each task's output lives at its own URL
    (refresh-safe, bookmarkable) instead of being trapped in a POST response body."""
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return render.not_found_page(what=f"task {task_id}", backend=_active())
    # A run is in flight for this task: render the live per-step timeline (polls status.json,
    # reloads into the result when the run lands). Uses the in-memory plan the DAG is mutating.
    entry = _ACTIVE_RUNS.get(task_id)
    if entry is not None and entry.get("state") == "running":
        _be = entry.get("backend") or "vllm"
        return render.task_running_page(
            task=task, plan=entry["plan"], backend=_active(),
            step_models={s.id: _step_models(s.capability, _be) for s in entry["plan"].steps})
    plan = store.plan_for_task(task_id)
    replan = (f"/projects/{project_id}/plan?objective={quote(task.objective)}"
              f"&domain={quote(task.domain.name)}&persona={quote(task.persona.name)}")
    if plan is None:
        # No saved plan (a legacy task, or one whose plan was lost to the old id-collision). Recover by
        # re-planning it from its own objective/domain/persona rather than dead-ending on an error.
        return RedirectResponse(url=replan, status_code=303)
    if _plan_is_stale(task, plan):
        # A plan minted before the deterministic template (e.g. the lopsided 2×competitor chain that
        # produced duplicate battlecards). Re-plan into the canonical chain rather than re-show garbage.
        return RedirectResponse(url=replan, status_code=303)
    proj = store.get_project(project_id)
    autonomy = proj.settings.autonomy if proj is not None else "propose"
    result = task.result
    # Sanitise backend: only carry forward a valid choice from the plan redirect.
    selected_be = backend.strip().lower() if backend.strip().lower() in ("gemini", "vllm") else ""
    try:
        kb_sources = KBStore().list_for_project(project_id)
    except Exception:
        kb_sources = []
    return render.plan_review_page(task=task, proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy=autonomy, backend=_active(),
                                   ran=result is not None, result=result,
                                   selected_backend=selected_be,
                                   kb_sources=kb_sources)


@app.post("/projects/{project_id}/tasks/{task_id}/delete")
async def delete_task_route(project_id: str, task_id: str) -> RedirectResponse:
    """Tidy the Tasks list: drop a task (and its plan). Always 303 back to the Research tab."""
    try:
        ProjectStore().delete_task(task_id)
    except Exception:
        pass  # fail-soft: a bad delete still returns to the page, never a 500
    return RedirectResponse(url=f"/projects/{project_id}/tasks", status_code=303)


@app.post("/projects/{project_id}/tasks/{task_id}/feedback")
async def task_feedback_route(
    project_id: str,
    task_id: str,
    signal: int = Form(...),
    note: str = Form(""),
) -> JSONResponse:
    """Record a thumbs-up (+1) or thumbs-down (-1) on a task result.

    The signal is persisted in ``user_feedback`` and immediately applied to the entity's
    SM-2 memory entries: +1 reinforces, -1 weakens. Returns JSON so the fetch-based UI
    can update the button state without a full page reload.
    """
    if signal not in (1, -1):
        return JSONResponse({"ok": False, "error": "signal must be +1 or -1"}, status_code=400)
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None or task.project_id != project_id:
        return JSONResponse({"ok": False, "error": "task not found"}, status_code=404)
    from sentinel.memory.store import FeedbackStore

    FeedbackStore().save(
        project_id=project_id,
        task_id=task_id,
        run_id=task_id,          # task_id is a stable per-task surrogate for the latest run
        entity=task.objective,
        signal=signal,
        note=note.strip() or None,
    )
    return JSONResponse({"ok": True, "signal": signal})


# Live run registry: task_id → the in-memory Plan the DAG mutates (step.status/started_at) plus
# the run state. Lets the status endpoint serve real per-step progress without touching dag.py.
# In-process only (single-worker deploy); the status endpoint falls back to the DB task.status.
_ACTIVE_RUNS: dict[str, dict] = {}


def _step_models(capability: str, backend: str) -> str:
    """Human label for the model(s) one capability step runs on — mirrors the two-pass split in
    dag.py (``StepSpec.tool`` steps ride the 12B tools model; synthesis/strategy ride the 26B
    reasoner) so the live timeline shows real agent→model handovers, not a generic spinner."""
    if backend == "gemini":
        return "Gemini"
    try:
        from sentinel.agent.modes.spec import SKILL_SPECS
        spec = SKILL_SPECS.get(capability)
    except Exception:                                              # never break the status poller
        spec = None
    if spec is not None and any(getattr(s, "tool", None) for s in spec.steps):
        return "Gemma-12B tools → Gemma-26B reasoning"             # two-pass capability
    return "Gemma-26B reasoning"                                   # synth-only (compare/strategy/minted)


async def _execute_run(task, plan, proj, override_backend: str) -> None:
    """The actual run (background task): gate → DAG → persist Result. Updates _ACTIVE_RUNS so the
    live timeline on the task page can poll progress; never raises (state carries the error)."""
    store = ProjectStore()
    entry = _ACTIVE_RUNS[task.id]
    cloud_allowed = _cloud_allowed_for(proj) if proj is not None else True
    proposal = PlanProposal(plan=plan, created_specs=[])
    try:
        trace: list[str] = []
        policy = _run_policy(cloud_allowed)
        # Apply user's explicit backend choice, honouring sovereignty.
        if override_backend == "vllm-26b":
            policy["backend"] = "vllm"
            policy["vllm_model"] = "gemma-4-27b-it"
        elif override_backend in ("gemini", "vllm") and (cloud_allowed or override_backend != "gemini"):
            policy["backend"] = override_backend
        # Re-derive search_provider now that backend is finalised — the initial _run_policy call used
        # the config default (vllm), so google_search would never be attached even when the user
        # picked gemini. Re-computing here ensures the search provider matches the resolved backend.
        from sentinel.agent.governance import effective_search_provider as _esp
        policy["search_provider"] = _esp(get_config(), allow_cloud=cloud_allowed, backend=policy["backend"])
        entry["backend"] = policy["backend"]   # resolved truth — the timeline labels models off this
        outcome = await gate_proposal(
            proposal, autonomy="autonomous", seeds=_plan_seeds(task, plan, proj),
            cfg=get_config(), cloud_allowed=cloud_allowed, trace=trace, **policy,
            persona=task.persona, grade=_grade_sample(), grade_objective=task.objective,
            project_id=task.project_id,
            user_id=task.user_id or None,
            handoff_id=task.handoff_id or None,
        )
        if outcome.ran and outcome.result is not None:
            task.status = "failed" if outcome.result.degraded else "done"   # reflect the run in the list
            task.result = outcome.result      # persist on the task so it lives at the task's own URL
            store.save_task(task)
            _persist_run(task, outcome.result, policy["backend"])
            store.save_plan(plan)            # flush in-memory step statuses (done/failed) to DB
            entry["state"] = task.status
        else:
            task.status = "failed"
            store.save_task(task)
            entry["state"] = "failed"
            entry["error"] = "Run was gated or produced no result."
    except Exception as exc:
        task.status = "failed"
        try:
            store.save_task(task)
        except Exception:
            pass
        entry["state"] = "failed"
        entry["error"] = f"{type(exc).__name__}: {exc}"


async def _approve_and_run(task_id: str, override_backend: str = "",
                           extra_context: str = "",
                           background_tasks: BackgroundTasks | None = None) -> RedirectResponse | str:
    """Human approval of a proposed plan: reload the persisted plan, kick the run off in the
    background (after the redirect is sent), then (PRG) land on the task's own URL — which renders
    a live per-step timeline while the run is in flight and the persisted Result once it lands.
    No blocking POST, no popup. BackgroundTasks (not asyncio.create_task) so the run also completes
    deterministically under TestClient."""
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return render.not_found_page(what=f"task {task_id}", backend=_active())
    plan = store.plan_for_task(task_id)
    if plan is None:
        return render.error_page("No plan found for this task — re-plan it first.", backend=_active())
    if _ACTIVE_RUNS.get(task_id, {}).get("state") == "running":
        # Double-submit guard: one run per task at a time — just land on the live timeline.
        return RedirectResponse(url=f"/projects/{task.project_id}/tasks/{quote(task.id)}", status_code=303)
    # Re-run steering prompt: persist onto task.context so _plan_seeds injects it into every
    # agent's vertical_context. The marker block is REPLACED (not stacked) on repeated re-runs,
    # so the original project/task context never snowballs.
    if extra_context.strip():
        _marker = "\n\n[Re-run guidance] "
        base = (task.context or "").split(_marker, 1)[0]
        task.context = (base + _marker + extra_context.strip()).strip()
    # Reset step statuses so a re-run doesn't skip steps that completed on a prior attempt.
    for _s in plan.steps:
        _s.status = "pending"
        _s.started_at = None
        _s.finished_at = None
    task.status = "running"
    store.save_task(task)
    proj = store.get_project(task.project_id)
    # Initial backend guess (override wins, else the active default); _execute_run overwrites it
    # with the governance-resolved policy backend once the background task starts.
    _backend_guess = "vllm" if override_backend == "vllm-26b" else (
        override_backend if override_backend in ("gemini", "vllm") else _active())
    _ACTIVE_RUNS[task_id] = {"plan": plan, "state": "running", "error": None,
                             "backend": _backend_guess}
    if background_tasks is not None:
        background_tasks.add_task(_execute_run, task, plan, proj, override_backend)
    else:
        await _execute_run(task, plan, proj, override_backend)   # no carrier — run inline (CLI/tests)
    return RedirectResponse(url=f"/projects/{task.project_id}/tasks/{quote(task.id)}", status_code=303)


@app.get("/projects/{project_id}/tasks/{task_id}/status.json")
async def task_run_status(project_id: str, task_id: str) -> JSONResponse:
    """Live progress for the task-page timeline. Serves the in-memory plan the DAG is mutating
    (real per-step statuses); falls back to the persisted task when this process holds no run
    (e.g. after a restart) so the poller always terminates."""
    entry = _ACTIVE_RUNS.get(task_id)
    if entry is not None:
        backend = entry.get("backend") or "vllm"
        steps = [
            {
                "id": s.id, "capability": s.capability,
                # dag.py stamps started_at but leaves status='pending' until done/failed —
                # derive 'running' so the timeline can spin the in-flight step(s).
                "status": (s.status if s.status != "pending"
                           else ("running" if s.started_at else "pending")),
                # Who's working and on what — drives the active-agent banner + handover animation.
                "agent": s.agent_spec_id or s.capability,
                "model": _step_models(s.capability, backend),
            }
            for s in entry["plan"].steps
        ]
        return JSONResponse({"state": entry["state"], "error": entry.get("error"),
                             "backend": backend, "steps": steps})
    task = ProjectStore().get_task(task_id)
    if task is None:
        return JSONResponse({"state": "unknown", "error": "task not found", "steps": []}, status_code=404)
    # No live entry (restart mid-run leaves status='running' in the DB — report failed so the
    # poller stops; the user can re-run).
    state = "failed" if task.status == "running" else task.status
    return JSONResponse({"state": state, "error": None, "steps": []})


@app.post("/projects/{project_id}/tasks/{task_id}/run", response_model=None)
async def run_task_route(project_id: str, task_id: str,
                         background_tasks: BackgroundTasks,
                         backend: str = Form(""),
                         context: str = Form("")) -> RedirectResponse | str:
    """Per-task run route (the Approve & run control posts here) — each task runs at its own URL."""
    return await _approve_and_run(task_id, override_backend=backend.strip().lower(),
                                  extra_context=context, background_tasks=background_tasks)


@app.post("/projects/run-plan", response_model=None)
async def run_plan_route(background_tasks: BackgroundTasks,
                         task_id: str = Form(...),
                         backend: str = Form(""),
                         context: str = Form("")) -> RedirectResponse | str:
    """Back-compat alias for the per-task run route (kept so existing forms/links keep working)."""
    return await _approve_and_run(task_id, override_backend=backend.strip().lower(),
                                  extra_context=context, background_tasks=background_tasks)


@app.post("/projects/{project_id}/tasks/{task_id}/chat")
async def task_chat(project_id: str, task_id: str,
                    message: str = Form(...)):
    """Conversational refinement on a completed task — Claude.ai-style post-run chat.

    Streams the reply token-by-token (chunked text/plain) so the UI renders it
    progressively like ChatGPT/Claude, instead of blocking on the full response.
    """
    from fastapi.responses import JSONResponse as _J
    from fastapi.responses import StreamingResponse as _Stream
    import litellm as _litellm

    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return _J({"error": "Task not found"}, status_code=404)

    # Build system context from the task's artifact
    artifact_ctx = ""
    if task.result and task.result.dashboard_payload:
        payload = task.result.dashboard_payload
        arts = payload.get("artifacts") or payload
        if isinstance(arts, dict):
            import json as _json
            try:
                artifact_ctx = _json.dumps(arts, indent=2)[:6000]
            except Exception:
                artifact_ctx = str(arts)[:3000]

    system_prompt = (
        f"You are a research assistant helping refine and discuss findings from a Sentinel research task.\n"
        f"Task objective: {task.objective}\n"
        f"Domain: {task.domain.name}\n"
    )
    if artifact_ctx:
        system_prompt += f"\nResearch findings (summarized):\n{artifact_ctx}\n"
    system_prompt += (
        "\nAnswer questions, suggest improvements, and help the user act on these findings. "
        "Be concise and cite specific data from the findings where relevant."
    )

    # Build message history
    history = list(getattr(task, "chat", []) or [])
    history.append({"role": "user", "content": message.strip()})

    messages = [{"role": "system", "content": system_prompt}] + history

    async def _gen():
        """Yield reply deltas as they arrive; persist the full turn once complete."""
        chunks: list[str] = []
        try:
            stream = await _litellm.acompletion(
                model=f"gemini/{get_config().backend.gemini.model}",
                messages=messages,
                api_key=os.environ.get("GOOGLE_API_KEY"),
                max_tokens=1024,
                drop_params=True,
                stream=True,
            )
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                delta = (getattr(choices[0].delta, "content", "") or "") if choices else ""
                if delta:
                    chunks.append(delta)
                    yield delta
        except Exception as exc:
            yield f"\n[LLM error: {type(exc).__name__}: {exc}]"
        finally:
            reply = "".join(chunks)
            if reply:
                history.append({"role": "assistant", "content": reply})
                task.chat = history
                store.save_task(task)

    return _Stream(_gen(), media_type="text/plain; charset=utf-8")


@app.get("/projects/{project_id}/tasks/{task_id}/export.html", response_class=HTMLResponse)
async def export_task_html(project_id: str, task_id: str) -> str:
    """Download a clean standalone HTML report — fully formatted, no raw JSON."""
    from html import escape as _esc
    from sentinel.web import render as _render
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None or task.result is None:
        return HTMLResponse("<html><body>No result found for this task.</body></html>", status_code=404)

    result = task.result
    arts = (result.dashboard_payload or {}).get("artifacts", {}) or {}

    # Reuse the same _artifact_html renderer used in the live UI —
    # strips the dark-mode CSS classes via inline-style substitution for print
    arts_html = ""
    for key, art in arts.items():
        raw = _render._artifact_html(key, art)
        # Replace CSS variables with print-safe values so it renders in any browser
        raw = (raw
               .replace("var(--accent-2)", "#1a56db")
               .replace("var(--card)", "#fff")
               .replace("var(--line)", "#e5e7eb")
               .replace("var(--muted)", "#6b7280")
               .replace("var(--public)", "#16a34a")
               .replace("var(--good,#16a34a)", "#16a34a")
               .replace("var(--warn,#ca8a04)", "#ca8a04")
               .replace("var(--bad,#dc2626)", "#dc2626")
               .replace("var(--bad)", "#dc2626")
               .replace("var(--ink)", "#1a1a1a")
               .replace("var(--ink-3)", "#6b7280")
               .replace("var(--border)", "#e5e7eb")
               .replace("var(--fg-2)", "#6b7280")
               .replace("var(--accent-line)", "#eff6ff")
               .replace("var(--rail)", "#f9fafb")
               .replace("var(--panel)", "#f3f4f6")
               .replace("var(--mono)", "monospace")
               # Translate card/section-h/find/note/pill/badge class patterns
               .replace("class='card'", "style='border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:10px 0'")
               .replace("class='note'", "style='color:#374151;font-size:14px;line-height:1.6'")
               .replace("class='find'", "style='padding-left:18px;margin:4px 0'")
               .replace("class='pill'", "style='display:inline-block;background:#f3f4f6;border-radius:99px;padding:2px 10px;font-size:12px;margin:2px'")
               .replace("class='badge'", "style='display:inline-block;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:600'")
               .replace("class='section-h'", "style='margin:12px 0 6px'")
               .replace("class='tag'", "style='font-size:11px;opacity:.7'")
               )
        arts_html += arts_html and "<hr style='border:0;border-top:1px solid #e5e7eb;margin:20px 0'>" or ""
        arts_html += raw

    cites_html = ""
    if result.citations:
        cites_html = "<h2 style='font-size:15px;border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:24px'>📎 Sources</h2><ul style='padding-left:20px'>"
        for c in result.citations:
            url = getattr(c, "url", "") or ""
            label = getattr(c, "label", url) or url
            cites_html += (f"<li style='margin:4px 0'><a href='{_esc(url)}' style='color:#1a56db'>{_esc(label)}</a></li>"
                           if url else f"<li style='margin:4px 0'>{_esc(label)}</li>")
        cites_html += "</ul>"

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{_esc(task.objective[:80])}</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#1a1a1a;line-height:1.6}}
h1{{font-size:22px;margin-bottom:4px;color:#111}}
h2,h3{{color:#222}}
h3{{font-size:15px;margin:0 0 8px}}
.meta{{font-size:13px;color:#6b7280;margin-bottom:28px;padding-bottom:12px;border-bottom:1px solid #e5e7eb}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:13px}}
td,th{{border:1px solid #e5e7eb;padding:8px 10px;text-align:left}}
th{{background:#f9fafb;font-weight:600;color:#374151}}
a{{color:#1a56db;text-decoration:none}}
a:hover{{text-decoration:underline}}
ul{{padding-left:20px}} li{{margin:4px 0;font-size:13px}}
p{{margin:4px 0 8px;font-size:14px;color:#374151}}
details summary{{cursor:pointer;font-size:13px;color:#6b7280;padding:4px 0}}
@media print{{body{{margin:20px;padding:0}}}}
</style></head>
<body>
<h1>{_esc(task.objective)}</h1>
<div class="meta">
  <strong>Domain:</strong> {_esc(task.domain.name)} &nbsp;·&nbsp;
  <strong>Persona:</strong> {_esc(task.persona.name)} ({_esc(_render._persona_tip(task.persona))}) &nbsp;·&nbsp;
  {_esc((task.created_at or '')[:19].replace('T', ' '))} UTC
</div>
<h2 style='font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px;margin-bottom:12px'>📊 Summary</h2>
<p style='font-size:15px'>{_esc(_render._clean_text(result.summary or ''))}</p>
<h2 style='font-size:16px;border-bottom:1px solid #ddd;padding-bottom:4px;margin:24px 0 12px'>📦 Deliverables</h2>
{arts_html}
{cites_html}
</body></html>"""
    from fastapi.responses import Response as _Resp
    return _Resp(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename=\"sentinel-{task_id[:8]}.html\""},
    )


@app.post("/run", response_class=HTMLResponse)
async def run(
    target: str = Form(...),
    mode: str = Form("competitor"),
    vertical: str = Form(""),
    backend: str = Form(""),
) -> str:
    from sentinel.agent.orchestrator_planner import _template_plan, _SINGLE_STEP_DOMAINS

    target = target.strip()
    if not target:
        return render.error_page("Target is required.", backend=_active())
    _DAG_MODES = _SINGLE_STEP_DOMAINS | {"govt_proposal"}
    if mode not in ({"competitor", "client"} | _DAG_MODES):
        return render.error_page(f"Unknown mode {mode!r}.", backend=_active())
    backend = backend.strip().lower()
    if backend not in ("", "gemini", "vllm"):
        return render.error_page(f"Unknown backend {backend!r}.", backend=_active())

    if mode in _DAG_MODES:
        # Domain modes route through the orchestrated DAG path — _template_plan produces a
        # deterministic plan (no LLM call), so this is fast and reliable.
        task = Task(
            id=f"run-{mode}-{uuid4().hex[:8]}",
            project_id="legacy",
            objective=target,
            domain=Domain(name=mode),
            created_at=utcnow().isoformat(),
        )
        plan = _template_plan(task)
        if plan is None:
            return render.error_page(f"No template plan for domain {mode!r}.", backend=_active())
        proposal = PlanProposal(plan=plan, created_specs=[])
        cloud_allowed = True
        policy = _run_policy(cloud_allowed)
        if backend:
            policy["backend"] = backend
        from sentinel.agent.governance import effective_search_provider as _esp
        policy["search_provider"] = _esp(get_config(), allow_cloud=cloud_allowed, backend=policy["backend"])
        trace: list[str] = []
        try:
            outcome = await gate_proposal(
                proposal,
                autonomy="autonomous",
                seeds={s.id: {"target": target, "vertical_context": vertical.strip() or target}
                       for s in plan.steps},
                cfg=get_config(),
                cloud_allowed=cloud_allowed,
                trace=trace,
                **policy,
            )
        except Exception as exc:
            return render.error_page(
                f"{type(exc).__name__}: {exc}",
                hint=_failure_hint(exc),
                backend=policy.get("backend") or _active(),
            )
        return render.plan_review_page(
            task=task,
            proposal=proposal,
            autonomy="autonomous",
            backend=policy.get("backend") or _active(),
            ran=outcome.ran,
            result=outcome.result,
            trace=trace,
        )

    try:
        result = await run_async(
            target,
            mode,  # type: ignore[arg-type]  # validated above against Mode literal
            vertical_context=vertical.strip() or None,
            backend=backend or None,
        )
    except Exception as exc:  # surfacing the failure beats a blank 500 in a live demo
        return render.error_page(
            f"{type(exc).__name__}: {exc}",
            hint=_failure_hint(exc),
            backend=backend or _active(),
        )

    # The orchestrator persists the run to the durable RunStore (AC-1); the dashboard reads it.
    return render.render_artifact(
        result.artifact, backend=result.backend,
        reference=result.write.reference, trace=result.trace,
        delta=getattr(result, "delta", None),
    )


# --------------------------------------------------------------------------- #
# Settings (SENTINEL-003) — view + edit the live SentinelConfig. Each section
# commits to a deep copy only after validation, so a bad edit never corrupts the
# stored config (NFR-2). No secret is ever rendered or persisted (NFR-1).
# --------------------------------------------------------------------------- #
def _settings_html(*, ok: str = "", err: str = "", password_ok: str = "", password_err: str = "") -> str:
    from sentinel.tools.mcp_registry import mcp_status
    return render.settings_page(
        get_config(),
        backend=_active(),
        gemini_key_set=_key_set("GOOGLE_API_KEY"),
        vllm_key_set=_key_set("VLLM_API_KEY"),
        brave_key_set=_key_set("BRAVE_API_KEY"),
        serpapi_key_set=_key_set("SERPAPI_API_KEY"),
        google_cse_id_set=_key_set("GOOGLE_CSE_ID"),
        atcuality_key_set=_key_set("ATCUALITY_API_KEY"),
        mcp_rows=mcp_status(get_config()),
        ok=ok,
        err=err,
        password_ok=password_ok,
        password_err=password_err,
    )


@app.post("/settings/mcp/{name}", response_class=HTMLResponse)
async def settings_mcp_toggle(name: str, enabled: str = Form("")) -> RedirectResponse:
    from urllib.parse import quote as _q
    cfg = get_config().model_copy(deep=True)
    server = cfg.mcp_servers.get(name)
    if server is None:
        return RedirectResponse(f"/settings?err={_q(f'Unknown MCP server {name}.')}", status_code=303)
    server.enabled = bool(enabled)
    set_config(cfg, persist=True)
    state = "enabled" if server.enabled else "disabled"
    return RedirectResponse(f"/settings?ok={_q(f'MCP server {name} {state}.')}", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings(ok: str = "", err: str = "") -> str:
    return _settings_html(ok=ok, err=err)


@app.post("/settings/backends", response_class=HTMLResponse)
async def settings_backends(
    default: str = Form("gemini"),
    gemini_model: str = Form(...),
    vllm_model: str = Form(...),
    vllm_api_base: str = Form(...),
    vllm_reasoning_model: str = Form(""),
    vllm_reasoning_api_base: str = Form(""),
) -> str:
    try:
        cfg = settings_helpers.apply_backends(
            get_config(), default=default, gemini_model=gemini_model,
            vllm_model=vllm_model, vllm_api_base=vllm_api_base,
        )
        # Wire the reasoning model to synthesizer + strategist roles if provided
        if vllm_reasoning_model.strip():
            cfg = settings_helpers.apply_models(cfg, {
                "synthesizer": {"model": vllm_reasoning_model.strip(),
                                "api_base": vllm_reasoning_api_base.strip() or vllm_api_base.strip()},
                "strategist":  {"model": vllm_reasoning_model.strip(),
                                "api_base": vllm_reasoning_api_base.strip() or vllm_api_base.strip()},
            })
        else:
            cfg = settings_helpers.apply_models(cfg, {})  # clears roles → single-model mode
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Backends saved. The next run uses them.")


@app.post("/settings/generation", response_class=HTMLResponse)
async def settings_generation(
    temperature: str = Form(""),
    max_output_tokens: str = Form(""),
    top_p: str = Form(""),
    top_k: str = Form(""),
) -> str:
    form = {"temperature": temperature, "max_output_tokens": max_output_tokens,
            "top_p": top_p, "top_k": top_k}
    try:
        gen = settings_helpers.parse_generation(form, allow_blank=False)
        set_config(settings_helpers.apply_generation(get_config(), gen), persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Generation defaults saved.")


@app.post("/settings/governance", response_class=HTMLResponse)
async def settings_governance(
    compliance_mode: str = Form("cloud_ok"),
    audit_log: str = Form(""),
    block_cloud_on_private: str = Form(""),
) -> str:
    try:
        cfg = settings_helpers.apply_governance(
            get_config(),
            compliance_mode=compliance_mode,
            audit_log=bool(audit_log),
            block_cloud_on_private=bool(block_cloud_on_private),
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Governance policy saved. The next run obeys it.")


@app.post("/settings/search", response_class=HTMLResponse)
async def settings_search(
    provider: str = Form("gemini"),
    results: str = Form("5"),
    onprem_fallback: str = Form("duckduckgo"),
) -> str:
    try:
        cfg = settings_helpers.apply_search(
            get_config(),
            provider=provider,
            results=results,
            onprem_fallback=onprem_fallback,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Search provider saved. The next run uses it.")


@app.post("/settings/models", response_class=HTMLResponse)
async def settings_models(request: Request) -> str:
    """Per-role Gemma-4 model map (SENTINEL-011). Dynamic fields ``model__<role>`` /
    ``api_base__<role>`` — read via the raw form since the role set is data, not fixed params."""
    form = await request.form()
    roles: dict[str, dict[str, str]] = {}
    for field, value in form.items():
        if field.startswith("model__"):
            roles.setdefault(field[len("model__"):], {})["model"] = str(value)
        elif field.startswith("api_base__"):
            roles.setdefault(field[len("api_base__"):], {})["api_base"] = str(value)
    try:
        cfg = settings_helpers.apply_models(get_config(), roles)
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Model tiering saved. The next run uses it.")


@app.post("/settings/strategy", response_class=HTMLResponse)
async def settings_strategy(
    enabled: str = Form(""),
    playbook_dir: str = Form("playbooks"),
    competitor_playbook: str = Form("competitor-counterplay"),
    client_playbook: str = Form("account-strategy"),
) -> str:
    try:
        cfg = settings_helpers.apply_strategy(
            get_config(),
            enabled=bool(enabled),
            playbook_dir=playbook_dir,
            competitor_playbook=competitor_playbook,
            client_playbook=client_playbook,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Strategy settings saved. The next run uses them.")


@app.post("/settings/coordinator", response_class=HTMLResponse)
async def settings_coordinator(enabled: str = Form("")) -> str:
    try:
        cfg = settings_helpers.apply_coordinator(get_config(), enabled=bool(enabled))
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Coordinator setting saved. The next run uses it.")


@app.post("/settings/memory", response_class=HTMLResponse)
async def settings_memory(
    entity_memory: str = Form(""),
    retention_days: str = Form(""),
    inject_org_prefs: str = Form(""),
    episodic_recall: str = Form(""),
    episodic_recall_top_k: str = Form("3"),
    context_window_tokens: str = Form("2400"),
) -> str:
    try:
        cfg = settings_helpers.apply_memory(
            get_config(),
            entity_memory=bool(entity_memory),
            retention_days=retention_days,
            inject_org_prefs=bool(inject_org_prefs),
            episodic_recall=bool(episodic_recall),
            episodic_recall_top_k=episodic_recall_top_k,
            context_window_tokens=context_window_tokens,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Memory settings saved.")


@app.post("/settings/harness", response_class=HTMLResponse)
async def settings_harness(
    max_turns: str = Form("30"),
    max_retries: str = Form("3"),
    base_retry_delay_s: str = Form("1.0"),
) -> str:
    """Agent harness settings: turn controller + retry policy (SENTINEL-015 FR-06/FR-07)."""
    try:
        cfg = settings_helpers.apply_harness(
            get_config(),
            max_turns=max_turns,
            max_retries=max_retries,
            base_retry_delay_s=base_retry_delay_s,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Harness settings saved. The next run uses them.")


@app.get("/memory/episodes", response_class=HTMLResponse)
async def memory_episodes(ok: str = "", err: str = "") -> str:
    """Episodic memory viewer — list all run records with delete controls (SENTINEL-015 CRUD)."""
    try:
        records = RunStore().all()
    except Exception:
        records = []
    return render.episodes_page(records=records, backend=_active(), ok=ok, err=err)


@app.post("/memory/episodes/{run_id}/delete", response_class=HTMLResponse)
async def memory_episode_delete(run_id: str) -> HTMLResponse:
    """Delete a single run record from episodic memory (SENTINEL-015 CRUD)."""
    from fastapi.responses import RedirectResponse
    try:
        deleted = RunStore().delete_run(run_id)
        msg = f"ok=Run+{run_id[:8]}…+deleted." if deleted else f"err=Run+{run_id[:8]}+not+found."
    except Exception as exc:
        msg = f"err={type(exc).__name__}"
    return RedirectResponse(url=f"/memory/episodes?{msg}", status_code=303)


@app.post("/settings/agents/{key}", response_class=HTMLResponse)
async def settings_agent(
    key: str,
    enabled: str = Form(""),
    model: str = Form(""),
    pin_gemini: str = Form(""),
    temperature: str = Form(""),
    max_output_tokens: str = Form(""),
    top_p: str = Form(""),
    top_k: str = Form(""),
) -> str:
    form = {"temperature": temperature, "max_output_tokens": max_output_tokens,
            "top_p": top_p, "top_k": top_k}
    try:
        gen = settings_helpers.parse_generation(form, allow_blank=True)
        cfg = settings_helpers.apply_agent(
            get_config(), key, enabled=bool(enabled), model=model,
            pin_gemini=bool(pin_gemini), gen=gen,
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok=f"Agent {key} saved.")


# --------------------------------------------------------------------------- #
# Prompts CRUD page + JSON API (full Create / Read / Update / Delete)
# --------------------------------------------------------------------------- #

def _prompts_html(*, ok: str = "", err: str = "") -> str:
    cfg = get_config()
    backend = cfg.backend.default
    return render.prompts_page(cfg, backend=backend, ok=ok, err=err)


@app.get("/settings/prompts", response_class=HTMLResponse)
async def prompts_page(ok: str = "", err: str = "") -> str:
    return _prompts_html(ok=ok, err=err)


@app.post("/settings/prompts/create", response_class=HTMLResponse)
async def prompts_create(
    key: str = Form(...),
    template: str = Form(...),
    variables: str = Form(""),
) -> RedirectResponse:
    try:
        vars_list = [v.strip() for v in variables.split(",") if v.strip()]
        set_config(settings_helpers.create_prompt(get_config(), key, template, vars_list), persist=True)
    except ValueError as exc:
        from urllib.parse import quote as _q
        return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
    from urllib.parse import quote as _q
    return RedirectResponse(f"/settings/prompts?ok={_q(f'Prompt {key} created.')}", status_code=303)


@app.post("/settings/prompts/{key}", response_class=HTMLResponse)
async def prompts_save(key: str, template: str = Form(...)) -> RedirectResponse:
    try:
        set_config(settings_helpers.apply_prompt(get_config(), key, template), persist=True)
    except ValueError as exc:
        from urllib.parse import quote as _q
        return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
    from urllib.parse import quote as _q
    return RedirectResponse(f"/settings/prompts?ok={_q(f'Prompt {key} saved.')}", status_code=303)


@app.post("/settings/prompts/{key}/reset", response_class=HTMLResponse)
async def prompts_reset(key: str) -> RedirectResponse:
    try:
        set_config(settings_helpers.reset_prompt(get_config(), key), persist=True)
    except ValueError as exc:
        from urllib.parse import quote as _q
        return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
    from urllib.parse import quote as _q
    return RedirectResponse(f"/settings/prompts?ok={_q(f'Prompt {key} reset to default.')}", status_code=303)


@app.post("/settings/prompts/{key}/delete", response_class=HTMLResponse)
async def prompts_delete(key: str) -> RedirectResponse:
    try:
        set_config(settings_helpers.delete_prompt(get_config(), key), persist=True)
    except ValueError as exc:
        from urllib.parse import quote as _q
        return RedirectResponse(f"/settings/prompts?err={_q(str(exc))}", status_code=303)
    from urllib.parse import quote as _q
    return RedirectResponse(f"/settings/prompts?ok={_q(f'Prompt {key} deleted.')}", status_code=303)


# --------------------------------------------------------------------------- #
# Persona library — editor page + LLM-backed profile generator
# --------------------------------------------------------------------------- #

def _persona_reserved_names() -> set[str]:
    """Names no saved persona may take: the two form sentinels plus ``enterprise`` (which must stay
    == Persona() for the dag skip-pass invariant). The other 5 built-ins ARE editable — saving one
    creates an override the /personas editor manages, resolved ahead of the code default."""
    return {"enterprise", "custom", "auto"}


def _builtin_overrides(saved: list) -> dict:
    """Map built-in persona name → its override SavedPersona (newest wins), for cards that show an
    edited built-in. ``saved`` is PersonaStore().list() (newest-first)."""
    from sentinel.artifacts.schemas import PERSONA_PROFILES
    out: dict = {}
    for p in saved:
        k = p.name.strip().lower()
        if k in PERSONA_PROFILES and k != "enterprise" and k not in out:
            out[k] = p
    return out


@app.get("/personas", response_class=HTMLResponse)
async def personas_page(request: Request, ok: str = "", err: str = "") -> str:
    from sentinel.memory.store import PersonaStore
    saved = PersonaStore().list()
    # gen_* query params carry a generator result into the create form (PRG, no session state)
    gen = {k[4:]: v for k, v in request.query_params.items() if k.startswith("gen_")}
    return render.personas_page(saved, backend=_active(), ok=ok, err=err, gen=gen or None,
                                builtin_overrides=_builtin_overrides(saved))


@app.post("/personas/create", response_class=HTMLResponse)
async def personas_create(
    name: str = Form(...),
    description: str = Form(""),
    reading_level: str = Form(""),
    tone: str = Form(""),
    format: str = Form(""),
    source_policy: str = Form(""),
) -> RedirectResponse:
    from urllib.parse import quote as _q
    from sentinel.artifacts.schemas import PERSONA_PROFILES, SavedPersona
    from sentinel.memory.store import PersonaStore
    import re
    n = name.strip()
    if not n:
        return RedirectResponse(f"/personas?err={_q('Persona name is required.')}", status_code=303)
    if n.lower() in _persona_reserved_names():
        return RedirectResponse(
            f"/personas?err={_q(f'{n} is reserved and cannot be edited.')}", status_code=303)
    # Names flow into <option value> attributes and the task form's <script> profile map —
    # bound the charset here (defense in depth on top of render-side < escaping).
    if not re.fullmatch(r"[A-Za-z0-9 _\-.]{1,64}", n):
        return RedirectResponse(
            f"/personas?err={_q('Persona names may use letters, digits, spaces, _ - . (max 64).')}",
            status_code=303)
    store = PersonaStore()
    # Re-saving an existing name EDITS it (one row per name) rather than stacking duplicates —
    # this is how both saved personas and built-in overrides get updated in place.
    for prior in store.list():
        if prior.name.strip().lower() == n.lower():
            store.delete(prior.id)
    store.save(SavedPersona(
        id=uuid4().hex,
        name=n,
        description=description.strip(),
        reading_level=reading_level.strip() or "professional",
        tone=tone.strip() or "neutral",
        format=format.strip() or "brief",
        source_policy=source_policy.strip() or None,
        created_at=utcnow().isoformat(),
    ))
    verb = "updated (overrides the built-in)" if n.lower() in PERSONA_PROFILES else "saved"
    return RedirectResponse(f"/personas?ok={_q(f'Persona {n} {verb}.')}", status_code=303)


@app.post("/personas/{persona_id}/delete", response_class=HTMLResponse)
async def personas_delete(persona_id: str) -> RedirectResponse:
    from urllib.parse import quote as _q
    from sentinel.memory.store import PersonaStore
    store = PersonaStore()
    p = store.get(persona_id)
    if p is None:
        return RedirectResponse(f"/personas?err={_q('Persona not found.')}", status_code=303)
    store.delete(persona_id)
    return RedirectResponse(f"/personas?ok={_q(f'Persona {p.name} deleted.')}", status_code=303)


@app.post("/personas/generate", response_class=HTMLResponse)
async def personas_generate(
    description: str = Form(...),
    name: str = Form(""),
) -> RedirectResponse:
    """One-shot LLM call: audience description → suggested full profile (prefills the create form)."""
    from urllib.parse import quote as _q
    desc = description.strip()
    if not desc:
        return RedirectResponse(f"/personas?err={_q('Describe the audience first.')}", status_code=303)

    prompt = (
        "You design audience profiles for a research-report renderer. Given this audience "
        f"description:\n\n{desc}\n\n"
        "Return ONLY a JSON object with exactly these string fields:\n"
        '{"reading_level": "...", "tone": "...", "format": "...", "source_policy": "..."}\n'
        "- reading_level: who can read it (e.g. 'K-12 to undergraduate', 'professional (clinical)')\n"
        "- tone: voice of the report (e.g. 'plain', 'technical', 'clinical')\n"
        "- format: output shape (e.g. 'checklist with a one-line rationale per item')\n"
        "- source_policy: which sources to prefer or require\n"
        "Keep each value under 90 characters."
    )
    try:
        import json as _json
        import litellm as _litellm
        cfg = get_config()
        if _active() == "gemini":
            resp = await _litellm.acompletion(
                model=f"gemini/{cfg.backend.gemini.model}",
                messages=[{"role": "user", "content": prompt}],
                api_key=os.environ.get("GOOGLE_API_KEY"),
                max_tokens=512,
                response_format={"type": "json_object"},
                drop_params=True,
            )
        else:
            from sentinel.llm.gateway import _vllm_api_key
            api_base = cfg.backend.vllm.api_base
            resp = await _litellm.acompletion(
                model=f"hosted_vllm/{cfg.backend.vllm.model}",
                messages=[{"role": "user", "content": prompt}],
                api_base=api_base,
                api_key=_vllm_api_key(api_base),
                max_tokens=512,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        text = (resp.choices[0].message.content or "").strip()
        start, end = text.find("{"), text.rfind("}")
        data = _json.loads(text[start:end + 1]) if start >= 0 <= end else {}
        if not isinstance(data, dict):
            raise ValueError("generator returned non-object JSON")
    except Exception as exc:
        return RedirectResponse(
            f"/personas?err={_q(f'Generator failed: {type(exc).__name__}: {str(exc)[:120]}')}",
            status_code=303)

    params = "&".join([
        f"gen_name={_q(name.strip())}",
        f"gen_desc={_q(desc)}",
        f"gen_rl={_q(str(data.get('reading_level', '')).strip()[:120])}",
        f"gen_tone={_q(str(data.get('tone', '')).strip()[:120])}",
        f"gen_fmt={_q(str(data.get('format', '')).strip()[:120])}",
        f"gen_sp={_q(str(data.get('source_policy', '')).strip()[:120])}",
    ])
    return RedirectResponse(
        f"/personas?ok={_q('Profile generated — review and save below.')}&{params}", status_code=303)


@app.get("/api/prompts")
async def api_prompts_list():
    from fastapi.responses import JSONResponse as _J
    cfg = get_config()
    return _J({
        k: {
            "template": v.template,
            "variables": v.variables,
            "has_default": v.default_template is not None,
            "is_custom": v.default_template is None,
        }
        for k, v in sorted(cfg.prompts.items())
    })


@app.get("/api/prompts/{key}")
async def api_prompt_detail(key: str):
    from fastapi.responses import JSONResponse as _J
    cfg = get_config()
    if key not in cfg.prompts:
        return _J({"error": f"Prompt {key!r} not found"}, status_code=404)
    p = cfg.prompts[key]
    ac = cfg.agents.get(key)
    return _J({
        "key": key,
        "template": p.template,
        "variables": p.variables,
        "has_default": p.default_template is not None,
        "is_custom": p.default_template is None,
        "role": ac.role if ac else None,
    })


def _failure_hint(exc: Exception) -> str:
    """Turn the most common live-demo failure into a one-line fix."""
    text = f"{type(exc).__name__} {exc}".lower()
    if "connect" in text or "refused" in text or "8000" in text or "hosted_vllm" in text:
        return (
            "Could not reach the local vLLM server. Start it (e.g. "
            "`docker compose -f deploy/vllm-compose.yml up`) and check VLLM_API_BASE, "
            "or switch the toggle back to Cloud · Gemini."
        )
    if "api_key" in text or "api key" in text or "credential" in text or "permission" in text:
        return (
            "The inference backend has no credentials. For the Gemini demo, set GOOGLE_API_KEY "
            "(https://aistudio.google.com/apikey)."
        )
    if "no '" in text and "in state" in text:
        return "The model returned no structured artifact — usually a transient model error; retry."
    return ""


@app.post("/settings/password", response_class=HTMLResponse)
async def settings_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
) -> str:
    cfg = get_config()
    if not cfg.auth.password_hash or not _auth.verify_password(current_password, cfg.auth.password_hash):
        return _settings_html(password_err="Current password is incorrect.")
    if len(new_password) < 8:
        return _settings_html(password_err="New password must be at least 8 characters.")
    if new_password != confirm_password:
        return _settings_html(password_err="New passwords do not match.")
    cfg = cfg.model_copy(deep=True)
    cfg.auth.password_hash = _auth.hash_password(new_password)
    set_config(cfg, persist=True)
    # Invalidate every session then re-issue one for the current admin so they
    # stay logged in while any other concurrent sessions are signed out.
    _auth.clear_all_sessions()
    token = _auth.create_session()
    resp = HTMLResponse(_settings_html(password_ok="Password changed. All other sessions have been signed out."))
    resp.set_cookie(_COOKIE, token, httponly=True, samesite="strict", max_age=43200)
    return resp


# ---- Memory-Brain: entity source-config API (Task 8) ----

@app.get("/api/memory/source-config/{entity_slug}")
async def get_memory_source_config(entity_slug: str):
    """Return the source-config for an entity (defaults if not yet saved)."""
    from fastapi.responses import JSONResponse
    from sentinel.memory.store import db_path as _db_path
    from sentinel.web.render.memory_config import get_source_config
    return JSONResponse(get_source_config(_db_path(), entity_slug))


@app.post("/api/memory/source-config/{entity_slug}")
async def post_memory_source_config(entity_slug: str, request: Request):
    """Save the source-config for an entity."""
    from fastapi.responses import JSONResponse
    from sentinel.memory.store import db_path as _db_path
    from sentinel.web.render.memory_config import save_source_config
    payload = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    try:
        save_source_config(_db_path(), entity_slug, payload)
        return JSONResponse({"ok": True})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/api/memory/crawl-now/{entity_slug}")
async def post_crawl_now(entity_slug: str):
    """Immediately enqueue all enabled crawl sources for an entity."""
    from fastapi.responses import JSONResponse
    from sentinel.memory.schema import normalize_entity as _norm
    from sentinel.memory.scheduler import CrawlScheduler
    from sentinel.memory.store import db_path as _db_path
    entity = _norm(entity_slug.replace("-", " "))
    n = CrawlScheduler(_db_path()).force_enqueue(entity, priority=10)
    return JSONResponse({"enqueued": n, "entity": entity})


def main() -> None:  # pragma: no cover - convenience entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":  # pragma: no cover
    main()
