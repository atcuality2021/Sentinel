# SENTINEL-011 — A2A Coordinator & Gemma-4 Model Tiering

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** SENTINEL-001 (`make_agent`/config), 002 (boundary invariant, `MemoryStore`/`RunStore`),
005 (`resolve_model(cloud_allowed=)` governance seam, gateway `build_model`), 008/009/010 (the
specialists the coordinator delegates to: research, strategy, priority, private)
**Blocks:** the demo "one agent that plans, delegates, and merges — sovereign" narrative
**Source:** SENTINEL-005 sovereignty seam · tested-live Gemma-4 endpoints (this session)

---

## 1. Context / problem

Two gaps block the next step.

**(a) One flat on-prem model.** Today `BackendConfig.vllm` is a *single* `BackendOption` —
every on-prem agent (planner, researcher, extractor, synthesizer, strategist) runs the same
`google/gemma-3-4b-it`. But we now have two purpose-built endpoints, verified live this session:
`gemma-4-12B` does **clean native OpenAI tool-calling** (the tool-caller), and `gemma-4-26B` does
**chat + structured JSON but its native tool-calling is broken** (emits raw `<|tool_call>` text, never
a `tool_calls` array — the reasoner; never give it tools). The flat model means a tool-using agent and
a tool-free reasoner are forced onto the same weights — wrong tool for each job, and the broken-tool
risk if the 26B ever gets a toolset. We need model selection by **role**, flowing through the same
`resolve_model` seam so `on_prem_required` still builds **zero** Gemini objects (SENTINEL-005 intact).

**(b) Fixed Sequential pipelines.** Both modes are hardwired `SequentialAgent` chains. There is no
agent that reasons about *which* specialists to invoke for a target, runs them, and merges the results
— and no path to push the **private** specialist out of the host process onto a customer-controlled
node. We add an A2A **Coordinator** (Goal→Plan→Delegate→Merge over the existing pipelines as
specialists) and specify the remote-A2A private node as a scoped later phase.

> **Not a solution restatement:** the ask is not "swap the model string" and not "add another agent."
> It is "pick the right Gemma for each role through the existing sovereignty seam, and put a
> coordinator over the existing pipelines — both shipping dark so the 145-test baseline stays
> byte-identical until an operator opts in."

## 2. Goal / non-goals

**Goal:**
1. **Model role tiering.** Extend `BackendConfig` so on-prem agents resolve a model by **role**
   (tool-caller `gemma-4-12B` vs reasoner `gemma-4-26B`), via `resolve_model`. Default config keeps
   today's single-model behaviour; tiering is opt-in.
2. **Gateway auth for the ATCUALITY endpoints.** `build_model("vllm", ...)` must send the
   `ATCUALITY_API_KEY` (env-only secret) as the Bearer key for the `*.atcuality.com` endpoints, with
   `VLLM_API_KEY` still honored for a generic vLLM. Endpoints are non-secret → config.
3. **In-process A2A Coordinator** (ADK `LlmAgent` on the 12B tool-caller) that runs
   Goal→Plan→Delegate→Merge over the existing pipelines wrapped as **specialists**, behind
   `coordinator.enabled` (default `False`).
4. **Remote-A2A private node — specified, scoped to a later phase.** Define how the PRIVATE specialist
   is exposed as a real A2A service inside the customer perimeter so only the boundary-tagged result
   crosses back. In-process is the must-have; remote ships behind its own flag + the `a2a-sdk`
   dependency.
5. **Sovereignty + boundary.** Every new agent built via `resolve_model(cloud_allowed=)`;
   `on_prem_required` ⇒ zero Gemini (introspection-proven). The SENTINEL-002 boundary invariant is
   inviolable and is *strengthened* by A2A isolation.
6. **Ship dark.** `coordinator.enabled=False` + tiering opt-in ⇒ pipeline + every artifact
   byte-identical to today; full existing suite green.

**Non-goals:** parallel specialist fan-out (coordinator delegates sequentially this increment);
running the full remote-A2A node end-to-end (Phase 2, separate dependency + ADR); a coordinator-config
UI beyond a Settings toggle; new artifact schemas (011 changes orchestration, not artifact shape);
multi-host service mesh / discovery (single declared private-node URL).

## 3. Personas

P1 **Analyst** — one run that plans which specialists to use and merges them; sees the delegation in
the trace. P2 **Admin** — picks the Gemma role map + toggles the coordinator in Settings. P3
**Compliance** — `on_prem_required` proves zero Gemini; remote-A2A keeps raw private data on-prem,
only the tagged result returns.

## 4. Acceptance criteria (testable, binary)

