# MEMORY.md — Project State (Living Document)

**Purpose:** Persistent context for Claude Code (and any AI-IDE) across sessions. The agent reads this on session start and updates it after meaningful work. Prevents every session from starting cold.

**Update rules:**
- Keep under 200 lines. If it grows past that, the `memory-curator` skill archives older entries to `/docs/memory-archive/YYYY-MM.md`.
- Update at end of every meaningful session (`memory-curator` skill).
- Use the structure below. Don't add new top-level sections without an ADR.
- Don't store secrets, credentials, or PII here.

**Last updated:** YYYY-MM-DD by [@dev or session-id]

---

## Project at a glance

**Sentinel — Sovereign Intelligence Agent.** An autonomous research agent for regulated
SMBs (BFSI / healthcare / government). One orchestrator, two modes — competitor
intelligence and client/account intelligence — over a shared MCP tool layer. It gathers
public signal via Gemini grounded search and private context via scoped MCP connections
(CRM, docs, email/calendar), reasons across both, and writes a structured battlecard /
account brief back to the user's own workspace as a durable artifact. Core thesis:
**public and private data live behind separate tool boundaries**, so the same agent runs
cloud-native for demo and sovereign on-prem (vLLM) for production without rework.

**Status:** Proof of concept — built for the Google for Startups AI Agents Challenge (Track 1: Build). Submission due 2026-06-11 17:00 PT.
**Deployment:** Demo = Cloud Run + Vertex AI (Gemini 2.x). Production target = customer-controlled on-prem inference (vLLM behind LLM gateway).
**Compliance mode:** `cloud_ok` (demo); architecture is `on_prem_required`-portable by design.
**Primary stakeholders:** Aarna Tech Consultants Pvt. Ltd. (BiltIQ AI); challenge judges (Google Cloud / DeepMind).

---

## Current focus (this week)

What the team is actively working on right now.

- **Active sprint:** Challenge build, 2026-06-07 → 2026-06-11 17:00 PT. Goal: win Google AI Agents Challenge (Track 1: Build, APAC).
- **Top 3 tasks in flight:**
  1. Production increments via the spec→design→plan→build loop — **001/002/003/004/005/011a/009/010/011b/008 BUILT, 266 tests green**. The **Intelligence-to-Action program (008/009/010) + A2A coordinator (011) is COMPLETE.** All ship dark except 010 (additive). Remaining backlog: 006 Connectors; two-tier *inside* the coordinator (008 fast-follow).
  2. Live run + Workspace MCP OAuth (real private connector) — **BLOCKED on user: GOOGLE_API_KEY in `.env` + Workspace OAuth**. Server live at :8080 (run pages, Settings, Accounts).
  3. **Now the critical path:** Cloud Run deploy (run the script with a key) + demo video — pending user GCP actions. Deadline 2026-06-11 17:00 PT.
- **Top 3 risks:**
  1. 4-day window + maximal scope (real Workspace, all-3 writers, full vLLM proof) → mitigate with fallback ladder (see docs/srs.md).
  2. Sovereignty claim discounted by judges → mitigated: boundary is structural (test_boundary.py) + vLLM gateway is real (test_gateway.py).
  3. Live demo depends on user's GCP account actions (OAuth, deploy) → prep everything to one-command-away.

---

## Recent decisions (last 30 days)

_(no decisions recorded)_

## Recently completed

What shipped recently. Move items here from "Current focus" once merged.

