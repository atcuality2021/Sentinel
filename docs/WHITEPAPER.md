# Sentinel — Sovereign Intelligence Agent

### A research agent that keeps public and private data on separate trust boundaries — and runs on your own GPUs.

**BiltIQ AI / Aarna Tech Consultants Pvt. Ltd.** · Built for the Google for Startups AI Agents Challenge (Track 1: Build, APAC)

> Every claim in this document maps to code and a passing test. See the **Evidence map (Appendix A)** — the point of this paper is that the trust properties are *demonstrable*, not asserted.

---

## 1. The problem

Organizations in regulated sectors — healthcare, BFSI, government, defence — have the same unmet need: **fast, cited, multi-step research that combines open-web signal with their own private data.** Today they must choose between two unacceptable options:

- **Public-web AI agents** (ChatGPT-style search, perplexity-style tools) are fast and well-grounded, but they **leak**: feeding a private customer record or clinical note into a third-party cloud LLM is, for many of these organizations, a legal or contractual non-starter (RBI data-localization, hospital data-governance, defence sovereignty).
- **Private-data tools** (internal RAG, CRM search) are safe but **siloed and slow**: they can't reach the open web, can't reason across both worlds, and produce unstructured output a human still has to verify.

The result: the organizations with the most to gain from agentic research are the ones structurally locked out of it.

## 2. The thesis — *Sovereign-to-Action*

Sentinel keeps **both** data worlds and separates them **in code, not in a prompt**:

| | Public boundary | Private boundary |
|---|---|---|
| **Tool** | `google_search` (cloud) / pluggable web search | scoped Workspace MCP, read-only |
| **Data** | open web | the customer's CRM / Docs / Calendar / internal stores |
| **Enforcement** | the public agent **cannot hold** a private tool | the private agent **never touches** the web |

