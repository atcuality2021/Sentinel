# Architecture Overview

**Repo:** Sentinel — Sovereign Intelligence Agent (BiltIQ AI / Aarna Tech Consultants Pvt. Ltd.)
**Last reviewed:** 2026-06-07 (A2A coordinator + Gemma-4 tiering — ADR-0001 / SENTINEL-011)

## What this system does (1-paragraph)

Sentinel is an autonomous research-to-action agent for regulated SMBs. A **coordinator** agent
accepts a target — a competitor or a client/account — plans the work, and delegates to **specialist**
agents that gather **public** signal through grounded web search and **private** signal through
scoped, user-authorized MCP connectors (CRM, document store, email/calendar). It reasons across both,
produces a structured **battlecard** (competitor mode) or **account brief** (client mode), then adds
an executable **strategy/action plan** and a deterministic **priority/focus list**. The defining
property is a hard separation between the public and private tool boundaries — enforced structurally
(disjoint toolsets, and, under A2A, network isolation) rather than by prompt instruction — and a
sovereignty switch that runs the whole loop on the customer's own GPUs with **zero cloud egress**,
provably.

## Components

- **Coordinator (ADK `LlmAgent`, tool-calling model)** — Goal → Plan → Delegate → Merge. Routes work
  to specialists via `google.adk.tools.AgentTool`. Gated by `coordinator.enabled` (default off);
  when off, the legacy per-mode `SequentialAgent` runs unchanged. *(SENTINEL-011)*
- **Specialists** — each a focused agent/pipeline:
  - *Research* (planner + public web search; tool-caller) → findings.
  - *Private* (scoped MCP connectors; tool-caller) → private findings. Client mode only; the only
    holder of the private toolset — the structural boundary.
  - *Synthesis* (reasoner, no tools) → schema-valid Battlecard / AccountBrief.
  - *Strategy* (reasoner, playbook overlay) → assessment + action plan + objection handling. *(009)*
  - *Prioritization* (deterministic, no LLM) → weighted-signal score + focus list. *(010)*
- **Model gateway (`llm/gateway.py`)** — `build_model`/`resolve_model` resolve a model **by role**:
  tool-calling roles → gemma-4-12B, reasoning roles → gemma-4-26B, or Gemini in cloud mode. One seam,
  so the backend swaps with no orchestration change.
- **Governance brain (`agent/governance.py`)** — `cloud_allowed` / `effective_backend` /
  `effective_search_provider`. `on_prem_required` ⇒ no Gemini object is ever constructed. *(005)*
- **Memory harness (`memory/`)** — shared, boundary-tagged SQLite store: working state (ADK session),
  episodic (`RunStore`), semantic (`MemoryStore` entity facts, SM-2 reinforced), procedural (009
  playbooks). `MemoryStore.recall(allowed_boundaries)` is the single boundary choke-point. *(002)*
- **Artifact writer (`artifacts/writer.py`)** — validates against the mode schema, writes the durable
  artifact (Markdown today; workspace via MCP later).
- **Dashboard (`web/`)** — FastAPI server-rendered UI: run form, reports, accounts, settings (one
  center for all non-secret config), and the focus list.

## Data flow

```
[user: target + mode]
      │
      ▼
[COORDINATOR]  Goal → Plan ───────────────► delegate (AgentTool / A2A)
      │                                          │
      ├──► RESEARCH specialist ──► PUBLIC boundary  (grounded search; gemma-4-12B | Gemini)
      │                                          │
      ├──► PRIVATE specialist ──► PRIVATE boundary (scoped MCP; gemma-4-12B)
      │            (under remote A2A: runs ON-PREM; raw private data never returns)
      ▼
[SYNTHESIS specialist]  merge public ⊕ private ──► Battlecard | AccountBrief   (gemma-4-26B | Gemini)
      │
      ├──► [STRATEGY specialist]  playbook overlay ──► assessment + action plan + objections  (009)
      ├──► [PRIORITIZATION]       deterministic registry ──► score + focus list (no LLM)        (010)
      ▼
[schema validation] → [artifact writer] → artifact + persist (RunStore / MemoryStore)
```

