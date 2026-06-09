# SENTINEL-011 — Design

**Step:** Design · **Spec:** [`spec.md`](./spec.md) · **Status:** Draft for approval

---

## 1. Architecture

Two additive seams, both reusing the SENTINEL-005 sovereignty choke-point. No change to the boundary
invariant, `recall`, the SENTINEL-004 read path, or the artifact schemas.

```
run_async(target, mode, backend)                                  (orchestrator.py — unchanged shape)
  ├─ governance.effective_backend / cloud_allowed / provider      (SENTINEL-005, unchanged)
  ├─ _build_agent(mode, ..., cloud_allowed, search_provider)
  │     ├─ if cfg.coordinator.enabled → build_coordinator(...)    NEW  (AC-8/10)
  │     │      LlmAgent(model = role(coordinator) → 12B)          ← Goal→Plan→Delegate→Merge
  │     │        tools = [AgentTool(research_pipeline),
  │     │                 AgentTool(strategy_specialist),         ← 009 (if enabled)  SENTINEL-011b
  │     │                 AgentTool(private_specialist)]          ← client mode only (AC-11)
  │     └─ else → build_competitor_agent / build_client_agent     existing SequentialAgent (AC-9)
  └─ _recompute_priority(target, mode, cfg)                       010 = deterministic post-run hook
         compute_account_priority(...) → PriorityStore().save()   ← NO LLM, NOT an AgentTool

make_agent → resolve_model(cfg, ac, mode_backend, *, cloud_allowed)
   not cloud_allowed → vllm                                       (SENTINEL-005 — no Gemini object)
   role in cfg.backend.vllm.roles → that role's BackendOption     NEW  (AC-4/6)
   else flat cfg.backend.vllm                                     (today's behaviour)
        └─ build_model("vllm", model_id, api_base)                gateway: auth by host  (AC-1)
```

> **Built-shape note (SENTINEL-011b, 2026-06-07):** this design originally drew 010 as an
> `AgentTool(priority_specialist)` alongside 009. When 010 was built it shipped **LLM-free** — one
> deterministic signal registry, pure arithmetic, reasons templated from cited data (NFR-1). A
> tool with no model cannot be an LLM-delegated `AgentTool`, and making the coordinator *narrate*
> the score would reintroduce the hallucination risk 010 was designed to remove. So 010 is wired as
> a **deterministic post-run hook** (`orchestrator._recompute_priority`, guarded by `priority.enabled`,
> fail-soft) that recomputes + persists the entity's `PriorityScore` after **every** run — shared by
> both the coordinator and SequentialAgent paths. Only the **009 strategist** is wrapped as an
> `AgentTool` specialist; its `output_key="strategy"` propagates back via AgentTool state-delta
> forwarding, so the orchestrator's existing `_merge_strategy` runs unchanged for both topologies.

**The sovereignty guarantee is unchanged and structural:** role tiering only selects *which vLLM*
`BackendOption` an agent gets; it never introduces a cloud path. `resolve_model` still returns vLLM for
every agent when `cloud_allowed=False`, so `on_prem_required` builds zero Gemini objects — provable by
introspection (AC-5), exactly as SENTINEL-005.

## 2. Gateway auth (`llm/gateway.py`)

`build_model` keeps its `(backend, model_id, api_base)` signature. Only the key resolution changes:

```python
def _vllm_api_key(api_base: str | None) -> str:
    host = urlsplit(api_base or "").hostname or ""
    if host.endswith(".atcuality.com"):
        return os.getenv("ATCUALITY_API_KEY", "not-needed")   # the two tested endpoints
    return os.getenv("VLLM_API_KEY", "not-needed")            # generic vLLM (unchanged default)
```

`LiteLlm(model=f"hosted_vllm/{model_id}", api_base=..., api_key=_vllm_api_key(api_base))`. The key is
read from env only — never an arg, never config (NFR-2). Today's `VLLM_API_KEY` path is preserved for
any non-`atcuality` endpoint, so `test_gateway` stays green; one new case covers the `.atcuality.com`
host → `ATCUALITY_API_KEY` mapping (AC-1).

## 3. Config (`config/schema.py`, `config/defaults.py`)