Because the separation is **structural**, one consequence falls out for free: the **same agent** runs cloud-native (Gemini on Cloud Run) for a demo and **fully sovereign on-prem** (vLLM/Gemma on the customer's own GPUs) for production — a configuration swap, not a rewrite.

**This is the moat: zero-egress agentic intelligence for organizations that legally cannot send private data to a third-party cloud.**

## 3. What Sentinel is

You give Sentinel an **objective**. It:

1. **Plans** the objective into a step-DAG (a directed graph of research steps).
2. **Staffs** each step with a specialist agent — reusing a vetted one from a registry, or *creating* a new one when the step is novel.
3. **Gates** execution by a per-project autonomy setting: *propose-then-approve* (a human signs off the plan) or *autonomous* (it runs).
4. **Executes** the DAG on a two-pass sovereign engine: a fast model for tool-calling, a larger model for reasoning.
5. **Returns** a typed, **fully-cited**, persona-adapted result — every fact tagged by the boundary it came from — plus an independent quality grade.

Built surface today: **~9,900 lines of Python, 410 passing tests, 4 architecture decision records (ADRs), a working dashboard.**

## 4. Architecture (four layers)

```
Project(context) ─▶ Task(objective × DOMAIN × persona)
   ─▶ Orchestrator:  PLAN (step-DAG)  +  STAFF (reuse | create specialist)  +  autonomy GATE
   ─▶ DAG runner on the two-pass sovereign engine (fast tools → large reasoner)
   ─▶ typed, CITED, persona-adapted Result  +  model grade
   ─▶ memory + provenance + project dashboard
```

| Layer | Responsibility | Defining design choice |
|---|---|---|
| **Sovereign engine** | Two-pass tiered execution; cloud↔on-prem parity | The reasoning backend is resolved per-role; under `on_prem_required` **no cloud model object is ever constructed** |
| **Trust boundary** | Public/private separation | Enforced at *build time* (which tools an agent can hold), not by instruction — and proven by a test that fails if anyone wires a private connector into the public path |
| **Research skills** | Domain knowledge as data | A new research domain is a declarative spec (steps + output schema), **not** new engine code |
| **Orchestration** | Plan, staff, govern, grade | A registry reuses or mints specialists; an autonomy gate decides whether a plan runs; an independent judge grades the output |

## 5. The universal model — *any research, for anyone*

A unit of work carries two composable dimensions beyond the objective:

- **Domain** = *what to research* → which sources/tools and which output schema. Shipped: market/competitor, account, self-profile, compare. The pattern extends to nutrition, software, finance, academic study, and more — each is data, not code.
- **Persona** = *who it's for* → reading level, tone, format, credible-source policy. The persona changes the **presentation only**; the underlying facts and citations are copied verbatim by code, so two personas over one research job share byte-identical facts and differ only in how they read.

Competitive intelligence is simply the **first packaged domain** — the proving deliverable, not the ceiling.

## 6. The trust model — structural, not prompted

Three safety properties, each enforced in code and pinned by tests:

1. **Boundary separation (public ⊥ private).** The public research agent is built without any private tool; the private agent is built without any web tool. A regression test fails if the wiring is ever crossed.
2. **No runtime escalation.** An agent's tools and data boundary are fixed on its spec at build time and are **never derived from content it reads**. Scraped web text is fenced as *source material — data, not instructions*; a planner-created specialist is minted public-only and tool-free and cannot grant itself private access — even if its capability name *is* an injection attempt.
3. **Sovereignty enforcement.** When a project declares `on_prem_required`, the model resolver structurally refuses to construct a cloud (Gemini) object — provable by introspecting the built agents, not by trusting a flag.

**Why this matters for a whitepaper claim:** prompt-based guardrails can be argued around ("but a clever prompt could…"). Build-time structural guarantees cannot — the capability simply does not exist in the object graph. That is the difference between *trust we ask for* and *trust we can prove*.

## 7. Quality & governance

- **Provenance-first.** Every finding is tagged public or private; every claim is cited; the dashboard renders the public-vs-private provenance split. Auditable by construction.
- **Governed autonomy.** A per-project gate chooses *propose-then-approve* (default — nothing runs until a human approves the plan) or *autonomous*. The same system fits a cautious enterprise and a fast individual.
- **Self-grading.** A hard-gate code grader (schema-valid, boundary-clean, citations resolve, no fabricated claims) plus an **independent** model grader (a separate judge model scoring a five-axis rubric) run on the production path — so a weak result is flagged, not presented as fact.

## 8. Where it applies

| Sector | Why Sentinel specifically |
|---|---|
| **Healthcare** (hospitals, pharmacy chains, NHA/CDSCO) | Clinical/patient data never leaves the premises; cited output for governance |
| **BFSI** (banks, NBFCs, insurance) | Borrower/customer intelligence with PII held on-prem; RBI-friendly |
| **Government & defence** (iDEX / ADITI / DRISHTI) | `on_prem_required` ⇒ structurally zero external API calls |
| **Manufacturing & enterprise** | Competitive/market intelligence without leaking strategy to a SaaS vendor |
| **Education** | Research adapted to a controlled reading level |

Sentinel is the **horizontal research layer** that can sit on top of the existing ATC suite — CommandCenter (CRM) as a private connector, Manthan (RAG) as a source.

## 9. How it helps — the value

- **Unlocks AI for data you legally cannot send to the cloud** — the difference between "can't use AI here" and "can."
- **Hours → minutes**, with structured, cited output instead of a chat blob to re-verify.
- **Auditable** — provenance + citations + boundary tags answer "where did this claim come from?"
- **Governed** — the autonomy gate matches the customer's risk posture.
- **Cheap to extend** — a new domain or persona is data; vetted specialists are reused via the registry.
- **Trustworthy** — independent grading flags low-quality results.

## 10. Honest limits & roadmap

- **High-stakes clinical/legal domains are gated OFF** by design until a source allow-list + factuality eval exist — over-blocking is deliberate for a safety gate.
- The challenge build runs `cloud_ok`; the on-prem path is architecturally proven (config-swap, tested) but the full live Workspace-MCP + multi-GPU demo is the remaining integration.
- Persona adaptation and model-grading are wired into the run path; per-domain **golden eval sets** are not yet seeded (data-entry, mechanism in place).

---

## Appendix A — Evidence map (claim → where it lives → test)

| Claim | Code | Proof |
|---|---|---|
| Public agent cannot hold a private tool | `agent/governance.py`, `agent/modes/spec.py` | `tests/test_boundary.py` |
| Cloud↔on-prem is a config swap | `llm/gateway.py`, `agent/modes/_build.py` | `tests/test_gateway.py` |
| `on_prem_required` ⇒ no Gemini object built | `agent/governance.py` (`resolve_model(cloud_allowed=)`) | `tests/test_governance.py`, `tests/test_phase3_registry.py` |
| A new domain is data, not engine code | `agent/modes/spec.py` (`ResearchModeSpec`) | `tests/test_research_pipeline.py` |
| Planner turns a Task into a step-DAG | `agent/orchestrator_planner.py` | `tests/test_phase3_planner.py` |
| Registry reuses or creates a specialist | `agent/registry.py` | `tests/test_phase3_registry.py` |
| Created specialists cannot escalate boundary/tools | `agent/orchestrator_planner.py` (`_mint_created_spec`), `agent/registry.py` (`validate_agent_spec`) | `tests/test_phase3_injection.py` |
| Autonomy gate: nothing runs until approved (default) | `agent/autonomy.py` | `tests/test_phase3_autonomy.py` |
| A created capability actually executes end-to-end | `agent/dag.py` (`_run_created_step`) | `tests/test_phase3_created_exec.py` |
| Scraped web text is fenced as data, not instructions | `tools/sanitize.py`, `tools/public/web_search.py` | `tests/test_phase3_injection.py` |
| Persona changes presentation, not facts | `agent/persona.py`, `agent/dag.py` (`_finalize_result`) | `tests/test_phase3_finalize.py` |
| Output is code-graded + model-graded | `eval/graders.py`, `eval/runner.py` | `tests/test_phase2_*`, `tests/test_phase3_finalize.py` |
| High-stakes domains are blocked at task creation | `artifacts/schemas.py` (`is_high_stakes`) | `tests/test_phase1_schemas.py` |

## Appendix B — Architecture decision records

- **ADR-0001** — A2A coordinator + Gemma-4 tiering (fast tool-caller / large reasoner, two-pass).
- **ADR-0002** — Remote A2A private node.
- **ADR-0003** — Projects / Tasks / eval store.
- **ADR-0004** — Agent-specs registry table (reuse-by-score).

*Status: living document. Last updated 2026-06-08.*
