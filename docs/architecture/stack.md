# Stack — Libraries, Wrappers, and Utilities

**Purpose:** The catalog of what already exists in this repo. Read this **before writing any new utility, client, or wrapper** — Anti-Pattern #1 (Duplication) and #2 (Abstraction Bypass) defenses.

**Update rules:**
- Every new utility / wrapper added to the repo gets an entry here in the same PR.
- Every wrapper that becomes deprecated moves to `## Deprecated` with the replacement noted.
- Reviewed at each milestone / architecture review.

---

## Languages & runtimes

- Python 3.11+ (only runtime; no TypeScript/Node — the dashboard is server-rendered HTML from Python)

---

## Web / API framework

- **FastAPI ≥ 0.110** — the dashboard + settings server (`src/sentinel/web/app.py`).
- Server-rendered HTML via `web/render.py` (no SPA, no client framework). All text escaped.

---

## Agent / LLM stack

- **Google ADK 2.2.0** (`google-adk[extensions]`) — orchestration. In use: `Agent`/`LlmAgent`,
  `SequentialAgent`, `InMemoryRunner`, `tools.AgentTool` (coordinator), `output_schema`,
  `google_search` builtin. **A2A** (`RemoteA2aAgent`/`to_a2a`) is NOT yet available — needs the
  `a2a-sdk` dependency (ADR-0001, SENTINEL-011 Phase 2).
- **google-genai ≥ 1.0** — Gemini models (cloud mode) + grounded search.
- **pydantic v2** — every schema/config (`model_validate`/`model_dump`; never `.dict()`/`.parse_obj`).
- **Models (by ROLE — see `resolve_model`):** tool-calling roles → `gemma-4-12B`
  (`GEMMA_12B_API_BASE`); reasoning roles → `gemma-4-26B` (`GEMMA_26B_API_BASE`); cloud option →
  Gemini. The Gemma gateway (atcuality) is OpenAI-compatible; key `ATCUALITY_API_KEY` (env only).
  ⚠ 26B native tool-calling is broken — never give a reasoning agent tools (ADR-0001).

---

## Database & storage

- **SQLite** — single file under `SENTINEL_DATA_DIR`; holds memory + run log (`memory/store.py`).
  No Postgres / Qdrant / Redis / MinIO — deliberately light, on-prem-portable.
- Artifacts written as **Markdown** (`artifacts/writer.py`); workspace/MCP write-back is later (006).

---

## Internal wrappers — use these, do not import the raw library

| What | Wrapper module | Wraps | Why |
|---|---|---|---|
| Config (source of truth) | `sentinel.config.get_config()` → `SentinelConfig` | YAML + pydantic | One center for all non-secret runtime config; validate-before-commit |
| Config persistence | `sentinel.config.store` | YAML file IO | Atomic read/write of `sentinel.config.yaml` |
| Prompt validation | `sentinel.config.render.render_prompt` | template `{vars}` | Validates required/reserved vars at build time (RESERVED_VARS) |
| Model resolution | `sentinel.llm.gateway.resolve_model` / `build_model` | ADK model objects | Role→model, governance (`cloud_allowed`), Gemini↔Gemma swap |
| Agent builder | `sentinel.agent.modes._build.make_agent` | ADK `Agent` | Config→agent; model/prompt/generation/tools/`instruction_suffix` in one place |
| Governance routing | `sentinel.agent.governance` | — | `cloud_allowed`, `effective_backend`, `effective_search_provider` |
| Entity memory | `sentinel.memory.MemoryStore` | SQLite | Boundary-filtered `recall` (the invariant choke-point), SM-2 reinforcement |
| Run log | `sentinel.memory.RunStore` | SQLite | Episodic run records, `entities()`/`runs_for()`/`latest_for()`, delta |
| Public search tool | `sentinel.tools.public.web_search.get_search_tool` | google_search / httpx | Pluggable provider, timeout, fail-soft, typed result |
| Private connectors | `sentinel.tools.private.workspace_mcp` | MCP toolset | Scoped private boundary; `private_boundary_configured()` |
| Artifact write | `sentinel.artifacts.writer.get_writer` | file IO | Schema-validated artifact persistence |

> If a category needs a wrapper and none exists, that's an ADR-worthy gap — flag it.

---

## Shared utilities

| What | Module | Use when |
|---|---|---|
| UTC datetime | `sentinel.memory.schema.utcnow()` | Any memory/run timestamp (tz-aware) |
| Entity key | `sentinel.memory.schema.normalize_entity()` | Any entity name → canonical key |
| Content hash | `sentinel.memory.schema.content_hash()` | Dedup key for memory entries |
| Time-decay / reinforcement | `sentinel.memory.strength` | `decayed_strength`, `reinforce` (SM-2) |

Secrets: env-only, read at the call site (e.g. `ATCUALITY_API_KEY`, `GOOGLE_API_KEY`,
`BRAVE_API_KEY`, `SERPAPI_API_KEY`). Never in config YAML, code, or HTML — shown as set/not-set pills.

---

## Test fixtures / conventions

- Tests live in `tests/` (`test_boundary`, `test_governance`, `test_gateway`, `test_memory`,
  `test_config`, `test_settings`, `test_web`, `test_accounts`, `test_artifacts`).
- **Hermetic:** run with `SENTINEL_DATA_DIR=$(mktemp -d) .venv/bin/python -m pytest -q`. No live
  LLM/network — mock `httpx`, seed session state, or introspect built agents.
- The boundary + sovereignty guarantees are proven by **introspecting built agents** (no Gemini
  object / no `google_search` in `on_prem_required`), not by output assertions.

---

## Deprecated

| Deprecated | Replacement | Removal target |
|---|---|---|
| `google/gemma-3-4b-it` (flat on-prem default) | Gemma-4 role map (12B/26B) | with SENTINEL-011 (ADR-0001) |

---

## When to add a new wrapper

Add a wrapper when the same external library is used in 3+ files with the same boilerplate, or has
cross-cutting concerns (auth, retry, logging, governance) that must be centralized, or when swapping
the library should not require rewriting every caller. List it here in the same PR — the
`code-reviewer` skill flags missing entries.
