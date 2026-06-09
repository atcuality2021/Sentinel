# SENTINEL-011 — Plan

**Step:** Plan · **Design:** [`design.md`](./design.md) · **Status:** Draft for approval

Atomic, ordered; each ends green and ships dark. No live LLM/network in any test (LiteLlm mocked,
agents introspected). Test IDs → spec ACs. Default config stays byte-identical until an operator opts
in, so every step is independently shippable inside the 4-day window.

---

### Step 1 — Gateway auth by endpoint host
`llm/gateway.py`: add `_vllm_api_key(api_base)` (`*.atcuality.com` → `ATCUALITY_API_KEY`, else
`VLLM_API_KEY`, else `"not-needed"`); `build_model` uses it. Signature unchanged.
**Test (AC-1):** mock LiteLlm, capture kwargs; `https://gemma.atcuality.com/v1` → `ATCUALITY_API_KEY`;
a generic `http://localhost:8000/v1` → `VLLM_API_KEY`; key never in args/config. Existing `test_gateway`
stays green.

### Step 2 — `Role` + role map in schema/defaults
`config/schema.py`: `Role` literal; `AgentConfig.role`; `BackendConfig.vllm.roles:dict[str,BackendOption]|None=None`.
`config/defaults.py`: set the correct `role` on each existing agent key (tool-callers vs reasoners);
`roles` stays `None`.
**Test (AC-2/3):** default cfg has `roles is None` + each agent's `role` correct; round-trips through YAML;
flat-vllm behaviour unchanged.

### Step 3 — `resolve_model` role selection + reasoner-tool-free guard
`agent/modes/_build.py`: pick `cfg.backend.vllm.roles[ac.role]` when present, else flat `vllm`; raise
if a `synthesizer`/`strategist` role is built with a non-empty `tools` list.
**Test (AC-4/5/6/7):** role map set → reasoner roles resolve `gemma-4-26B`, tool-callers `gemma-4-12B`
(introspect model id); `on_prem_required` → every agent vLLM, no Gemini object; reasoner + tools → raises.

### Step 4 — `CoordinatorConfig` + coordinator agent key/prompt
`config/schema.py`: `CoordinatorConfig{enabled=False, remote_private=False, private_a2a_url=None}`; add
`coordinator` to `SentinelConfig`. `config/defaults.py`: add a `coordinator` agent key
(`role="coordinator"`, `pin_gemini=False`) + a Goal→Plan→Delegate→Merge prompt; seed coordinator off.
**Test (AC-12):** default cfg has `coordinator.enabled is False`; the `coordinator` agent/prompt exist;
no-op vs baseline.

### Step 5 — `build_coordinator` (in-process, AgentTool-wrapped specialists)
`agent/coordinator.py` (NEW): build the existing pipeline(s) as specialists, wrap with `AgentTool`,
hand to an `LlmAgent` on the coordinator role (12B); register the private specialist only in client
mode; build every agent via `resolve_model(cloud_allowed=)`.
**Test (AC-8/11):** competitor coordinator registers only PUBLIC specialists (no MCP); client
coordinator's private specialist holds the MCP toolset and the public path has none;
`on_prem_required` → coordinator + specialists all vLLM (no Gemini).

### Step 6 — Wire coordinator into the orchestrator (dark by default)
`agent/orchestrator._build_agent`: `if cfg.coordinator.enabled → build_coordinator(...)` else the
existing `SequentialAgent`; trace `coordinator=on` + delegated specialists; fail-soft to Sequential.
**Test (AC-9/10):** coordinator off → `_build_agent` returns the existing SequentialAgent and the
artifact is byte-identical (reuse the SENTINEL-001 default-output assertion); coordinator on → returns
the LlmAgent and a schema-valid artifact lands in the output key; trace shows the delegation.

### Step 7 — Settings: Models + Coordinator sections
`web/settings.py` `apply_models` / `apply_coordinator` (validate role names, non-empty model ids).
`render.py` sections + ATCUALITY pill (reuse `_key_set`). `app.py` routes `/settings/models`,
`/settings/coordinator`. The "remote private (Phase 2)" control rendered disabled.
**Test (AC-13):** POST models/coordinator persists to YAML; no secret in YAML/HTML; ATCUALITY pill
reflects env; bad role → err banner.

### Step 8 — Housekeeping + no-regression + Phase-2 ADR stub
Docstrings; update MEMORY.md, specs/README.md, `.remember`. Write the Phase-2 remote-A2A ADR stub
(needs `a2a-sdk` + the `RemoteA2aAgent`/`to_a2a` design from design.md §6) so AC-14 is recorded, not built.
**Test (AC-15):** full `pytest -q` green; SENTINEL-002 boundary + 003/004 + 008/009/010 surfaces
untouched; tiering off + coordinator off is the default no-op against the 145-test baseline.

---

## Definition of done
- AC-1..AC-13 + AC-15 green. An admin can set a per-role Gemma model map (12B tool-callers, 26B
  reasoner) and toggle the coordinator in Settings; `on_prem_required` provably builds **zero** Gemini
  objects across the coordinator and every specialist; the reasoner is never given tools; defaults are
  byte-identical to today. The ATCUALITY key is env-only, shown as a pill. AC-14 (remote A2A) is
  designed + ADR-stubbed for a dependency-gated Phase 2 — no remote code or network this increment.

## Estimate
~8 steps. Heaviest: `build_coordinator` (Step 5) + the orchestrator wiring (Step 6). Steps 1-4 are the
sovereign-tiering foundation and ship dark immediately. Remote A2A is explicitly out of this
increment's build (spec + ADR only), keeping the diff small near the deadline.