- [ ] **AC-1** `build_model("vllm", model_id, api_base)` sends an auth key resolved as: `ATCUALITY_API_KEY`
  when `api_base` host ends in `.atcuality.com`, else `VLLM_API_KEY`, else `"not-needed"`. The key is
  read from env only; it never appears in config/YAML/args (proven by capturing the LiteLlm kwargs).
- [ ] **AC-2** `BackendOption` gains an optional per-role override; `BackendConfig.vllm` gains an
  optional `roles: dict[Role, BackendOption]`. With `roles` unset, every agent resolves the flat
  `vllm` model exactly as today (round-trips through YAML).
- [ ] **AC-3** A `Role` is assigned to each agent (`AgentConfig.role`): tool-calling roles
  (`coordinator`, `planner`, `public_research`, `private_research`, `extractor`) default to the
  tool-caller; reasoning roles (`synthesizer`, `strategist`) default to the reasoner.
- [ ] **AC-4** `resolve_model(cfg, ac, mode_backend, *, cloud_allowed)` picks the role's vLLM
  `BackendOption` when `cfg.backend.vllm.roles` has the agent's role; else the flat `vllm` option.
  The cloud path (`pin_gemini`, `cloud_allowed=True`) is unchanged.
- [ ] **AC-5** In `on_prem_required`, **every** agent (including the coordinator) resolves a vLLM
  object — no Gemini object is constructed — regardless of `pin_gemini` (SENTINEL-005 guarantee,
  introspection-proven per this increment).
- [ ] **AC-6** With tiering enabled and a role map set, the reasoner roles resolve to `gemma-4-26B`
  and the tool-caller roles to `gemma-4-12B` — asserted by introspecting each built agent's model id.
- [ ] **AC-7** The reasoner role (`gemma-4-26B`) is **never** built with a non-empty `tools` list:
  an assertion in the builder (or a structural test) proves no tool is attached to a reasoner-role
  agent.
- [ ] **AC-8** A `Coordinator` builder produces an ADK `LlmAgent` (model = tool-caller role) whose
  delegatable specialists are the existing pipelines wrapped via ADK `AgentTool` (and/or `sub_agents`),
  one per available specialist (research, strategy[009], priority[010], private).
- [ ] **AC-9** With `coordinator.enabled=False` (default), `_build_agent` returns the existing
  `SequentialAgent` unchanged and the artifact is **byte-identical** to today (reuse the SENTINEL-001
  no-regression assertion).
- [ ] **AC-10** With `coordinator.enabled=True`, `_build_agent` returns the `Coordinator`; the
  orchestrator drives it to completion and still produces a schema-valid artifact into the mode's
  output key; the trace records `coordinator=on` + each delegated specialist.
- [ ] **AC-11** **Boundary invariant holds under the coordinator:** in competitor mode the coordinator
  can only reach PUBLIC specialists (no private specialist is registered); in client mode the private
  specialist owns the MCP toolset and the public path has no MCP tool — proven structurally, mirroring
  SENTINEL-002.
- [ ] **AC-12** A `coordinator` agent key + prompt exist in defaults (Goal→Plan→Delegate→Merge), with
  `role="coordinator"`, `pin_gemini=False`; defaults seed the coordinator **off** and the role map
  **unset** (no-regression).
- [ ] **AC-13** Settings exposes a **Models** section (per-role vLLM model + api_base; key shown as a
  set/not-set pill for `ATCUALITY_API_KEY`) and a **Coordinator** toggle; saving persists to YAML, no
  secret written.
- [ ] **AC-14** *(Phase 2, spec-only this increment)* A `RemoteA2aAgent`-backed private specialist and
  a `to_a2a`-exposed private service are designed; gated behind `coordinator.remote_private` + the
  `a2a-sdk` dependency; an ADR is required before build. No remote network call is added this increment.
- [ ] **AC-15** All existing tests pass; SENTINEL-002 boundary + 003/004 surfaces unchanged; tiering
  off + coordinator off is the default and a no-op against the 145-test baseline.

## 5. Functional requirements

- **FR-1** `llm/gateway.py`: `build_model` resolves the auth key by endpoint host
  (`*.atcuality.com` → `ATCUALITY_API_KEY`, else `VLLM_API_KEY`, else `"not-needed"`); a small
  `_vllm_api_key(api_base)` helper, env-only. No new config field for the key.
- **FR-2** `config/schema.py`: a `Role` literal; `AgentConfig.role: Role`; `BackendConfig.vllm` gains
  `roles: dict[str, BackendOption] | None = None`; `CoordinatorConfig{enabled=False, remote_private=False,
  private_a2a_url=None}`; add `coordinator` to `SentinelConfig`.
- **FR-3** `agent/modes/_build.py`: `resolve_model` selects the role's vLLM `BackendOption` (fallback
  to flat `vllm`); reasoner-role agents are asserted tool-free (AC-7).
