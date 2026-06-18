# MEMORY.md — Project State (Living Document)

**Purpose:** Persistent context for Claude Code (and any AI-IDE) across sessions. The agent reads this on session start and updates it after meaningful work. Prevents every session from starting cold.

**Update rules:**
- Keep under 200 lines. If it grows past that, the `memory-curator` skill archives older entries to `/docs/memory-archive/YYYY-MM.md`.
- Update at end of every meaningful session (`memory-curator` skill).
- Use the structure below. Don't add new top-level sections without an ADR.
- Don't store secrets, credentials, or PII here.

**Last updated:** 2026-06-18 by harish@atcuality.com

---

## Project at a glance

**Sentinel — Sovereign Intelligence Agent.** A full-stack autonomous research platform for
regulated SMBs (BFSI / healthcare / government). Users create Projects → Tasks → run a
multi-agent DAG pipeline → get typed reports with citations. 9 research domains, persona
presets, per-project Knowledge Base (ChromaDB + BM25), self-driving memory (episodic +
semantic), and a sovereign mode that runs entirely on-prem via Gemma-4 dual-tier (12B
tool-caller + 26B reasoner) with zero cloud egress.

**Status:** Post-challenge production build. Challenge deadline (2026-06-11) passed — submission
delivered. Now hardening for a real pilot user. Quality wins over demo polish.
**Deployment:** GCP VM at `35.252.125.139` → `sentinel.atcuality.com`. PM2 manages
`sentinel-backend` (:8094) and `sentinel-frontend` (:3001). Nginx proxies HTTPS → :3001.
**Compliance mode:** `cloud_ok` (demo/production); `on_prem_preferred` (regulated customers).
Sovereignty switch is a config-only swap, zero code change.
**Stack:** Next.js 16 frontend + FastAPI backend. SQLite (WAL). ChromaDB + BM25 for KB hybrid
search. ADK 2.2.0 for agent orchestration.

---

## Current focus (this week)

- **Active sprint:** E2E quality loop — find bugs, fix, push to git + server.
- **Engine status:** 946 tests green. SENTINEL-001 through SENTINEL-022+ complete.
- **Production deploy:** `sentinel.atcuality.com` live. PM2 managing both services.
- **Infra:** Start with `PORT=3001 npm start` for frontend (nginx expects :3001, NOT :3000).
  Backend: `PORT=8094 .venv/bin/python3 -m sentinel.web.app`.

---

## Recent decisions (last 30 days)

- **2026-06-18** — `_row_to_task` and `_row_to_spec` now read authoritative DB columns
  (`status`, `active`) instead of trusting the JSON blob. Fixes stale-status display bugs.
- **2026-06-18** — 8 bad `agent_specs` rows with `(domain:...)` suffix deactivated in DB.
  `build_from_spec` and `_mint_created_spec` now sanitize agent names to valid Python IDs.
- **2026-06-16** — `sentinel-memory-worker` entry point ships as a separate PM2 process;
  CrawlScheduler + MemoryWorker co-routines. 4 connectors: web, YouTube, email, social.
- **2026-06-15** — `/accounts` routes removed; Memory Sources form moved to project memory tab.
  Entity slug: `projectName.trim().toLowerCase().replace(/\s+/g, '-')`.
- **2026-06-14** — vLLM → Gemini → Claude automatic fallback with UI notification banner.
- **2026-06-14** — `find_deals` e-commerce domain uses SearchAPI `google_shopping_search`
  (40 priced listings); provider collision with `google_search` fixed (non-pinned only).

---

## Recently completed

- **2026-06-18** — E2E sweep (13 pages). Fixed: `_row_to_task` stale status, `_row_to_spec`
  active column, agent spec name sanitization, bad DB spec deactivation. 4 commits pushed.
- **2026-06-16** — Self-Driving Memory Brain (18 commits, 946 tests): CrawlScheduler,
  MemoryWorker, 4 connectors (web/YouTube/email/social), SSRF guard hardened (DNS rebinding),
  30-route JSON API, Memory Sources CRUD on project Memory tab.
