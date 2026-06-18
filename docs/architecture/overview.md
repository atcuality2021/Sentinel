# Architecture Overview

**Repo:** Sentinel — Sovereign Intelligence Agent (BiltIQ AI / Aarna Tech Consultants Pvt. Ltd.)
**Last reviewed:** 2026-06-18 (memory brain + full Next.js frontend + e-commerce domains)

## What this system does (1-paragraph)

Sentinel is a full-stack autonomous research platform for regulated SMBs. Users create
**Projects → Tasks**; each Task triggers a multi-agent **DAG pipeline** that plans,
executes parallel researcher agents, synthesizes findings, and returns a typed report
with citations. 9 research domains (competitor, client, market, finance, software,
academic, nutrition, travel, e-commerce/deals). A **self-driving memory brain** crawls
configured sources on a schedule and enriches the per-project Knowledge Base (ChromaDB
+ BM25 hybrid). The defining architectural property is a hard **public/private tool
boundary** enforced structurally in code, plus a sovereignty switch that runs the entire
stack on-prem via Gemma-4 dual-tier (12B tool-caller + 26B reasoner) with zero cloud
egress, provably.

## Components

### Orchestration layer (`src/sentinel/agent/`)
- **DAG planner** (`dag.py`) — `run_dag` executes a plan's steps in dependency order using
  a level-scheduler (`asyncio.gather` per frontier level). Per-step semaphore
  (`_leaf_semaphore`) caps concurrent ADK runners. Steps reference registry specs by
  `agent_spec_id`; fetched + built at run time.
- **Orchestrator** (`orchestrator.py`) — `_plan_and_run` → `_approve_and_run` →
  `_execute_run` → `gate_proposal(autonomy="autonomous")` → `run_dag`. Plan lifecycle:
  `proposed → running → done/failed`. Task lifecycle mirrors it.
- **AgentRegistry** (`registry.py`) — persisted `agent_specs` table. `build_from_spec`
  sanitizes agent names to valid Python IDs before passing to `make_agent`.
- **Autonomy gate** (`autonomy.py`) — `gate_proposal(autonomy="propose")` halts at
  `proposed` (human approval); `"autonomous"` runs the DAG immediately.
- **Governance** (`governance.py`) — `cloud_allowed` / `effective_backend` /
  `effective_search_provider`. `on_prem_required` ⇒ zero Gemini objects built.
- **Coordinator** (`coordinator.py`) — ADK `LlmAgent` over `AgentTool` specialists.
  Gated by `coordinator.enabled` (default off); legacy `SequentialAgent` runs unchanged.

### Model layer (`src/sentinel/llm/`)
- **Gateway** (`gateway.py`) — `resolve_model(role, cloud_allowed)` maps roles to models:
  tool-calling → gemma-4-12B, reasoning → gemma-4-26B, or Gemini in cloud mode. One seam
  for the sovereignty swap.
- **Fallback chain** — vLLM → Gemini → Claude, automatic with UI notification banner.
  Config: `SENTINEL_LLM_BACKEND`. Gemini 2.5 Flash is cloud default.

### Memory layer (`src/sentinel/memory/`)
- **RunStore** — SQLite (WAL). Task/Plan/AgentSpec CRUD. `_row_to_task` reads authoritative
  `status` DB column (not stale JSON blob). `_row_to_spec` reads authoritative `active`
  column.
- **MemoryStore** — entity facts (SM-2 reinforced). `recall(entity, allowed_boundaries)` is
  the single boundary choke-point — the ONLY place the public/private rule is enforced.
- **KBManager** — per-project Knowledge Base. ChromaDB vector store + BM25. Hybrid search.
  Ingest path: `add_text()` / `add_url()` / post-run auto-ingest. Read path: `hybrid_search`.
- **EpisodicStore** — run history for persona-aware recall across sessions.
- **MemoryWorker** (`worker.py`) — background worker polling a job queue. Entry point:
  `sentinel-memory-worker`.
- **CrawlScheduler** — cron-driven enqueuer; reads per-entity `source_config` (priority +
  connector type) and enqueues crawl jobs for the worker.
- **Connectors** (`connectors/`) — 4 connectors: `web` (Firecrawl), `youtube` (SearchAPI),
  `email` (IMAP), `social` (LinkedIn/Twitter). SSRF guard on all external URLs (DNS rebinding
  protected via `getaddrinfo` all-record check).

### Web layer (`src/sentinel/web/`)
- **FastAPI backend** (`app.py`) — 30+ JSON API routes. Key: `_ACTIVE_RUNS` dict tracks
  live pipeline state; `status.json` endpoint serves step states from it. Post-restart
  orphan detection: `status == "running"` with no active run → returns `"failed"`.
- **API routes** (`api_json.py`) — CRUD for projects, tasks, agents, settings, personas,
  KB, memory sources, chat.

### Frontend (`frontend/`)
- **Next.js 16** app. Rewrites `/api/*` → backend `:8094` (no CORS). SWR for data fetching
  with polling on running tasks.
- **Pages:** Projects, Project detail (KB / Tasks / Memory / Artifacts tabs), Task detail
  (live pipeline + accordion report), Agents, Personas, Focus, Settings, Settings/Prompts.
