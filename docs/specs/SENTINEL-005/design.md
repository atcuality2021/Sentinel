# SENTINEL-005 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture

One new governance seam + one new pluggable-tool layer, both read from `SentinelConfig` (the one
center). No change to `recall`, the boundary invariant, or the SENTINEL-004 read path.

```
run_async(target, mode, backend, *, private?)
  └─ governance.effective_backend(cfg, backend, private=private)  → "gemini" | "vllm"   (AC-2,8)
  └─ governance.cloud_allowed(cfg)                                 → bool                (AC-1)
  └─ governance.effective_search_provider(cfg, cloud_allowed)      → provider            (AC-4,5)
        │
  mode builder:
     resolve_model(cfg, ac, mode_backend, cloud_allowed)          → str | LiteLlm       (AC-2,3)
     get_search_tool(provider, results)                           → google_search | fn  (AC-4)
```

**The no-cloud guarantee (NFR-2) is structural:** when `cloud_allowed` is False, (a) `resolve_model`
never builds a Gemini object — `pin_gemini` is ignored and the backend is forced `vllm`; and (b) the
public-research agent is given a non-Gemini function tool, never `google_search`. Provable by
introspecting the built agents (no `str` model, no `google_search` in any toolset).

## 2. Config (`config/schema.py`, `config/defaults.py`)

```python
class SearchConfig(BaseModel):
    provider: Literal["gemini","duckduckgo","brave","serpapi"] = "gemini"
    results: int = 5
    onprem_fallback: Literal["duckduckgo","brave","serpapi"] = "duckduckgo"  # used when on_prem + provider==gemini

# SentinelConfig gains:  search: SearchConfig = Field(default_factory=SearchConfig)
# GovernanceConfig already has: compliance_mode, audit_log, block_cloud_on_private (wire them)
```
`defaults.py` seeds `search.provider` from `SENTINEL_SEARCH_PROVIDER` (first-boot only, same rule).

## 3. Governance helpers (`agent/governance.py`, NEW)

```python
def cloud_allowed(cfg) -> bool:
    return cfg.governance.compliance_mode != "on_prem_required"

def effective_backend(cfg, requested=None, *, private=False) -> str:
    # on_prem_required → vllm; block_cloud_on_private + private boundary → vllm; else requested|default
    if not cloud_allowed(cfg): return "vllm"
    if private and cfg.governance.block_cloud_on_private: return "vllm"
    return resolve_backend(requested or cfg.backend.default)

def effective_search_provider(cfg, *, allow_cloud: bool) -> str:
    p = cfg.search.provider
    if not allow_cloud and p == "gemini":     # AC-5: never gemini on-prem
        return cfg.search.onprem_fallback
    return p
```

## 4. Pluggable search (`tools/public/web_search.py`, NEW)

`get_search_tool(provider, *, results)` →
- `gemini` → the ADK builtin `google_search` (cloud, Gemini-pinned).
- `duckduckgo|brave|serpapi` → a module-level **function tool** (typed `query: str` + docstring, the
  ADK pattern) the reasoning model calls via function-calling (proven to work on Gemma).

Each non-Gemini tool: `httpx.get(..., timeout=10)`, fail-soft, returns
`{"status":"success","results":[{"title","url","snippet"}, …]}` or `{"status":"error","message":…}`.
- **duckduckgo**: keyless — `https://api.duckduckgo.com/?q=&format=json` (Instant Answer; best-effort).
- **brave**: `https://api.search.brave.com/res/v1/web/search` + header `X-Subscription-Token:
  $BRAVE_API_KEY`.
- **serpapi**: `https://serpapi.com/search.json?engine=google&api_key=$SERPAPI_API_KEY`.

`results` count is bound at tool-build via a tiny wrapper that keeps a clean introspectable signature
(`def search(query: str) -> dict`). Keys read from env inside the call (secrets, never args).

## 5. Wiring (`agent/modes/_build.py`, `competitor.py`, `client.py`, `orchestrator.py`)

- `resolve_model(cfg, ac, mode_backend, *, cloud_allowed)` — forced `vllm` + ignore `pin_gemini`
  when not cloud-allowed.
- Mode builders take `cloud_allowed` + `provider`; build `public_research` with
  `tools=[get_search_tool(provider, results=cfg.search.results)]`. (Private MCP path unchanged.)
- `orchestrator.run_async`: compute `private = private_boundary_configured()`; derive
  `eff_backend`, `cloud_ok`, `provider`; pass down; add `search={provider}` to the trace (AC-10).

## 6. Settings (`web/render.py`, `web/app.py`)

- **Governance** section: `compliance_mode` select (cloud_ok / on_prem_preferred / on_prem_required),
  `audit_log` + `block_cloud_on_private` checkboxes. POST `/settings/governance`.
- **Search** section: `provider` select, `results` number, `onprem_fallback` select, and key pills for
  `BRAVE_API_KEY` / `SERPAPI_API_KEY` (reuse `_key_set`). POST `/settings/search`.
- New-run/topbar: when on-prem is forced, show a "sovereign — no cloud" chip; disable the Gemini toggle.

## 7. File-by-file

| File | Change |
|---|---|
| `config/schema.py` | NEW `SearchConfig`; add `search` to `SentinelConfig` |
| `config/defaults.py` | seed `search` from env (first-boot) |
| `agent/governance.py` | NEW helpers (cloud_allowed, effective_backend, effective_search_provider) |
| `tools/public/web_search.py` | NEW provider registry + function tools |
| `agent/modes/_build.py` | `resolve_model` honors `cloud_allowed` |
| `agent/modes/{competitor,client}.py` | grounding tool = resolved provider |
| `agent/orchestrator.py` | derive governance, pass down, trace provider |
| `web/render.py` + `web/app.py` | Governance + Search settings sections + routes + pills |
| `web/settings.py` | `apply_governance`, `apply_search` validation helpers |
| `tests/test_governance.py` | NEW — AC-1..AC-11 |

## 8. Testing
Mock `httpx` for brave/serpapi/ddg (canned JSON → assert parsing + fail-soft). Introspect built
agents to prove no-Gemini in on_prem_required (AC-2/5). Route tests via TestClient + tmp config.
Reuse SENTINEL-002 boundary tests as the unchanged-agent-path guard (AC-11).

## 9. Rollback
Additive. Default `compliance_mode=cloud_ok` + `search.provider=gemini` reproduces today's behaviour
exactly, so the increment is a no-op until an operator changes the policy.
