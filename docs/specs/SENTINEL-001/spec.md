# SENTINEL-001 — Configurable Agent Runtime

**Step:** Spec · **Status:** Draft for approval · **Author:** 2026-06-07
**Depends on:** none · **Blocks:** SENTINEL-002, 003, 005, 006

---

## 1. Context / problem

Today the agent's behaviour is **hardcoded**:

- Model ids live inside `gateway.py` and the mode builders (`competitor.py`, `client.py`).
- Each agent's instruction (prompt) is a string literal inside the builder functions.
- There is **no generation control** — temperature, max output tokens, top_p/top_k are never
  set, so we get library defaults (non-deterministic, uncapped length, uncontrolled cost).
- Backend selection is via scattered env vars.

For a real pilot, an admin must tune the agent **without editing code or redeploying**: choose a
model per step, edit prompts, cap tokens, set temperature. None of that is possible until the
configuration is **externalized into a single object the agent reads at runtime**. This task
builds that backbone. It ships **no UI** (that is SENTINEL-003) — but it exposes the config API
the UI and the memory harness will build on.

## 2. Goal / non-goals

**Goal:** A single, persisted `SentinelConfig` is the source of truth for backends, per-agent
model, per-agent prompt, and generation parameters. The orchestrator builds every agent from it.
Defaults reproduce today's behaviour exactly (no regression) while making all of it editable.

**Non-goals (explicit, to prevent scope creep):**
- No Settings UI (SENTINEL-003).
- No memory/persistence of runs (SENTINEL-002).
- No prompt *versioning* beyond keeping the shipped default for "reset" (versioning → 003).
- No auth / multi-tenant.

## 3. Personas served

P2 Admin (configures), P1 Analyst (benefits from tuned output), P3 Compliance (token caps,
backend governance hooks land here for 005).

## 4. User stories

- **US-3.1** Admin picks a model per agent (planner=flash, synthesizer=pro) — *config field exists
  and is honoured at build time.*
- **US-3.2** Admin sets the default backend and it is overridable per run — *already partly done;
  this task moves the default into config.*
- **US-5.1 (backend half)** Admin can change an agent's prompt — *prompt is read from config, not
  a literal; "reset to default" is possible because the shipped default is retained.*
- **US-6.1** Admin sets temperature, max_output_tokens, top_p, top_k globally and per agent —
  *passed to the model via `generate_content_config`; per-agent overrides win.*

## 5. Acceptance criteria (testable, binary)

- [ ] **AC-1** `SentinelConfig.default()` produces a config whose model ids and prompts equal the
  current hardcoded values (golden test: built agents have identical `instruction` and model).
- [ ] **AC-2** Saving a config to YAML and loading it round-trips to an equal object.
- [ ] **AC-3** If the config file is absent, the runtime loads defaults and writes the file once
  (self-seeding); if present, it is used.
- [ ] **AC-4** `build_competitor_agent(config)` / `build_client_agent(config)` set each sub-agent's
  model from `config.agents[name].model` (falling back to the backend default).
- [ ] **AC-5** Each sub-agent receives a `generate_content_config` with the resolved temperature,
  max_output_tokens, top_p, top_k (per-agent override beats global).
- [ ] **AC-6** Each sub-agent's `instruction` is rendered from `config.prompts[name].template`, and
  a prompt missing a required variable (e.g. `{target}`) fails validation with a clear error.
- [ ] **AC-7** `public_research` model stays Gemini regardless of backend (grounding is native) —
  enforced and tested (extends existing boundary guarantee).
- [ ] **AC-8** The synthesizer (which uses `output_schema`) still works; generation config is
  applied in a way compatible with structured output (temperature set, no tool calls).
- [ ] **AC-9** Per-run backend override (existing UI/CLI toggle) still wins over the config default.
- [ ] **AC-10** All existing tests pass; new tests cover AC-1..AC-9.

## 6. Functional requirements

- **FR-1** Provide `sentinel.config` with: `GenerationConfig`, `BackendConfig`, `AgentConfig`,
  `PromptTemplate`, `MemoryConfig` (stub for 002), `GovernanceConfig` (stub for 005), `SentinelConfig`.
- **FR-2** `load_config(path) -> SentinelConfig` and `save_config(cfg, path)`; YAML on disk.
- **FR-3** A process-level accessor `get_config()` (cached) and `set_config()` for tests/UI.
- **FR-4** Prompt templates declare `variables: list[str]`; rendering validates all are supplied
  and that the template references no unknown `{var}`.
- **FR-5** Generation resolution: effective = global generation merged with per-agent override.
- **FR-6** Model resolution: per-agent `model` if set, else the active backend's default model;
  `public_research` is pinned to the Gemini default model.
- **FR-7** Mode builders accept an optional `config` (default `get_config()`) and an optional
  per-run `backend` (existing behaviour preserved).
- **FR-8** Config file path resolves from `SENTINEL_CONFIG_PATH` env, else `./sentinel.config.yaml`.

## 7. Non-functional requirements

- **NFR-1** No regression: default config reproduces current outputs (golden tests).
- **NFR-2** Backend-agnostic: generation config applies to both Gemini and Gemma/vLLM paths
  (where the model honours it); document any LiteLlm limitation rather than silently dropping it.
- **NFR-3** Safe: config file holds **no secrets** (API keys stay in env / secret store).
- **NFR-4** Typed: no `Any`; pydantic validation on load with actionable errors.

## 8. Out of scope

Settings UI, run persistence, memory, prompt versioning/rollback, audit log, connectors OAuth,
auth. All tracked as later increments in `docs/specs/README.md`.

## 9. Dependencies

- `pydantic` (present), `pyyaml` (present, v6), `google-genai` `types.GenerateContentConfig`
  (present), ADK `Agent.generate_content_config` field (present).

## 10. Risks

- **R-1** LiteLlm (vLLM path) may not map every `generate_content_config` field. *Mitigation:* set
  the fields ADK/LiteLlm support (temperature, max_output_tokens, top_p); verify on the live vLLM
  smoke test; document gaps. Don't block the Gemini path on this.
- **R-2** `output_schema` + generation config interaction on the synthesizer. *Mitigation:* test
  that structured output still validates; keep synthesizer temperature modest.
- **R-3** Prompt edits could break `{state_key}` injection ADK relies on. *Mitigation:* variable
  validation (FR-4) + keep ADK's `{var}` syntax; document reserved variables per agent.

## 11. Open questions

- **OQ-1** Env-var precedence after migration: should existing env vars (`SENTINEL_GEMINI_MODEL`,
  `VLLM_MODEL`, `SENTINEL_LLM_BACKEND`) seed the *initial* config then defer to the file, or keep
  overriding it? *Proposed:* env seeds defaults on first run; file is source of truth thereafter;
  `SENTINEL_LLM_BACKEND` per-process still allowed as an override for ops. Confirm.
