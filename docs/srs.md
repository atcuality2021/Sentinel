# System Requirements Specification — Sentinel (Sovereign Intelligence Agent)

**Version:** 0.1 (draft)
**Last updated:** 2026-06-07
**Status:** Draft — for challenge build (Track 1: Build)
**Source business analysis:** `docs/business-analysis.md`
**Scope note:** Requirements are scoped to the Google for Startups AI Agents Challenge PoC (due 2026-06-11). Production-only items are marked `Won't (this release)`.

---

## Stakeholders

| # | Name/Role | Type | Influence | Primary concern |
|---|---|---|---|---|
| 1 | Sales / strategy analyst (end user) | End user | H | Fast, trustworthy battlecard / brief |
| 2 | Account executive | End user | H | Merged public + private context per account |
| 3 | CISO / compliance officer | Security / Compliance | H | No private-data egress; provable boundaries |
| 4 | BiltIQ AI (vendor / sponsor) | Sponsor | H | Cloud-demo → on-prem-prod portability thesis |
| 5 | Operations (deploy/monitor) | Operations | M | Cloud Run deploy, traces, graceful degradation |
| 6 | Challenge judges | External evaluator | H | ADK + MCP + business impact + demo |

---

## Functional Requirements

| ID | Priority | Requirement | Source | Acceptance criteria |
|---|---|---|---|---|
| FR-01 | Must | The system shall accept a research target (a competitor or a client/account) and a mode selector (competitor \| client). | US-1, US-2 | Given a target + mode, the orchestrator starts a run and returns a run handle. |
| FR-02 | Must | The system shall decompose a target into a multi-step research plan before executing tool calls. | Findings (decompose is the hard part) | Given a vague target, the run produces an explicit plan of ≥2 research steps, visible in the trace. |
| FR-03 | Must | The system shall gather public signal via Gemini grounded web search. | US-1 | Given competitor mode, public findings include ≥3 source-cited items (e.g. positioning, news, pricing signal). |
| FR-04 | Must | The system shall gather private signal only through scoped, user-authorized MCP connectors. | US-3 | Given a connected CRM/doc store, private findings are retrieved via MCP within granted scopes only. |
| FR-05 | Must | The system shall never pass private data into the public (grounded-search) tool boundary. | US-3, CISO | Trace shows no private field is included in any grounded-search call payload. |
| FR-06 | Must | The system shall merge public and private signal into a single coherent artifact (not two separate summaries). | US-2, Findings | Client-mode artifact contains interleaved public + private sections referencing the same account entity. |
| FR-07 | Must | The system shall produce a structured **battlecard** (competitor mode) conforming to a defined schema. | US-1 | Output validates against `artifacts/schemas/battlecard`. |
| FR-08 | Must | The system shall produce a structured **account brief** (client mode) conforming to a defined schema. | US-2 | Output validates against `artifacts/schemas/account_brief`. |
| FR-09 | Must | The system shall write the artifact back to the user's workspace as a durable artifact and return a reference. | US-5 | A document/record is created in the connected target; the run returns its id/URL. |
| FR-10 | Must | The system shall degrade gracefully: a single tool failure produces a partial artifact that flags the missing source rather than failing the run. | NFR-Reliability | Given an unavailable private connector, a public-only artifact is produced with an explicit "source unavailable" note. |
| FR-11 | Should | The system shall route inference through an LLM gateway that abstracts the backend (Vertex/Gemini vs vLLM). | US-4 | Backend is selected by config; orchestration code contains no direct backend SDK calls in the private-data path. |
| FR-12 | Should | The system shall emit a run trace (plan → tool calls → merge → write) for observability and demo. | Ops, Findings | Each run produces a structured, inspectable trace. |
| FR-13 | Could | The system shall stream run progress to the caller (plan + step completion). | NFR-Performance | Caller receives incremental updates before final artifact. |
| FR-14 | Won't (this release) | The system shall support scheduled / continuous re-runs (monitoring). | Out of scope | — |
| FR-15 | Won't (this release) | The system shall support multi-tenant auth, billing, and org isolation. | Out of scope | — |

---

## Non-Functional Requirements

| ID | Category | Requirement | Metric | Target | Source |
|---|---|---|---|---|---|
| NFR-01 | Performance | Competitor-mode run completes within budget | end-to-end latency | ≤ 90s (p50) | BA perf |
| NFR-02 | Performance | Client-mode (multi-source) run completes within budget | end-to-end latency | ≤ 120s (p50) | BA perf |
| NFR-03 | Reliability | Single-source failure does not fail the run | degraded-run success rate | 100% produce partial artifact | FR-10 |
| NFR-04 | Security / Sovereignty | Public/private boundary enforced at the tool layer, not by prompt | private-data leakage to public path | 0 incidents (verifiable in trace) | CISO, US-3 |
| NFR-05 | Security | MCP connectors operate only within user-granted scopes | out-of-scope access attempts | 0 | CISO |
| NFR-06 | Portability | Inference backend swappable without orchestration change | files changed to swap Vertex→vLLM | config-only (0 orchestration edits) | US-4 |
| NFR-07 | Scalability | Agent runtime is stateless and horizontally scalable | concurrent runs (demo) | bounded by inference quota, not app state | Ops |
| NFR-08 | Observability | Every run is traceable end-to-end | runs with complete trace | 100% | FR-12 |
| NFR-09 | Compliance | No public-cloud dependency in the private-data path (prod target) | cloud edges on private path in arch diagram | 0 | BiltIQ thesis |
| NFR-10 | Demo | Demo is deterministic / offline-safe for private data | reliance on live external private source | seeded mock data available | Risk mitigation |

