# SENTINEL-005 — Governance & Pluggable Search (Sovereignty Policy)

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (`GovernanceConfig` stub, config store), gateway (`build_model`), mode builders
**Blocks:** audit log / cost view (later 005 sub-increment)

---

## 1. Context / problem

Today the cloud/on-prem split is hardwired: public web research **always** uses Gemini's native
`google_search`, even when the user wants a sovereign run. The `governance.compliance_mode` field
exists in the schema but is **not wired** to anything. Operators in regulated settings need a single
switch that the orchestrator obeys: *on-prem ⇒ no cloud at all; cloud-ok ⇒ Gemini grounding allowed.*
And "grounding" must not be Gemini-only — the public-search tool should be **pluggable** (Gemini,
DuckDuckGo, Brave, SerpAPI) so a no-cloud run still has eyes on the web via Gemma function-calling.

## 2. Goal / non-goals

**Goal:**
1. Wire `governance.compliance_mode` into the orchestrator's model + tool routing ("the brain").
2. A **pluggable public-search provider**: `gemini | duckduckgo | brave | serpapi`, config-selectable.
3. Surface both on the **Settings page** (one center); provider keys (Brave/SerpAPI) are secrets → env.
4. `on_prem_required` ⇒ **no Gemini anywhere** (reasoning forced to vLLM, grounding forced to a
   non-Gemini provider); `block_cloud_on_private` ⇒ any run touching the private boundary is forced
   on-prem for that run.

**Non-goals:** audit-log persistence + cost view (next 005 sub-increment); per-agent provider
override; result re-ranking/caching; non-search MCP tools (006).

## 3. Personas
P3 **Compliance** (sets on_prem_required, must trust no cloud egress), P2 **Admin** (picks a search
provider + keys), P1 **Analyst** (runs; sees which brain/provider was used in the trace).

## 4. Acceptance criteria (testable, binary)

- [ ] **AC-1** `cloud_allowed(cfg)` is `False` iff `compliance_mode == "on_prem_required"`.
- [ ] **AC-2** When not cloud-allowed, `resolve_model` returns a **vLLM** model for **every** agent —
  `pin_gemini` is ignored (no Gemini object is ever constructed).
- [ ] **AC-3** When cloud-allowed, behaviour is unchanged: grounding agents stay Gemini (`pin_gemini`).
- [ ] **AC-4** The public-research agent's tool is the configured provider: `gemini`→`google_search`;
  `duckduckgo|brave|serpapi`→ the matching function tool.
- [ ] **AC-5** In `on_prem_required`, the effective provider is **never** `gemini`: if config says
  `gemini`, it is overridden to the configured non-cloud fallback (default `duckduckgo`).
- [ ] **AC-6** Brave/SerpAPI tools read their key from env (`BRAVE_API_KEY`/`SERPAPI_API_KEY`); the
  key never appears in config/YAML or page HTML (boolean pill only).
- [ ] **AC-7** Each non-Gemini search tool returns a typed result list and **fails soft** (network
  error ⇒ `{"status":"error",...}`, never an exception that kills the run); all have a timeout.
- [ ] **AC-8** `block_cloud_on_private = True` + a connected private boundary ⇒ that run is forced
  on-prem (no Gemini), regardless of `compliance_mode`/toggle.
- [ ] **AC-9** Settings page has a **Governance** section (compliance_mode select, audit_log,
  block_cloud_on_private) and a **Search** section (provider select, results count, Brave/SerpAPI key
  pills); saving persists to YAML (no secret written).
- [ ] **AC-10** The run trace records the effective backend + provider (e.g. `search=duckduckgo`).
- [ ] **AC-11** All existing tests pass; the SENTINEL-002 boundary invariant and SENTINEL-004 read
  path are unchanged.

## 5. Functional requirements
- **FR-1** `governance.py`: `cloud_allowed(cfg)`, `effective_backend(cfg, requested, *, private)`,
  `effective_search_provider(cfg, *, cloud_allowed)`.
- **FR-2** `SearchConfig{provider, results, onprem_fallback}` added to `SentinelConfig`.
- **FR-3** `tools/public/web_search.py`: `get_search_tool(provider, *, results)` → an ADK tool;
  function tools for duckduckgo/brave/serpapi (httpx, timeout, fail-soft, typed dict result).
- **FR-4** `resolve_model` + both mode builders consult governance for model + grounding tool.
- **FR-5** Settings routes `/settings/governance`, `/settings/search`; render sections + key pills.

## 6. Non-functional
- **NFR-1** Secrets (provider keys) env-only; shown as set/not-set pills (one center).
- **NFR-2** No-cloud guarantee in on_prem_required is **structural** (no Gemini object built, no
  `google_search` attached) — provable by introspection, not prompt.
- **NFR-3** External search calls: explicit timeout, fail-soft; typed; no `Any`.
- **NFR-4** Server-rendered HTML; all text escaped.

## 7. Risks
- **R-1 silent cloud egress** in on_prem mode → structural block + an introspection test (AC-2/AC-5).
- **R-2 DDG/scraping fragility** → fail-soft to a gap; Brave/SerpAPI are the robust paths.
- **R-3 provider/key missing** → pill shows not-set; tool returns an error result, run degrades to a
  gap rather than crashing (AC-7).

## 8. Open questions
- **OQ-1** Default on-prem fallback provider when config says gemini? *Proposed:* `duckduckgo`
  (keyless), so on_prem_required works with zero extra setup.
- **OQ-2** Audit-log persistence — deferred to a 005 sub-increment (this increment is the policy +
  search layer). *Proposed:* keep `audit_log` toggle visible; wire the sink next.