- **FR-4** `agent/coordinator.py` (NEW): `build_coordinator(mode, cfg, *, backend, cloud_allowed,
  search_provider, memory_context)` → an `LlmAgent` whose specialists are the existing pipelines wrapped
  with `AgentTool`; one specialist per available capability for the mode.
- **FR-5** `agent/orchestrator._build_agent`: when `cfg.coordinator.enabled`, return
  `build_coordinator(...)`; else the existing `SequentialAgent` (unchanged). Trace the delegation.
- **FR-6** `config/defaults.py`: assign a `role` to every existing agent key; add the `coordinator`
  agent key + Goal→Plan→Delegate→Merge prompt; seed coordinator off + role map unset.
- **FR-7** `web/settings.py`/`app.py`/`render.py`: **Models** section (per-role model/api_base, ATCUALITY
  key pill) + **Coordinator** toggle; POST `/settings/models`, `/settings/coordinator`.

## 6. Non-functional

- **NFR-1** Sovereignty structural: every new agent (coordinator included) built via
  `resolve_model(cloud_allowed=)`; `on_prem_required` ⇒ no Gemini object — introspection-proven (AC-5).
- **NFR-2** Secrets env-only: `ATCUALITY_API_KEY` never in config/YAML/HTML/args; endpoints are config.
- **NFR-3** No-regression: tiering off + coordinator off ⇒ byte-identical pipeline + artifact
  (AC-9/AC-15). Each step lands green and ships dark independently (4-day deadline).
- **NFR-4** Deterministic-first/fail-soft: a coordinator/delegation failure degrades to the legacy
  Sequential pipeline or a gap-rich artifact — never breaks a run.
- **NFR-5** The reasoner (`gemma-4-26B`) is never given tools (AC-7) — broken native tool-calling is
  contained structurally, not by prompt.
- **NFR-6** Typed contracts; no `Any`, no unjustified `# type: ignore`; pydantic structured output
  (no free-text-JSON repair); tests hermetic (`SENTINEL_DATA_DIR=$(mktemp -d)`, no live LLM/network —
  mock/introspect).

## 7. Risks

- **R-1 Sovereignty regression** — the coordinator or a role override sneaks in a Gemini object.
  *Mitigation:* coordinator + every specialist built through the SENTINEL-005 seam; AC-5 introspection
  test. The role map only ever names vLLM `BackendOption`s; cloud stays governed by `pin_gemini`.
- **R-2 Reasoner gets a toolset** — `gemma-4-26B` would emit raw `<|tool_call>` garbage. *Mitigation:*
  AC-7 structural assertion; reasoner roles are the tool-free synthesizer/strategist only.
- **R-3 No-regression drift** — adding the coordinator/role plumbing changes the default graph.
  *Mitigation:* default config (coordinator off, role map unset) returns the exact existing
  `SequentialAgent`; AC-9/AC-15 assert byte-identical output. Land each step dark.
- **R-4 ADK 2.2.0 multi-agent semantics** — `AgentTool`/`sub_agents` transfer behaviour with a Gemma
  tool-caller. *Mitigation:* coordinator uses the 12B (proven clean tool-calling); fail-soft to the
  Sequential path (NFR-4); keep the coordinator prompt explicit about merge into the output key.
- **R-5 Remote A2A is heavier than it looks** — `RemoteA2aAgent`/`to_a2a` require the `a2a-sdk`
  package, **not installed** in the current venv (verified: `google.adk.a2a.*` ships but its `a2a`
  dependency is absent). *Mitigation:* Phase 2, behind `coordinator.remote_private` + an ADR; this
  increment is spec-only for remote (AC-14), so no dependency churn near the deadline.
- **R-6 Secret leak** — the ATCUALITY key in config/logs. *Mitigation:* env-only resolution by host
  (AC-1); Settings shows a pill, never the value (AC-13).

## 8. Open questions

- **OQ-1** Coordinator wrapping: ADK `AgentTool` (specialist-as-tool) vs `sub_agents` transfer?
  *Proposed:* `AgentTool` for the in-process default (deterministic, the 12B calls each as a tool and
  merges); `sub_agents` transfer is a fast-follow if delegation needs to hand off control. (Both
  available in ADK 2.2.0; `RemoteA2aAgent` is not, pending `a2a-sdk`.)
- **OQ-2** Role map default values when tiering is *enabled* — ship `gemma-4-12B`/`gemma-4-26B` at the
  `.atcuality.com` endpoints as the seeded roles, or require the admin to fill them? *Proposed:* seed
  the two known endpoints (env-overridable, file-authoritative thereafter); flat `vllm` stays the
  default until `roles` is set.
- **OQ-3** Remote-private node deployment shape (sidecar vs standalone service inside the perimeter) —
  defer to the Phase 2 ADR (AC-14).