---

## Constraints

| # | Constraint | Source | Impact |
|---|---|---|---|
| C-1 | 4-day build window (today → 2026-06-11 17:00 PT) | Challenge deadline | Forces vertical-slice scoping; competitor mode first |
| C-2 | Must use ADK (or approved OSS framework) + MCP | Challenge Track 1 rules | Architecture committed to ADK + MCP |
| C-3 | Demo inference uses Gemini 2.x via Vertex AI | Challenge terms; $500 credits | Public path is Gemini-bound for demo |
| C-4 | Submission requires: code, video, architecture diagram, testing access (live demo/login) | Challenge requirements | Cloud Run deploy + diagram + video are hard deliverables |
| C-5 | Compliance mode `cloud_ok` for demo; architecture must remain on-prem-portable | AGENT_RULES.md | Gateway abstraction is non-negotiable for the thesis |
| C-6 | Region: APAC (BiltIQ AI, India) | Org location | Eligible for APAC regional track |

---

## Assumptions

| # | Assumption | Risk if wrong | Validation plan |
|---|---|---|---|
| A-1 | Gemini grounded search returns deal-relevant public signal with citations | Public artifact thin / unconvincing | Smoke-test grounding on 2-3 real competitors early |
| A-2 | One MCP connector (mock CRM / doc store) is enough to prove the private boundary on video | Private-mode demo weak | Build the connector + seed data in slice 2 |
| A-3 | A thin LLM gateway + a vLLM smoke test sufficiently proves portability to judges | Sovereignty claim reads as a slide | Record the vLLM smoke test as part of the demo |
| A-4 | Cloud Run + Vertex quota under $500 credits covers demo load | Demo throttled | Monitor quota; keep runs bounded |
| A-5 | Judges weight architectural sovereignty as genuine innovation | Innovation score lower than hoped | Make the boundary the centerpiece of the narrative + diagram |

---

## Traceability Matrix

| Req ID | Source | Component (target) | Test | Status |
|---|---|---|---|---|
| FR-01 | US-1/2 | `agent/orchestrator` | TC-01 entrypoint | Planned |
| FR-02 | Findings | `agent/orchestrator` (plan step) | TC-02 plan-emitted | Planned |
| FR-03 | US-1 | `tools/public/grounded_search` | TC-03 public-findings | Planned |
| FR-04 | US-3 | `tools/private/mcp_*` | TC-04 scoped-fetch | Planned |
| FR-05 | US-3 | boundary guard | TC-05 no-leak (trace assertion) | Planned |
| FR-06 | US-2 | `agent/merge` | TC-06 merged-artifact | Planned |
| FR-07 | US-1 | `artifacts/schemas/battlecard` | TC-07 schema-valid | Planned |
| FR-08 | US-2 | `artifacts/schemas/account_brief` | TC-08 schema-valid | Planned |
| FR-09 | US-5 | `artifacts/writer` | TC-09 write-back | Planned |
| FR-10 | NFR-03 | degradation handler | TC-10 partial-on-failure | Planned |
| FR-11 | US-4 | `llm/gateway` | TC-11 backend-swap | Planned |
| NFR-04 | CISO | boundary guard | TC-05 (shared) | Planned |
| NFR-06 | US-4 | `llm/gateway` | TC-11 (shared) | Planned |

---

## Decisions (resolved 2026-06-07)

| # | Question | Decision | Build implication |
|---|---|---|---|
| Q-1 | Private MCP connector | **Real Google Workspace (Docs + Calendar)** | OAuth-scoped Workspace MCP connector; read-only. Keep a seeded fallback for offline demo safety. |
| Q-2 | Artifact write-back target | **All three** — Google Doc, CRM record, Markdown | Build a pluggable `ArtifactWriter` interface w/ 3 backends. Priority: Doc → Markdown → CRM. |
| Q-3 | vLLM portability proof | **Full** — gateway + smoke test + partial deploy + diagram | LLM gateway is mandatory; smoke test guaranteed; partial on-prem deploy as stretch. |
| Q-4 | Lead vertical | **Industry-agnostic** — adaptable to any vertical | No vertical hardcoding; prompts + schemas stay generic; vertical is a config/context input. |
| Q-5 | Region | **APAC** (BiltIQ AI, India) | Eligible for APAC regional track. |

### Scope-risk note (constraint C-1: 4 days)
All choices are the maximal option. Mitigation = a **fallback ladder** per layer so there is always a working demo:
- **Connector:** real Workspace (target) → seeded mock (fallback if OAuth/quota blocks).
- **Write-back:** Markdown (always works) → Google Doc → CRM (stretch).
- **vLLM:** gateway + recorded smoke test (guaranteed) → partial on-prem deploy (stretch).
- **Modes:** competitor mode fully working + deployed first → client mode + merge second.