- 2026-06-08 — **SENTINEL-012 Universal Research Agent — ALL 4 PHASES / 17 STEPS, 400 tests (+119 from 281), 0 regressions. CLOSED (`reflect.md` written).** Project→Task→Orchestrator→typed/cited Result platform, fully additive over the shipped competitor/client modes (AC-9 golden never broke). **Phase 0** role-partition + `run_step` + declarative `ResearchModeSpec`. **Phase 1** Project/Task/Plan schemas + store (ADR-0003) + `/projects` UI. **Phase 2** `self_profile`+`compare`+program-strategy skills, persona render, DAG budget/cache, code+model graders. **Phase 3** orchestrator planner (Task→DAG), `AgentRegistry` + persisted `agent_specs` table (ADR-0004, reuse-by-`(eval_score,version)`), autonomy gate (propose default; `run_dag` never fires until approved), prompt-injection stance (NEW `tools/sanitize.py` fences scraped text as `[SOURCE MATERIAL …]`; tools/boundary fixed on spec at build → content can't escalate; created specs PUBLIC-only+tool-free). **2 ADRs (0003 store, 0004 registry table).** **Tech debt TD-1/2/3/4 CLOSED 2026-06-08** (suite 400→410, +10, zero regression): TD-1 created-capability *execution* now wired (`_run_created_step` builds the registry spec via `build_from_spec`; seam test crosses mint→persist→run); TD-2 persona render + TD-3 `model_grade` attached via a new additive `run_plan` finalize pass (`Result.persona_rendered`/`Result.grade`; dark by default, `SENTINEL_GRADE_SAMPLE` env); TD-4 web-route body tests (caught + fixed a real bug: GET /plan passed a `datetime` for `Task.created_at`). Residual: AC-20 golden eval-set *files* per domain (data-entry; `load_eval_set` mechanism wired). Also fixed memory-spine `task_state_change` schema to accept `SENTINEL-` prefix + emitted the closure event. See `docs/specs/SENTINEL-012/reflect.md` §6.1.

- 2026-06-07 — **SENTINEL-008 Research Depth** (266 tests, +23). Declarative research modes + two-tier research, both behind `research.two_tier` (off, byte-identical default). A mode is now **data** — `ResearchModeSpec` = ordered `list[StepSpec]` + output schema (`COMPETITOR_SPEC`/`CLIENT_SPEC` in NEW `agent/modes/spec.py`); the single generic constructor `build_step_agents(spec, …, two_tier=)` builds the flat agent list, `build_pipeline` wraps it in a `SequentialAgent`. **A new mode is config, not engine code** (AC-7, proven by `test_new_mode_builds_with_no_engine_edit`). **Reconciliation (008 triad predated 009/011b):** `build_*_subagents` (011b coordinator source) delegate to `build_step_agents(two_tier=False)` and map by `output_key` → coordinator untouched, zero 011b regression; the 009 strategist stays appended at the mode-builder level (overlay, not a step) → graph byte-identical (AC-6). Two-tier: cheap `<mode>.extractor` (12B, `ExtractionSet`, no tools, +1 LLM call) distils `{public_findings}`→`{extractions}` before the synth's `_2t` prompt; `orchestrator._merge_extraction_gaps` folds gaps onto the artifact (deterministic, fail-soft). Provenance: `RunRecord.sources` + 1-based `run_seq` (additive SQLite `ALTER`; old rows → `[]`/`0`), rendered on the account timeline (legacy row → neutral dash, never `#0`). Extractor obeys `resolve_model(cloud_allowed=)` → no Gemini in `on_prem_required` (AC-10). **Intelligence-to-Action program (008/009/010) complete.** Fast-follow: two-tier inside the coordinator.
- 2026-06-07 — **SENTINEL-011b Coordinator parity** (243 tests, +8). 009 strategist wrapped as an `AgentTool` specialist in both modes (state-delta forwards `output_key="strategy"` → `_merge_strategy` unchanged); 010 priority wired as a deterministic LLM-free **post-run hook** (`_recompute_priority`), not an AgentTool. Ships dark via `coordinator.enabled`.
- 2026-06-07 — **SENTINEL-010 Account Prioritization** (235 tests, +23). Pure-Python `priority/` — one signal `REGISTRY`, 5 seed signals, deterministic 0-100 score (no LLM/network), boundary-safe cited reasons, persisted snapshots, `/focus` route + dashboard card. Additive (enabled).
- 2026-06-07 — **SENTINEL-009 Strategy & Action Plan** (212 tests, +30). Tool-free strategist → `StrategyOverlay` (assessment + action_plan + objection_handling) shaped by admin-editable Markdown playbooks; `maybe_strategist` appends it per pipeline; `_merge_strategy` deterministic + fail-soft. Ships dark (`strategy.enabled=False`).
- 2026-06-07 — **SENTINEL-011a Tiering + Coordinator backbone** (182 tests, +37). Gateway auth-by-host (`ATCUALITY_API_KEY` for `*.atcuality.com`), `Role` tiering (12B tool-callers / 26B reasoners) + reasoner-tool-free build guard, `CoordinatorConfig` + `agent/coordinator.py` (`LlmAgent` over `AgentTool` specialists), orchestrator fail-soft to Sequential. Byte-identical default (`backend.roles=None`, `coordinator.enabled=False`).
- 2026-06-07 — **SENTINEL-005 Governance & Pluggable Search** (143 tests, +30). Wired `governance.compliance_mode` into orchestrator routing: `on_prem_required` ⇒ **structural zero-Gemini** (NEW `agent/governance.py` → `cloud_allowed`/`effective_backend`/`effective_search_provider`; `_build.resolve_model(..., cloud_allowed)` forces vllm + ignores `pin_gemini`; provable by introspecting built agents). `block_cloud_on_private` forces on-prem for any client run touching the private boundary. Public search is now **pluggable** (NEW `tools/public/web_search.py` → `get_search_tool(provider)`): `gemini`→`google_search`; `duckduckgo`(keyless)/`brave`/`serpapi`→ httpx **function tools** (typed `search(query)`, 10s timeout, fail-soft `{status:error}`, env keys `BRAVE_API_KEY`/`SERPAPI_API_KEY` read inside the call). NEW `SearchConfig{provider,results,onprem_fallback}` in config (one center; env `SENTINEL_SEARCH_PROVIDER` seeds first-boot). Settings: NEW Governance + Search sections + routes `/settings/governance`,`/settings/search` (key pills, validate-before-commit). Orchestrator trace records `compliance=`/`cloud_allowed=`/`search=`. New-run form reflects sovereign mode honestly (disables the Gemini toggle + "cloud blocked by governance" chip when on_prem_required). 145 tests. **Ships dark**: default `cloud_ok`+`gemini` = byte-identical to before (SENTINEL-002 boundary + 004 tests untouched). DEFERRED: audit-log persistence sub-increment.
- 2026-06-07 — **SENTINEL-004 Reports & Accounts** (109 tests, +17). New `/accounts` (entity index) + `/accounts/{entity}` (run timeline + boundary-separated memory + cumulative provenance donut) + POST `/accounts/{entity}/purge` (confirm-gated, 303 redirect). KEY: account page reads via NEW read-only `MemoryStore.list_for_entity` (no reinforcement / no budget / no mode gate) — NOT `recall`. AC-5 proven structurally (SELECT-only; strength/access_count unchanged after a page fetch). `recall` + the boundary invariant untouched. `RunStore.entities()`/`runs_for()` + `EntitySummary.from_runs()` (shared aggregation, AC-6 consistency). Artifacts/dashboard rows now link target→account.
- 2026-06-07 — **SENTINEL-003 Settings UI** (92 tests). View/edit live `SentinelConfig` (Backends/Generation/Memory/Agents/Prompts); validate-before-commit on a deep copy, no-restart pickup, secrets shown as a boolean pill only (never rendered/persisted).
- 2026-06-07 — Web demo layer: `src/sentinel/web/{app,render}.py` (FastAPI form + HTML artifact renderer with public/private provenance badges, XSS-escaped). 6 web tests via stubbed orchestrator (no API key). `sentinel-web` entrypoint.
- 2026-06-07 — Deploy artifacts: `Dockerfile` (Cloud Run, binds $PORT), `.dockerignore`, `deploy/cloudrun.sh` (one-command, `--source .`, APAC `asia-south1`, `--allow-unauthenticated`).
- 2026-06-07 — Architecture diagram (`docs/architecture/diagram.html` for slides, `diagram.mmd` Mermaid source) + judge-facing `README.md`.
- 2026-06-07 — **Dashboard UI rebuild**: `web/render.py` is now a full app shell (collapsible sidebar persisted via localStorage, top bar) + pages: Dashboard (KPI cards + Chart.js charts — signature public/private provenance donut, runs-by-mode bar, backend-usage donut, recent-runs table), New Run (form), Artifacts, Backends, Architecture (iframes `/architecture/diagram`). In-memory `STORE` in `web/app.py` feeds charts live (session-scoped, no DB). Routes: `/ /new /run /artifacts /backends /architecture /architecture/diagram /healthz`. Charts via Chart.js CDN.
- 2026-06-07 — **Dual backend + live toggle**: gateway `get_model(backend)`/`active_backend(backend)`/`resolve_backend()` accept per-run override; vLLM default model now `google/gemma-3-4b-it` (Gemma). Threaded through mode builders, orchestrator (`run_async(..., backend=)`), CLI (`--backend`), and UI segmented toggle (Cloud·Gemini / On-prem·Gemma). Presets `.env.gemini` + `.env.vllm`; `deploy/vllm-compose.yml` serves Gemma locally. 28 tests green. NOTE: toggle swaps *reasoning* LLM only — public `google_search` grounding stays Gemini-native by design.

---

## Known issues & gotchas

Things the next session needs to know to avoid wasted time.

- **Env:** Python 3.14.4; venv at `.venv`. ADK 2.2.0. Run via `. .venv/bin/activate`. Package installed editable (`pip install -e .`).
- **ADK deprecation:** `SequentialAgent` warns "use Workflow instead" in 2.2.0. Works fine; revisit only if it breaks.
- **Grounding (updated by 005):** `google_search` is Gemini-native — does NOT run on vLLM. But public search is now **pluggable** (`search.provider`): on-prem runs use a non-Gemini **function tool** (duckduckgo/brave/serpapi) the reasoning model calls, so a sovereign run still has web eyes. `gemini` provider remains the default and stays Gemini-pinned.
- **LiteLlm/MCP:** require `google-adk[extensions]` + `mcp` (both installed). `LiteLlm` import fails without extensions.
- **To run live:** need `GOOGLE_API_KEY` (AI Studio) in `.env` (copy from `.env.example`). Without it, agents construct + tests pass but a real run errors at the model call.
- **CLI:** `python -m sentinel "Stripe" --mode competitor`. Artifacts land in `artifacts_out/`.
- **Memory (SENTINEL-002):** durable state in `data/sentinel.db` (SQLite, WAL, gitignored). Override path with `SENTINEL_DATA_DIR`. **Run tests with `SENTINEL_DATA_DIR=$(mktemp -d)`** to stay hermetic (web tests read `RunStore`). Memory is config-gated by `cfg.memory.entity_memory` and fully fail-soft — a db error degrades to "no memory", never breaks a run. The boundary rule lives ONLY in `MemoryStore.recall`; never read the table elsewhere.

---

## Open questions

_(no open questions)_

## Code areas under active change

Where multiple people are working concurrently.

- `path/to/module/` — [@owner] is refactoring [reason]; expect merge conflicts
- `path/to/file.py` — [@owner] is adding [feature]; coordinate before editing

---

## Conventions specific to this repo

Things that are *not* in `AGENT_RULES.md` because they only apply to this repo.

- [e.g., "All datetime fields use `datetime_utc` suffix in DB columns"]
- [e.g., "Error responses use envelope: `{'error': {'code': str, 'message': str}}`"]

---

## Glossary deltas

Terms introduced or changed since `/docs/GLOSSARY.md` was last updated. When this list gets long, fold into the glossary and clear here.

- [Term] — [Definition]

---

## Session log (last 5 sessions)

Brief notes from recent sessions. Helps the next session understand what was tried and why.

### YYYY-MM-DD HH:MM — [@dev or session-id]
- Worked on: [BILTIQ-XXX]
- Did: [1-2 lines]
- Discovered: [if anything noteworthy]
- Next session should: [recommendation]

---

## Active task

- _(none in flight)_ — last closed: **SENTINEL-012** _2026-06-08 08:27_

## Today's activity

_(no activity recorded today)_

## Open blockers

_(no open blockers)_

## Doctor installs

_(no doctor installs recorded yet)_

## Documentation updates

_(no documentation updates recorded yet)_

## Archive

Older entries (>30 days) live in `/docs/memory-archive/YYYY-MM.md`.