- **Live pipeline UI** — `LiveRunPanel` polls `status.json`; shows per-step status with
  agent+model badges, handover animation, warming-up skeleton, and fail reason on error.
- **Memory Sources form** — on Project Memory tab. Entity slug:
  `projectName.trim().toLowerCase().replace(/\s+/g, '-')`. Calls
  `GET/POST /api/memory/source-config/${slug}` and `POST /api/memory/crawl-now/${slug}`.

## Data flow

```
Browser (Next.js 16)
  │  POST /api/projects/{id}/tasks  →  task created, background _plan_and_run fires
  │  GET  /api/projects/{id}/tasks/{taskId}/status.json  (SWR poll, 2s)
  │
  ▼
FastAPI (:8094)
  │
  ├── _plan_and_run
  │     └── OrchestratorPlanner → Plan (steps + agent_spec_ids)
  │           └── gate_proposal(autonomy="autonomous")
  │                 └── run_dag(plan)
  │                       ├── [level 0] public_research steps  (Gemma 12B, DDG/SearchAPI)
  │                       ├── [level 1] private_research steps (Gemma 12B, scoped MCP)
  │                       ├── [level 2] synthesizer            (Gemma 26B / Gemini)
  │                       └── [level 3] grader + strategy      (deterministic / LLM)
  │
  ├── Memory harness (parallel)
  │     ├── EpisodicStore  ← run records
  │     ├── MemoryStore    ← entity facts (SM-2)
  │     └── KBManager      ← post-run auto-ingest of finding_texts
  │
  └── MemoryWorker (separate process)
        └── CrawlScheduler → job queue → connectors (web/YT/email/social) → KBManager
```

## Deployment topology

- **Production:** GCP VM `35.252.125.139`. PM2: `sentinel-backend` (:8094) +
  `sentinel-frontend` (:3001). Nginx reverse-proxy → HTTPS `sentinel.atcuality.com`.
  **Critical:** frontend must start as `PORT=3001 npm start` — nginx `proxy_pass` expects
  :3001; default port 3000 causes 502.
- **Models:** Gemma-4-12B at `gemma.atcuality.com`, Gemma-4-26B at `omni.atcuality.com`
  (Cloudflare-proxied vLLM, OpenAI-compatible). Automatic fallback → Gemini 2.5 Flash →
  Claude.
- **Local dev:** `PORT=8094 .venv/bin/python3 -m sentinel.web.app` + `npm run dev` in
  `frontend/` (dev auto-uses :3001 via `next.config.js`).
- **Data:** SQLite at `data/sentinel.db` (WAL, gitignored). ChromaDB at `data/kb/`.
  Override with `SENTINEL_DATA_DIR`.

## Dependencies

External:
- Gemma-4 sovereign gateway (atcuality) — 12B tool-caller + 26B reasoner (OpenAI-compat)
- Google Gemini 2.5 Flash / Vertex AI — cloud-mode fallback + grounded search
- Claude (Anthropic) — tertiary fallback
- Google ADK 2.2.0 (`google-adk[extensions]`) — agent orchestration + AgentTool
- SearchAPI — `google_shopping_search` (find_deals), `youtube_search`, `google_search`
- Firecrawl MCP — web content extraction for KB connector
- DuckDuckGo lite / SearXNG — sovereign keyless public search
- ChromaDB + BM25 — KB hybrid search store

Internal:
- Model gateway (`llm/gateway.py`) — role→model resolution + fallback chain
- Governance (`agent/governance.py`) — sovereignty routing brain
- Memory harness (`memory/`) — boundary-aware episodic + semantic + KB stores
- AgentRegistry (`agent/registry.py`) — persisted spec store + `build_from_spec`

## Failure modes

| Dependency | Failure | Behavior |
|---|---|---|
| Gemma gateway | timeout / 5xx | Fallback → Gemini → Claude; UI notification banner |
| DAG step error | agent errors | Step marked `failed`; `fail_reason` surfaced in UI |
| MCP connector | unauthorized / unreachable | Gap recorded; partial output still produced |
| MemoryWorker | crash | Crawl jobs queue; re-processed on restart |
| ChromaDB ingest | embed auth failure | KB returns 0 chunks; research continues without KB |
| Post-restart orphan | `status=running` + no `_ACTIVE_RUNS` entry | Returns `"failed"` to UI |

## Where new code goes

- New research domain → `src/sentinel/agent/modes/` + register in domain map
- DAG / orchestrator logic → `src/sentinel/agent/dag.py` / `orchestrator.py`
- Model adapters / role resolution → `src/sentinel/llm/gateway.py`
- New MCP tool/connector → `src/sentinel/tools/{public,private}/` (correct boundary)
- Memory connector → `src/sentinel/memory/connectors/` + register in worker
- Artifact schemas → `src/sentinel/artifacts/schemas.py`
- Priority signals → `src/sentinel/priority/` (SENTINEL-010)
- Strategy playbooks → `playbooks/*.md` (runtime-loaded)
- Shared utility → `src/sentinel/lib/` (add to `stack.md`)
- Frontend page → `frontend/app/(app)/`

## Audit cadence

Reviewed at each milestone. Material changes (new component, new boundary, new
model/dependency, deploy-topology change) require a same-PR update and, for a new AI
dependency, an ADR.
