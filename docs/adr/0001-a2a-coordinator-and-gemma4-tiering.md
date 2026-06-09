# ADR 0001: A2A Multi-Agent Coordinator + Gemma-4 Model Tiering

**Status:** accepted
**Date:** 2026-06-07
**Deciders:** @don007rvs (owner, BiltIQ AI)
**Related task:** SENTINEL-011

## Context

Sentinel today runs each mode as a single ADK `SequentialAgent` (planner → research →
synthesizer) on one configured backend (`gemini-2.5-flash` cloud / `google/gemma-3-4b-it`
on vLLM). Two forces require a change:

1. **Topology.** The Google AI Agents Challenge (Track 1) and the production roadmap call for a
   coordinator/specialist (Agent-to-Agent, **A2A**) architecture — one orchestrator delegating to
   specialist agents — rather than a fixed linear pipeline. A2A is Google's own protocol, so this is
   also the strongest "Built on Google" signal available to us.
2. **Models.** A sovereign Gemma-4 inference gateway is now available (atcuality), and live testing
   (2026-06-07) found the two endpoints have **different capabilities**, which must drive role
   assignment rather than a single flat model choice.

Live verification of the gateway (recorded so the decision is reproducible):

| Endpoint (env) | Model | Chat | OpenAI tool-calling | Structured JSON |
|---|---|---|---|---|
| `GEMMA_12B_API_BASE` (`gemma.atcuality.com`) | `gemma-4-12B` | ✅ | ✅ native `tool_calls` | ✅ |
| `GEMMA_26B_API_BASE` (`omni.atcuality.com`) | `gemma-4-26B` | ✅ | ❌ emits raw `<|tool_call>` text¹ | ✅ (`json_object` + instruction) |

Both are OpenAI-compatible and authenticate with `ATCUALITY_API_KEY` (Bearer). The key is a secret
(in `.env`); the endpoints + model ids are non-secret config.

> **Update (2026-06-08): the 26B tool-calling defect was a server-config gap, now fixed.**
> ¹ The "broken tool-calling" was not a model defect — omni's vLLM was missing
> `--enable-auto-tool-choice --tool-call-parser gemma4`. The 26B emitted the correct Gemma-4
> `<|tool_call>…<tool_call|>` delimiters all along; without the parser flag they leaked into `content`.
> With both flags live (verified 2026-06-08: `get_weather({"city":"Paris"})` → `finish_reason:tool_calls`),
> **gemma-4-26B now does OpenAI tool-calling correctly.**
>
> This does **not** reverse Decision #2. We still keep the 26B **tool-free** — but the reason is now
> **latency, not capability**: the 26B decodes at ~11 tok/s vs the 12B's ~71 tok/s (7×), so the
> multi-turn research/tool loop belongs on the 12B, and the 26B is reserved for streamed reasoning
> (it also must be SSE-streamed to clear the ~100s Cloudflare 524 wall, and streaming + tool-calling is
> the fragile `lite_llm` arg-accumulation combo we deliberately avoid). The structured-JSON path was a
> *separate* fix — the gateway now sends `response_format: json_schema` (guided decoding via xgrammar);
> that is independent of the tool-call parser and must not be removed. See memory `sentinel-vllm-server-gaps`.

## Decision

1. **Adopt an A2A coordinator topology.** Add a Coordinator agent (ADK `LlmAgent` on the tool-calling
   model) that runs Goal → Plan → Delegate → Merge over **specialists** (research, synthesis,
   strategy [SENTINEL-009], prioritization [SENTINEL-010], private). Today's `SequentialAgent`
   pipelines become specialists. The Coordinator is gated by `coordinator.enabled` (default **off**),
   so the existing path stays byte-identical until enabled. (SENTINEL-011)
2. **Tier models by capability, not size.** Tool-calling roles (coordinator delegation, planner,
   public/private research, extractor) use **gemma-4-12B**; reasoning roles (synthesizer, strategist)
   use **gemma-4-26B**, which is never given tools. Gemini remains the cloud-mode option.
3. **Keep the sovereignty guarantee structural.** Every agent is still built through
   `resolve_model(cloud_allowed=)`; in `on_prem_required` no Gemini object is ever constructed —
   introspection-proven, per SENTINEL-005. A2A *strengthens* the SENTINEL-002 boundary: the private
   specialist can later be exposed as a real A2A remote running inside the customer perimeter, so raw
   private data never crosses back to a cloud coordinator.
4. **Migrate the on-prem default model** from `gemma-3-4b-it` to the Gemma-4 role map (see ADR-driven
   row in `approved-versions.md`).

## Alternatives considered

1. **Keep the single `SequentialAgent`, no coordinator** — Rejected: no delegation/specialization,
   no A2A story for the challenge, and no clean place for the 009/010 specialists to plug in.
2. **Use gemma-4-26B everywhere (bigger = better)** — Rejected: 26B's tool-calling is broken
   (emits non-parseable text), so it cannot drive MCP or web search. Capability, not size, must pick
   the model.
3. **Full remote A2A services from day one (every specialist its own deployed service)** — Rejected
   for now: heavy deploy/ops work against a 4-day deadline. We build the in-process coordinator first
   and scope **one** real A2A remote (the private specialist) as a later phase / demo spotlight.
4. **A third-party orchestration framework (LangGraph/CrewAI)** — Rejected: ADK is the challenge's
   native stack and already supports multi-agent + A2A; adding another framework is needless surface.

## Consequences

**Positive:**
- A genuine coordinator/specialist (A2A) architecture — stronger engineering and a "Built on Google"
  (ADK + A2A + Gemini/Gemma) narrative.
- Capability-correct model use: reliable tool-calling (12B) and stronger reasoning (26B), sovereign.
- The 009/010/008 increments slot in cleanly as specialists rather than bolt-ons.
- Sets up the network-level boundary story (cloud coordinator ↔ on-prem private A2A agent).

**Negative / risks:**
- New operational dependency on the atcuality Gemma-4 gateway (mitigated: fail-soft + the gateway is
  OpenAI-compatible, so it reuses the existing vLLM adapter path).
- Coordinator delegation adds reasoning hops vs a fixed pipeline (mitigated: ship dark behind a flag;
  measure before defaulting on).
- Full remote A2A (separate services) is real work deferred to a later phase.

**Tech debt accepted:**
- ~~The Gemma-4 26B endpoint's broken tool-calling is a vendor-side defect we route around (never give
  it tools) rather than fix; revisit if the gateway is corrected.~~ **Resolved 2026-06-08** — the
  gateway was corrected (`--enable-auto-tool-choice --tool-call-parser gemma4`); the 26B now tool-calls.
  We continue to keep it tool-free by **policy (latency)**, not necessity — see the Update note above.
- The in-process coordinator approximates A2A semantics until the remote-service phase lands.

## References
- SENTINEL-011 triad: `docs/specs/SENTINEL-011/{spec,design,plan}.md`
- Sovereignty seam: SENTINEL-005 (`resolve_model(cloud_allowed=)`, `agent/governance.py`)
- Boundary invariant: SENTINEL-002 (`MemoryStore.recall` choke-point)
- Specialists: SENTINEL-009 (strategy), SENTINEL-010 (prioritization), SENTINEL-008 (research depth)
- Live gateway test: this session, 2026-06-07 (table above)