```python
Role = Literal["coordinator","planner","public_research","private_research",
               "extractor","synthesizer","strategist"]
# tool-callers: coordinator, planner, public_research, private_research, extractor → 12B
# reasoners:    synthesizer, strategist                                            → 26B (never tools)

class BackendConfig(BaseModel):
    ...
    vllm: BackendOption = ...                       # flat default (today; google/gemma-3-4b-it)
    roles: dict[str, BackendOption] | None = None   # NEW: per-role override, keyed by Role
# NOTE (build, 2026-06-07): `roles` sits on BackendConfig (→ cfg.backend.roles), NOT on the shared
# BackendOption — so `gemini` never carries a meaningless role map. The flat `vllm` stays the fallback.

class AgentConfig(BaseModel):
    ...
    role: Role = "synthesizer"                       # NEW; defaults.py sets the right role per key

class CoordinatorConfig(BaseModel):
    enabled: bool = False                            # ship dark
    remote_private: bool = False                     # Phase 2 (AC-14), needs a2a-sdk + ADR
    private_a2a_url: str | None = None               # Phase 2 (non-secret endpoint → config)

# SentinelConfig gains: coordinator: CoordinatorConfig = Field(default_factory=CoordinatorConfig)
```

`roles` lives under `backend.vllm` (not a parallel top-level) so the role map is clearly the on-prem
model selector and the flat `vllm` stays the fallback. `defaults.py` seeds **`roles=None`** (no
regression) and the coordinator **off**; when an admin enables tiering, the two tested endpoints are
seeded env-overridable:

```python
# only materialized when tiering is turned on (Settings) — defaults keep roles=None
"gemma-4-12B" @ GEMMA_12B_API_BASE (https://gemma.atcuality.com/v1)   # tool-callers
"gemma-4-26B" @ GEMMA_26B_API_BASE (https://omni.atcuality.com/v1)    # reasoners
```

## 4. `resolve_model` role selection (`agent/modes/_build.py`)

```python
def resolve_model(cfg, ac, mode_backend, *, cloud_allowed=True):
    if not cloud_allowed:            backend = "vllm"      # SENTINEL-005, unchanged
    elif ac.pin_gemini:              backend = "gemini"    # cloud, unchanged
    else:                            backend = resolve_backend(mode_backend or cfg.backend.default)
    if backend == "gemini":
        return build_model("gemini", ac.model or cfg.backend.gemini.model)
    opt = (cfg.backend.roles or {}).get(ac.role) or cfg.backend.vllm        # NEW: role → option
    return build_model("vllm", ac.model or opt.model, opt.api_base)
```

When `roles` is `None`/missing the role, this is identical to today (flat `vllm`), so AC-2/AC-9 hold.
A small guard enforces AC-7: a reasoner-role agent must be built with no tools (the builder raises if
`tools` is passed to a `synthesizer`/`strategist` role) — keeping the broken-tool 26B tool-free
structurally.

## 5. Coordinator (`agent/coordinator.py`, NEW)

```
build_coordinator(mode, cfg, *, backend, cloud_allowed, search_provider, memory_context) -> LlmAgent
```

- Builds the existing pipeline(s) as **specialists** by reusing the current builders (the research
  pipeline = today's `build_competitor_agent`/`build_client_agent`; the **009 strategy** specialist is
  registered via `maybe_strategist` when `strategy.enabled`). **010 priority is NOT a specialist** —
  it ships LLM-free, so it runs as a deterministic post-run hook (`_recompute_priority`), not an
  AgentTool (see the built-shape note in §1).
- Wraps each specialist with `google.adk.tools.AgentTool` (available in ADK 2.2.0 — verified) and
  hands the list to an `LlmAgent` whose model is the **coordinator role** (12B tool-caller). The
  coordinator prompt is Goal→Plan→Delegate→Merge and writes the final artifact into the mode's
  `output_key` so the orchestrator's existing extract/coerce/write path is untouched.
- **Boundary (AC-11):** competitor mode registers only PUBLIC specialists; the **private** specialist
  (the client MCP research agent) is the only holder of the MCP toolset and is registered only in
  client mode — so the coordinator cannot reach private tools in a public run, mirroring SENTINEL-002.
- Every specialist + the coordinator are built via `make_agent`/`resolve_model(cloud_allowed=)`, so
  `on_prem_required` keeps the zero-Gemini guarantee across the whole graph (AC-5).

`_build_agent` switches on `cfg.coordinator.enabled`: off → existing `SequentialAgent` (byte-identical,
AC-9); on → `build_coordinator(...)`. Fail-soft (NFR-4): a coordinator build/drive error degrades to
the Sequential path.

