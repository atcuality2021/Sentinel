# SENTINEL-005 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** ✅ Built — 143 tests green (AC-1..AC-11)

Atomic, ordered; each ends green. No live LLM/network in any test (httpx mocked). Test IDs → spec ACs.

---

### Step 1 — `SearchConfig` + governance wiring in schema/defaults
Add `SearchConfig{provider, results, onprem_fallback}` to `config/schema.py`; add `search` to
`SentinelConfig`. Seed `search.provider` from `SENTINEL_SEARCH_PROVIDER` in `defaults.py` (first-boot).
**Test:** default cfg has `search.provider=="gemini"`; round-trips through YAML.

### Step 2 — `agent/governance.py` helpers
`cloud_allowed`, `effective_backend(cfg, requested, *, private)`, `effective_search_provider(cfg, *,
allow_cloud)`.
**Test (AC-1/5/8):** on_prem_required → cloud_allowed False + effective_backend "vllm";
block_cloud_on_private + private=True → "vllm"; provider gemini + no cloud → onprem_fallback.

### Step 3 — `tools/public/web_search.py` provider layer
`get_search_tool(provider, *, results)`; function tools for duckduckgo/brave/serpapi (httpx, timeout,
fail-soft, typed dict). gemini → `google_search`.
**Test (AC-4/6/7):** registry returns google_search for gemini, a callable for others; mocked httpx
→ parsed results; network error → `{"status":"error"}` (no raise); brave/serpapi read env key.

### Step 4 — `resolve_model` honors governance
`resolve_model(cfg, ac, mode_backend, *, cloud_allowed)`: not cloud-allowed ⇒ force vllm + ignore
pin_gemini.
**Test (AC-2/3):** on_prem_required → every agent's model is LiteLlm (no str/Gemini); cloud_ok →
pin_gemini agent is a str (Gemini), unchanged.

### Step 5 — mode builders use the resolved provider
`build_competitor_agent` / `build_client_agent` take `cloud_allowed` + `provider`; public_research
tool = `get_search_tool(provider)`.
**Test (AC-4):** competitor in on_prem_required has no `google_search` in any toolset; has the
duckduckgo tool; client private MCP path unchanged.

### Step 6 — orchestrator derives + traces governance
`run_async`: compute private/eff_backend/cloud_ok/provider; pass down; trace `search={provider}` +
`backend={eff}`.
**Test (AC-10):** trace contains the effective provider; on_prem_required run builds no Gemini object.

### Step 7 — Settings: Governance + Search sections
`web/settings.py` `apply_governance` / `apply_search` (validate enums/results≥1). `render.py`
sections + key pills. `app.py` routes `/settings/governance`, `/settings/search`. New-run "sovereign"
chip when forced.
**Test (AC-9):** POST governance/search persists to YAML; no secret in YAML/HTML; pills reflect
`BRAVE_API_KEY`/`SERPAPI_API_KEY`; bad enum → err banner.

### Step 8 — Housekeeping + no-regression
Docstrings; update MEMORY.md, specs/README.md, .remember. 
**Test (AC-11):** full `pytest -q` green; SENTINEL-002 boundary + SENTINEL-004 tests untouched.

---

## Definition of done
- AC-1..AC-11 green. An operator picks compliance mode + search provider in Settings; on_prem_required
  provably builds **zero** Gemini objects and uses a non-cloud search tool on Gemma; cloud_ok is
  byte-identical to today. Provider keys are env-only, shown as pills.

## Estimate
~8 steps. Heaviest: the provider layer (Step 3) + the routing wiring (Steps 4-6). Default config
reproduces current behaviour, so it ships dark until policy is changed.
