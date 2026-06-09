# ADR-0002 — Remote A2A private node (Phase 2)

**Status:** Proposed (stub — not yet built) · **Date:** 2026-06-07 · **Deciders:** @don007rvs
**Depends on:** [ADR-0001](./0001-a2a-coordinator-and-gemma4-tiering.md) (A2A coordinator + Gemma-4 tiering)
**Tracks:** SENTINEL-011 AC-14

## Context

SENTINEL-011 shipped the **in-process** A2A coordinator: a cloud/edge `LlmAgent` (12B) delegates to
specialist agents wrapped as `AgentTool`s, with the private/MCP toolset structurally isolated to a
single `private_research` specialist (the SENTINEL-002 boundary). All specialists run in the same
process as the coordinator.

The sovereign end-state goes one step further: run the **private specialist as a separate service
inside the customer's perimeter**, so a coordinator running anywhere delegates the private-data task
over the network and **raw private data never crosses back** — only the boundary-tagged result
(`private_findings` / merged insight) returns. This upgrades the boundary from
disjoint-toolsets-in-one-process to **network-level isolation**. No incumbent CI/account-intel
product has this.

## Decision (deferred — this ADR records the design, not a build)

Adopt remote A2A as a **dependency-gated Phase 2**, gated by `coordinator.remote_private` +
`coordinator.private_a2a_url` (both already present in `CoordinatorConfig`, defaulting off/None).

Verified state of ADK 2.2.0 in this repo (2026-06-07):
`google.adk.agents.remote_a2a_agent.RemoteA2aAgent` and `google.adk.a2a.utils.agent_to_a2a.to_a2a`
**ship** but import-fail because the standalone **`a2a` SDK is not installed**. So this is a clean
dependency add, not a refactor.

Planned shape:
- On-prem: expose the `private_research` specialist as an A2A service via `to_a2a(private_agent, ...)`
  behind an agent card. It runs the MCP toolset locally, inside the perimeter.
- Coordinator side: when `remote_private` is on, register a
  `RemoteA2aAgent(url=cfg.coordinator.private_a2a_url)` in place of the in-process private specialist.
- Contract: the remote node returns the **same boundary-tagged `private_findings` shape** the
  in-process path returns — the coordinator merge path and artifact schema are unchanged.

## Consequences

- **Requires** adding `a2a-sdk` to dependencies (its own line in `pyproject`/`requirements`) and a
  follow-up ADR flipping this one to **Accepted** before any code lands.
- Sovereignty strengthened to network-level; the cloud coordinator never sees raw private data.
- New operational surface: the on-prem A2A endpoint (auth, TLS, agent-card discovery) — to be
  specified in the Phase-2 build.
- Until then, `remote_private` stays non-togglable from the Settings UI (rendered disabled) and
  `apply_coordinator` never enables it (AC-14 is recorded, not buildable).

## Alternatives considered

- **Build remote A2A now** — rejected: the `a2a-sdk` dependency + endpoint hardening can't be done
  and validated inside the 4-day window, and the in-process boundary already satisfies the demo.
- **Tunnel MCP to the cloud coordinator instead** — rejected: that pulls private data across the
  boundary, defeating the entire sovereignty thesis.
