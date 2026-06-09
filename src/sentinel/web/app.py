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

from fastapi import FastAPI, Form, Request
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
from sentinel.memory.store import ProjectStore
from sentinel.priority import PriorityStore, compute_account_priority
from sentinel.tools.private.workspace_mcp import private_boundary_configured
from sentinel.web import render
from sentinel.web import settings as settings_helpers

app = FastAPI(title="Sentinel — Sovereign Intelligence Agent", docs_url="/api")


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


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    records = _runs()
    recent = [
        {"target": r.target, "entity": r.entity, "mode": r.mode, "backend": r.backend,
         "public": r.public, "private": r.private, "when": _when(r)}
        for r in records[:8]
    ]
    try:
        focus = _focus_scores()[:5]
    except Exception:  # the dashboard never 500s on a scoring hiccup (NFR-6)
        focus = []
    return render.dashboard_page(
        stats=_stats(records), charts=_charts(records), recent=recent, backend=_active(),
        focus=focus,
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
    return render.focus_page(scores=scores, backend=_active(), enabled=True, project=pill)


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


@app.get("/agents", response_class=HTMLResponse)
async def agents() -> str:
    """The agent roster + pipeline flow graph (introspected from the live specs + config)."""
    modes, flags = _agents_view(get_config())
    return render.agents_page(modes=modes, flags=flags, backend=_active())


@app.get("/artifacts", response_class=HTMLResponse)
async def artifacts(project: str = "") -> str:
    pid, pill = _resolve_project(project)  # optional project scope (SENTINEL-012 AC-10)
    items = [
        {"target": r.target, "entity": r.entity, "kind": r.kind, "public": r.public,
         "private": r.private, "backend": r.backend, "reference": r.reference, "when": _when(r)}
        for r in _runs(project_id=pid)
    ]
    return render.artifacts_page(artifacts=items, backend=_active(), project=pill)


@app.get("/backends", response_class=HTMLResponse)
async def backends() -> str:
    cfg = get_config()  # Settings edits these; env only seeds the initial config
    return render.backends_page(
        default_backend=_active(),
        gemini_model=cfg.backend.gemini.model,
        vllm_model=cfg.backend.vllm.model,
        vllm_api_base=cfg.backend.vllm.api_base or "",
        gemini_key_set=_key_set("GOOGLE_API_KEY"),
        vllm_key_set=_key_set("VLLM_API_KEY"),
        private_configured=private_boundary_configured(),
    )


# --------------------------------------------------------------------------- #
# Accounts (SENTINEL-004) — entity-centric read views + the purge control.
# All reads fail-soft to an empty/not-found state (NFR-6); no read mutates memory
# (AC-5 — the detail page uses list_for_entity, never recall); deletion is POST-only
# behind a confirm step (AC-8).
# --------------------------------------------------------------------------- #
@app.get("/accounts", response_class=HTMLResponse)
async def accounts(ok: str = "", project: str = "") -> str:
    pid, pill = _resolve_project(project)  # optional project scope (SENTINEL-012 AC-10)
    try:
        summaries = RunStore().entities(project_id=pid)
    except Exception:  # a store error degrades to the empty state, never a 500 (NFR-6)
        summaries = []
    return render.accounts_page(accounts=summaries, backend=_active(), ok=ok, project=pill)


@app.get("/accounts/{entity}", response_class=HTMLResponse)
async def account_detail(entity: str, confirm: str = "") -> str:
    key = normalize_entity(entity)
    try:
        runs = RunStore().runs_for(key)
        mem = MemoryStore()
        public_mem = mem.list_for_entity(key, allowed={DataBoundary.PUBLIC})
        private_mem = mem.list_for_entity(key, allowed={DataBoundary.PRIVATE})
    except Exception:  # fail-soft (NFR-6)
        runs, public_mem, private_mem = [], [], []

    if not runs and not public_mem and not private_mem:  # unknown entity (AC-9)
        return render.not_found_page(what=entity, backend=_active())

    summary = _summary_for(key, runs)
    return render.account_detail_page(
        summary=summary, runs=runs, public_mem=public_mem, private_mem=private_mem,
        backend=_active(), confirm=(confirm == "purge"),
    )


@app.post("/accounts/{entity}/purge")
async def account_purge(entity: str) -> RedirectResponse:
    key = normalize_entity(entity)
    try:
        MemoryStore().purge_entity(key)
    except Exception:  # nothing to surface on the redirect target if it failed; stay fail-soft
        pass
    # 303 → the browser re-GETs /accounts, so a refresh can't re-trigger the POST (AC-8).
    return RedirectResponse(url="/accounts?ok=Account+purged.", status_code=303)


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
async def create_project(name: str = Form(...), website: str = Form(""),
                         objective: str = Form("")) -> RedirectResponse:
    name = name.strip()
    if not name:  # reject a blank name; re-GET the list (no row created)
        return RedirectResponse(url="/projects", status_code=303)
    proj = Project(
        id=uuid4().hex, name=name, website=website.strip() or None,
        created_at=utcnow().isoformat(),
    )
    try:
        ProjectStore().save_project(proj)
    except Exception:
        return RedirectResponse(url="/projects?ok=Could+not+save+project.", status_code=303)
    # 303 → browser re-GETs the next page; a refresh can't re-POST. If the dev gave a first objective,
    # flow straight into planning that task; otherwise land on the project workspace.
    objective = objective.strip()
    if objective:
        return RedirectResponse(
            url=f"/projects/{proj.id}/plan?objective={quote(objective)}", status_code=303)
    return RedirectResponse(url=f"/projects/{proj.id}", status_code=303)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(project_id: str) -> str:
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
    return render.project_detail_page(project=proj, tasks=tasks, backend=_active())


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
    return {
        "backend": effective_backend(cfg) if cloud_allowed else "vllm",
        "search_provider": effective_search_provider(cfg, allow_cloud=cloud_allowed),
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
    org = _extract(
        obj,
        [r"\b(?:profile|research|analy(?:se|ze)|assess|about)\s+(.+?)"
         r"(?:\s+(?:and|,|vs\.?|versus|against|compared?\b|to\b)|$)"],
        host or getattr(project, "name", None) or obj,
    )
    rival = _extract(
        obj,
        [r"\b(?:against|vs\.?|versus|compared?\s+(?:to|with)|competitor[s]?:?)\s+(.+?)(?:\s+(?:and|,|\.)|$)"],
        obj,
    )
    out = {}
    for s in plan.steps:
        if s.capability == "self_profile":
            target = org
        elif s.capability in ("competitor", "client"):
            target = rival
        else:
            target = obj                         # reasoners read upstream artifacts, not a target
        seed = {"target": target, "vertical_context": obj}
        if site:
            seed["website"] = site               # the project's own site, available to the self side
        out[s.id] = seed
    return out


def _grade_sample() -> bool:
    """Whether to model-grade a production run (§10.4, TD-3). Dark by default — grading calls the
    live judge, so it's opt-in via ``SENTINEL_GRADE_SAMPLE=1`` to avoid surprise demo latency."""
    return os.getenv("SENTINEL_GRADE_SAMPLE", "").strip().lower() in {"1", "true", "yes", "on"}


def _persist_run(task, result, backend: str) -> None:
    """Persist an orchestrated Result to the durable RunStore (ADR-0003) so it surfaces on the
    project's artifacts/dashboard — the run is otherwise ephemeral. Mapped onto the existing
    RunRecord shape (no schema change): citations split by boundary, missing steps as gaps."""
    from sentinel.artifacts.schemas import Boundary
    from sentinel.memory.schema import RunRecord

    public = sum(1 for c in result.citations if c.boundary == Boundary.PUBLIC)
    private = sum(1 for c in result.citations if c.boundary == Boundary.PRIVATE)
    rec = RunRecord(
        entity=task.objective, target=task.objective, mode="orchestrated", backend=backend,
        kind=task.domain.name, public=public, private=private, gaps=len(result.missing_inputs),
        reference=", ".join(result.artifacts), sources=list(result.citations),
        project_id=task.project_id,
    )
    RunStore().save(rec)


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


def _persona_for(name: str) -> Persona:
    """Build a Persona from the form's name; unknown/blank falls back to the default enterprise reader
    rather than 500-ing (the form constrains the options, but a hand-typed query must degrade safely)."""
    from sentinel.config.schema import PersonaName  # the allowed literal values
    from typing import get_args

    n = (name or "").strip().lower()
    return Persona(name=n) if n in get_args(PersonaName) else Persona()


@app.get("/projects/{project_id}/plan", response_class=HTMLResponse)
async def plan_review(project_id: str, objective: str = "", domain: str = "market",
                      persona: str = "enterprise") -> str:
    proj = ProjectStore().get_project(project_id)
    if proj is None:
        return render.not_found_page(what=f"project {project_id}", backend=_active())
    objective = objective.strip()
    if not objective:
        return render.error_page("An objective is required to plan a task.", backend=_active())
    store = ProjectStore()
    dom = domain.strip() or "market"
    # Reuse an existing task with the same objective+domain instead of piling up duplicates on every
    # re-plan (the Tasks list stays meaningful). A fresh objective makes a new task.
    task = next((t for t in store.tasks_for_project(project_id)
                 if t.objective == objective and t.domain.name == dom), None)
    if task is None:
        now = utcnow().isoformat()
        task = Task(id=f"task-{now}", project_id=project_id, objective=objective,
                    domain=Domain(name=dom), persona=_persona_for(persona), created_at=now)
    else:
        task.persona = _persona_for(persona)
    cloud_allowed = _cloud_allowed_for(proj)
    try:
        proposal = await plan_task(task, AgentRegistry(), cloud_allowed=cloud_allowed)
        task.status = "planned"             # the plan exists now (reflected in the Tasks list)
        task.plan_id = proposal.plan.id
        store.save_task(task)
        store.save_plan(proposal.plan)  # persist so Approve can reload the exact plan (no re-plan)
        trace: list[str] = []           # the execution log: which step ran on which agent, fail-soft notes
        outcome = await gate_proposal(
            proposal, autonomy=proj.settings.autonomy, seeds=_plan_seeds(task, proposal.plan, proj),
            cfg=get_config(), cloud_allowed=cloud_allowed, trace=trace, **_run_policy(cloud_allowed),
            persona=task.persona, grade=_grade_sample(), grade_objective=task.objective,
        )
        if outcome.ran and outcome.result is not None:
            task.status = "failed" if outcome.result.degraded else "done"   # honest run state
            task.result = outcome.result    # persist on the task so it lives at the task's own URL
            store.save_task(task)
            _persist_run(task, outcome.result, _run_policy(cloud_allowed)["backend"])
    except Exception as exc:  # a live demo surfaces the failure rather than a blank 500
        return render.error_page(f"{type(exc).__name__}: {exc}", backend=_active())
    # PRG: land on the task's own URL so the plan + result are bookmarkable/refresh-safe, not stuck on
    # the shared /plan querystring. The execution trace is ephemeral (in-memory only); it re-renders
    # from the persisted result on the task page.
    return RedirectResponse(url=f"/projects/{project_id}/tasks/{quote(task.id)}", status_code=303)


@app.get("/projects/{project_id}/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail(project_id: str, task_id: str) -> str:
    """The canonical per-task page (PRG target): its plan DAG + assigned agents + call boundaries,
    the Approve & run control, and — once run — the persisted Result + execution trace. Both planning
    (GET /plan) and running (POST .../run) redirect here, so each task's output lives at its own URL
    (refresh-safe, bookmarkable) instead of being trapped in a POST response body."""
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return render.not_found_page(what=f"task {task_id}", backend=_active())
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
    return render.plan_review_page(task=task, proposal=PlanProposal(plan=plan, created_specs=[]),
                                   autonomy=autonomy, backend=_active(),
                                   ran=result is not None, result=result)


@app.post("/projects/{project_id}/tasks/{task_id}/delete")
async def delete_task_route(project_id: str, task_id: str) -> RedirectResponse:
    """Tidy the Tasks list: drop a task (and its plan). Always 303 back to the project workspace."""
    try:
        ProjectStore().delete_task(task_id)
    except Exception:
        pass  # fail-soft: a bad delete still returns to the page, never a 500
    return RedirectResponse(url=f"/projects/{project_id}", status_code=303)


async def _approve_and_run(task_id: str) -> RedirectResponse | str:
    """Human approval of a proposed plan: reload the persisted plan, run it autonomously, persist the
    Result onto the task, then (PRG) redirect to the task's own URL where the output is rendered. The
    created specs are already persisted (Step 15), so the proposal is rebuilt from the stored plan."""
    store = ProjectStore()
    task = store.get_task(task_id)
    if task is None:
        return render.not_found_page(what=f"task {task_id}", backend=_active())
    plan = store.plan_for_task(task_id)
    if plan is None:
        return render.error_page("No plan found for this task — re-plan it first.", backend=_active())
    proj = store.get_project(task.project_id)
    cloud_allowed = _cloud_allowed_for(proj) if proj is not None else True
    proposal = PlanProposal(plan=plan, created_specs=[])
    try:
        trace: list[str] = []
        outcome = await gate_proposal(
            proposal, autonomy="autonomous", seeds=_plan_seeds(task, plan, proj),
            cfg=get_config(), cloud_allowed=cloud_allowed, trace=trace, **_run_policy(cloud_allowed),
            persona=task.persona, grade=_grade_sample(), grade_objective=task.objective,
        )
        if outcome.ran and outcome.result is not None:
            task.status = "failed" if outcome.result.degraded else "done"   # reflect the run in the list
            task.result = outcome.result      # persist on the task so it lives at the task's own URL
            store.save_task(task)
            _persist_run(task, outcome.result, _run_policy(cloud_allowed)["backend"])
    except Exception as exc:
        return render.error_page(f"{type(exc).__name__}: {exc}", backend=_active())
    return RedirectResponse(url=f"/projects/{task.project_id}/tasks/{quote(task.id)}", status_code=303)


@app.post("/projects/{project_id}/tasks/{task_id}/run", response_model=None)
async def run_task_route(project_id: str, task_id: str) -> RedirectResponse | str:
    """Per-task run route (the Approve & run control posts here) — each task runs at its own URL."""
    return await _approve_and_run(task_id)


@app.post("/projects/run-plan", response_model=None)
async def run_plan_route(task_id: str = Form(...)) -> RedirectResponse | str:
    """Back-compat alias for the per-task run route (kept so existing forms/links keep working)."""
    return await _approve_and_run(task_id)


@app.post("/run", response_class=HTMLResponse)
async def run(
    target: str = Form(...),
    mode: str = Form("competitor"),
    vertical: str = Form(""),
    backend: str = Form(""),
) -> str:
    target = target.strip()
    if not target:
        return render.error_page("Target is required.", backend=_active())
    if mode not in ("competitor", "client"):
        return render.error_page(f"Unknown mode {mode!r}.", backend=_active())
    backend = backend.strip().lower()
    if backend not in ("", "gemini", "vllm"):
        return render.error_page(f"Unknown backend {backend!r}.", backend=_active())

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
def _settings_html(*, ok: str = "", err: str = "") -> str:
    return render.settings_page(
        get_config(),
        backend=_active(),
        gemini_key_set=_key_set("GOOGLE_API_KEY"),
        vllm_key_set=_key_set("VLLM_API_KEY"),
        brave_key_set=_key_set("BRAVE_API_KEY"),
        serpapi_key_set=_key_set("SERPAPI_API_KEY"),
        atcuality_key_set=_key_set("ATCUALITY_API_KEY"),
        ok=ok,
        err=err,
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings(ok: str = "", err: str = "") -> str:
    return _settings_html(ok=ok, err=err)


@app.post("/settings/backends", response_class=HTMLResponse)
async def settings_backends(
    default: str = Form("gemini"),
    gemini_model: str = Form(...),
    vllm_model: str = Form(...),
    vllm_api_base: str = Form(...),
) -> str:
    try:
        cfg = settings_helpers.apply_backends(
            get_config(), default=default, gemini_model=gemini_model,
            vllm_model=vllm_model, vllm_api_base=vllm_api_base,
        )
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
) -> str:
    try:
        cfg = settings_helpers.apply_memory(
            get_config(),
            entity_memory=bool(entity_memory),
            retention_days=retention_days,
            inject_org_prefs=bool(inject_org_prefs),
        )
        set_config(cfg, persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok="Memory settings saved.")


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


@app.post("/settings/prompts/{key}", response_class=HTMLResponse)
async def settings_prompt(key: str, template: str = Form(...)) -> str:
    try:
        set_config(settings_helpers.apply_prompt(get_config(), key, template), persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok=f"Prompt {key} saved. The next run uses it.")


@app.post("/settings/prompts/{key}/reset", response_class=HTMLResponse)
async def settings_prompt_reset(key: str) -> str:
    try:
        set_config(settings_helpers.reset_prompt(get_config(), key), persist=True)
    except ValueError as exc:
        return _settings_html(err=str(exc))
    return _settings_html(ok=f"Prompt {key} reset to the shipped default.")


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


def main() -> None:  # pragma: no cover - convenience entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":  # pragma: no cover
    main()