- **2026-06-15** — Next.js full frontend overhaul: Projects/Tasks/Agents/Settings/Memory CRUD,
  KB redesign (3-cat sources, 9-picker, chunk drawer), task detail (accordion + markdown),
  citations hardened (0→5+), live pipeline UI with agent handover animation.
- **2026-06-14** — Shopping search: `find_deals` + `product_research` domains, SearchAPI
  google_shopping_search, 40 priced listings proven live. SENTINEL-022.
- **2026-06-13** — Mobile UX audit + responsive implementation: off-canvas drawer, phone
  breakpoint, list-first /projects layout. 390px→4K verified. 835 tests.
- **2026-06-12** — Persona library: editor/generator page + auto-selection on task create.
  813 tests.
- **2026-06-11** — Challenge submission shipped. Full async pipeline with live agent timeline,
  project context field, KB auto-ingest post-run, 783 tests at submission.

---

## Known issues & gotchas

- **Always restart backend after code changes** — Python imports cached at process start.
  `PORT=8094 .venv/bin/python3 -m sentinel.web.app` (or PM2 restart on server).
- **Frontend port** — Must start as `PORT=3001 npm start` (or `npm run dev`). Default port
  3000 does NOT match nginx `proxy_pass`. A restart without `PORT=3001` → 502 on the domain.
- **vLLM 26B tool-call parser** missing upstream — `agent_spec_id` tool-calling on the 26B
  omni model fails. Workaround: 12B for tool-calls, 26B for reasoning only (ADR-0001).
- **KB hybrid search ChromaDB path mismatch** — write path was `data/kb/kb_chroma`, read path
  `data/kb`. Aligned in 2026-06-16 fix. If KB returns 0 chunks, verify path consistency.
- **Citations sourcing** — synthesizer doesn't output a `sources` field yet; citations display
  comes from step-level `finding_texts`, not from a structured sources list.
- **Shopping domains** — `product_research` provider collision with `google_search` fixed for
  non-pinned modes only. TD-SENTINEL-022 tracks the pinned-mode case.
- **Env:** Python 3.14.4; venv at `.venv`. ADK 2.2.0. Run via `. .venv/bin/activate`.
- **Tests:** always run with `SENTINEL_DATA_DIR=$(mktemp -d)` — DB isolation required.
- **Config access:** always via `sentinel.config.get_config()` — never instantiate directly.

---

## Open questions

- Memory worker on server: is CrawlScheduler running as a third PM2 process, or embedded in
  the backend? (Check `pm2 list` — should be a separate `sentinel-memory-worker` entry.)
- Synthesizer `sources` field: when to wire structured citations from the DAG output?

---

## Conventions specific to this repo

- **Feature flags:** `research.two_tier`, `coordinator.enabled`, `strategy.enabled` default
  `False` (ship dark). Never change defaults without a spec step.
- **Boundary rule:** `MemoryStore.recall(entity, allowed_boundaries)` is the ONLY place that
  enforces the public/private memory boundary. Never read the memory table elsewhere.
- **Agent name safety:** always `re.sub(r"[^a-zA-Z0-9_]", "_", name)` before passing to
  `make_agent` — ADK `LlmAgent` rejects names that aren't valid Python identifiers.
- **Spec format:** SENTINEL specs use `.md` (AP-11 waiver). BiltIQ specs use `.html`.
- **Search tool extension:** register a `_fetcher` in `tools/public/web_search._FETCHERS`.

---

## Glossary deltas

- **two-tier** — 12B tool-callers (pass1, non-streamed) → 26B reasoners (pass2, SSE streamed).
- **SearXNG** — self-hosted metasearch; primary sovereign keyless search. `SEARXNG_URL` env.
- **MemoryWorker** — background worker polling a job queue; CrawlScheduler feeds it on cron.
- **find_deals** — e-commerce DAG capability; uses SearchAPI `google_shopping_search`.
- **entity slug** — project name → `trim().toLowerCase().replace(/\s+/g, '-')` for memory URLs.
- **_leaf_semaphore** — process-wide asyncio.Semaphore for concurrent ADK runner cap.

---

## Archive

Older entries (>30 days) live in `/docs/memory-archive/YYYY-MM.md`.