Every model is resolved through `resolve_model(cloud_allowed=)`; in `on_prem_required` the entire
graph runs on Gemma/vLLM with no Gemini object built (introspection-proven).

## Deployment topology

- **Demo / challenge:** containerized agent on **Google Cloud Run**; reasoning + grounded search via
  **Vertex AI / Gemini**; coordinator + specialists in one process (AgentTool). MCP to demo sources.
- **Production (regulated):** same container, models repointed to the **Gemma-4 sovereign gateway**
  (12B tool-caller `gemma.atcuality.com`, 26B reasoner `omni.atcuality.com`) on customer-controlled
  GPUs. No public-cloud dependency in any path. **Phase 2 (A2A remote):** the private specialist is
  deployed as a separate A2A service *inside the customer perimeter*; a cloud coordinator delegates to
  it over A2A and only the boundary-tagged result crosses back — network-level enforcement of the
  SENTINEL-002 invariant. *(requires the `a2a-sdk` dependency — ADR-0001.)*

## Dependencies

External:
- Gemma-4 sovereign gateway (atcuality; OpenAI-compatible) — 12B (tools) + 26B (reasoning)
- Google Gemini / Vertex AI — cloud-mode reasoning + grounded search
- Google Cloud Run — runtime (demo)
- Google ADK 2.2.0 (`google-adk[extensions]`) — orchestration + multi-agent (`AgentTool`); A2A
  (`RemoteA2aAgent`/`to_a2a`) pending the `a2a-sdk` add
- MCP connectors — CRM / document store / email-calendar (user-authorized)
- Pluggable public search — Gemini `google_search` | DuckDuckGo | Brave | SerpAPI (005)

Internal:
- Model gateway (`llm/gateway.py`) — role→model resolution, Gemini ↔ Gemma swap
- Governance (`agent/governance.py`) — the sovereignty routing brain
- Memory harness (`memory/`) — shared boundary-aware store

Depends on this repo: none yet (standalone agent).

## Failure modes

| Dependency | Failure | Behavior |
|---|---|---|
| Gemma gateway / Gemini | timeout / 5xx | Retry + fail-soft; degrade to a gap-recorded artifact, never crash the run. |
| Coordinator delegation | a specialist errors | Coordinator records the gap and merges what succeeded; a failed strategy/priority step degrades to the base artifact (deterministic-first). |
| MCP private connector | unauthorized / unreachable | Skip the source, record the gap ("CRM not connected"); public-only output still produced. |
| Model resolution | backend unavailable | Hard error — no silent fallback to a non-approved backend (compliance boundary). |
| Artifact write target | write fails | Persist locally / return inline; never lose synthesized work. |

## Where new code goes

- New specialist / mode → `src/sentinel/agent/modes/...` (+ register with the coordinator)
- Coordinator / delegation logic → `src/sentinel/agent/coordinator.py` (SENTINEL-011)
- Orchestrator entry loop → `src/sentinel/agent/orchestrator.py`
- Model adapters / role resolution → `src/sentinel/llm/gateway.py`
- A new MCP tool/connector → `src/sentinel/tools/{public,private}/...` (correct boundary)
- Artifact schemas → `src/sentinel/artifacts/schemas.py`
- Priority signals → `src/sentinel/priority/...` (SENTINEL-010)
- Strategy playbooks → `playbooks/*.md` (SENTINEL-009, runtime-loaded)
- A shared utility → `src/sentinel/lib/...` (and add to `stack.md`)

## Audit cadence

Reviewed at each milestone. Material changes (new component, new boundary, new model/dependency,
deploy-topology change) require a same-PR update and, for a new AI dependency, an ADR.