## 6. Remote-A2A private node — Phase 2 (spec-only this increment)

Verified state of ADK 2.2.0 in this repo: `google.adk.agents.remote_a2a_agent.RemoteA2aAgent` and
`google.adk.a2a.utils.agent_to_a2a.to_a2a` ship, but both import-fail because the standalone **`a2a`
SDK is not installed**. So remote A2A is a clean, dependency-gated phase, not this increment's code.

Design (for the Phase 2 ADR): the PRIVATE specialist is deployed **inside the customer perimeter** and
exposed as an A2A service via `to_a2a(private_agent, ...)` behind an agent card. A cloud-mode
Coordinator delegates the private-data task to a `RemoteA2aAgent(url=cfg.coordinator.private_a2a_url)`.
Raw private data never crosses back: the remote node runs the MCP toolset locally and returns only the
**boundary-tagged result** (the same `private_findings`/merged-insight shape the in-process path
returns). This elevates the SENTINEL-002 invariant from disjoint-toolsets-in-one-process to
network-level isolation. Gated by `coordinator.remote_private` + `private_a2a_url` (endpoint = config,
non-secret) and **requires an ADR + the `a2a-sdk` dependency** before any build (AC-14).

## 7. Settings (`web/render.py`, `web/app.py`, `web/settings.py`)

- **Models** section: per-role vLLM `model` + `api_base` (text inputs, written to
  `backend.vllm.roles[<role>]`), plus a set/not-set pill for `ATCUALITY_API_KEY` (reuse `_key_set`).
  POST `/settings/models`; `apply_models` validates role names + non-empty model ids; never writes a key.
- **Coordinator** section: `enabled` toggle (+ a disabled, clearly-labelled "remote private (Phase 2)"
  control). POST `/settings/coordinator`; `apply_coordinator`.
- Run trace already prints per-agent model; coordinator adds `coordinator=on` + one line per delegated
  specialist.

## 8. File-by-file

| File | Change |
|---|---|
| `llm/gateway.py` | `_vllm_api_key(api_base)`; `build_model` uses it (ATCUALITY by host, env-only) |
| `config/schema.py` | `Role`; `AgentConfig.role`; `BackendConfig.vllm.roles`; `CoordinatorConfig`; add `coordinator` |
| `config/defaults.py` | assign `role` per agent key; add `coordinator` key + prompt; seed off + `roles=None` |
| `agent/modes/_build.py` | `resolve_model` role selection; reasoner-role tool-free guard (AC-7) |
| `agent/coordinator.py` | NEW — `build_coordinator` (AgentTool-wrapped specialists, 12B coordinator); 011b adds the 009 strategist specialist (both modes) |
| `agent/orchestrator.py` | `_build_agent` switches on `coordinator.enabled`; trace delegation; 011b adds `_recompute_priority` post-run hook (010, deterministic, fail-soft) |
| `web/{render,app,settings}.py` | Models + Coordinator sections, routes, ATCUALITY pill |
| `tests/test_tiering.py` | NEW — AC-1..AC-7 (gateway auth, role map, reasoner-tool-free) |
| `tests/test_coordinator.py` | NEW — AC-8..AC-12, AC-15 (build, boundary, no-regression, trace) |

## 9. Testing

Hermetic, no live LLM/network. Mock `LiteLlm` (as `test_gateway` already does) to capture the
`api_key`/`api_base` kwargs for AC-1. Introspect built agents for the role→model map (AC-4/6), the
zero-Gemini guarantee (AC-5), and reasoner-tool-free (AC-7). Build the coordinator and assert its
`AgentTool` specialist set per mode (AC-8/11). Reuse the SENTINEL-001 default-output assertion for
byte-identical no-regression with both flags off (AC-9/15). Route tests via TestClient + tmp config;
assert no secret in YAML/HTML (AC-13). `SENTINEL_DATA_DIR=$(mktemp -d)` for any store touch.

## 10. Rollback

Fully additive. Defaults — `coordinator.enabled=False`, `backend.vllm.roles=None`, every `AgentConfig.role`
present but unused by the flat path — reproduce today's pipeline + artifact byte-for-byte, so the
increment is a no-op until an operator enables tiering or the coordinator. The gateway auth change is
backward-compatible (`VLLM_API_KEY` still used for non-`atcuality` endpoints). Remote A2A adds no code
or dependency this increment. Reverting is config-only.
