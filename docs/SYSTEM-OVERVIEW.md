# Sentinel — Complete System Overview

> Sovereign Intelligence Agent · Google AI Agents Challenge · Deadline 2026-06-11

---

## What Is Sentinel?

Sentinel is an **autonomous research-to-action agent**. You give it a target — a competitor, a client, a software product, a market, an academic topic, a destination — and it plans the work, runs a multi-agent research pipeline, synthesizes a structured intelligence brief, and recommends prioritised next actions. All of this can run entirely on your own hardware with zero cloud dependency.

**Scale:** 12,002 lines of production Python · 66 source files · 539 passing tests

---

## Architecture at a Glance

```
You → type a research objective
        ↓
Orchestrator reads config → builds a DAG of research steps
        ↓
    Step 1: Self-profile (who are WE?)
    Step 2a: Research rival A     Step 2b: Research rival B
    Step 3a: Compare us vs A      Step 3b: Compare us vs B
    Step 4:  Program strategy (cross-all-rivals synthesis)
        ↓
Each step: Plan → Search Web → Extract facts → Synthesize brief
        ↓
Result: structured artifact → memory stored → report rendered
```

### Two-Pass Sovereign Engine

| Pass | Model | Role | Transport |
|---|---|---|---|
| 1 | Gemma-4 12B (tool-calling) | Plans queries, calls search, extracts per-source notes | Non-streamed (avoids 524 timeout) |
| 2 | Gemma-4 26B (reasoning) | Synthesises all extracted notes into the structured output schema | SSE-streamed |

The two models never run simultaneously — tool-calling and reasoning are architecturally separated.

### Data Boundary Invariant

Every finding is tagged `PUBLIC` (web search) or `PRIVATE` (CRM / internal documents). The boundary is structurally enforced at `MemoryStore.recall()`. Under `on_prem_required`, no Gemini object is constructed — provably zero cloud egress.

---

## Complete Capability Map

### 9 Research Modes

| Mode | Output Artifact | What It Produces |
|---|---|---|
| `competitor` | `Battlecard` | Strengths, weaknesses, pricing signals, recent moves, counter-positioning |
| `client` | `AccountBrief` | Public news + private CRM data merged, strategy overlay, objection handling |
| `self_profile` | `SelfProfile` | Your own org / product profile for "us" side of comparisons |
| `compare` | `ComparisonMatrix` | Axis-by-axis win/lose/parity table per rival |
| `software` | `SoftwareBrief` | Tech stack, API quality, community health, pricing, alternatives |
| `finance` | `FinancialProfile` | Key metrics, market position, risk signals, investment thesis |
| `academic` | `AcademicBrief` | Literature survey, key findings, methodology notes, open research gaps |
| `nutrition` | `NutritionBrief` | Evidence-based claims, dosage guidance, contraindications |
| `travel` | `TravelBrief` | Practical info, highlights, safety notes, budget guidance |

### Intelligence Features

**Strategy overlay (on every artifact):**
- `assessment` — where the target stands + best angle of attack
- `action_plan` — prioritised next moves with timelines
- `objection_handling` — for client/competitor modes

**Program strategy (cross-competitor):**
After running N rivals, a separate strategist synthesises a single cross-product market capture plan.

**39 agent roles** across all skills: planner, public_research, extractor, synthesiser, strategist per skill variant.

### Memory System — Three Tiers, SM-2

| Layer | Stores | Behaviour |
|---|---|---|
| Semantic (entity) | Facts extracted from past runs | SM-2 spaced-repetition: used facts strengthen, stale ones decay and drop |
| Episodic | Run records (what was researched, when, what was found) | Injected into new runs about the same entity — builds on prior context |
| Procedural | Strategy playbooks (Markdown, editable) | Loaded at runtime by the strategy agent |

**User feedback loop (thumbs up/down):** +1 reinforces SM-2 strength on entity facts; -1 weakens ease and strength. Feedback persists in `user_feedback` SQLite table and is applied immediately via `_apply_to_memory`.

### Knowledge Base

| Feature | Implementation |
|---|---|
| Auto-crawl on project creation | Playwright crawler → httpx fallback; SSRF-safe redirect following |
| Chunking | Sentence-aware, overlap-configurable |
| Embedding | Qwen3-VL-Embedding-2B |
| Search | BM25 (keyword) + ChromaDB vector (semantic) + cross-encoder reranker |
| KB chat | Query indexed KB directly from the browser |
| Episodic recall integration | KB hybrid_search supplements LIKE-search when `project_id` provided |

### DAG Orchestrator

- Steps declare `depends_on` relationships
- Independent steps run in parallel (semaphore default: 3 concurrent)
- Failed step → `degraded=True`, dependent steps skipped, independent ones continue
- Budget: max steps, max reasoner calls, wall-clock timeout
- Per-entity step cache: same target in the same session → cache hit skips re-research

### Agent Registry (self-improving)

- All 9 modes seeded as `AgentSpec` rows in SQLite
- Planner can create new specialist specs at runtime for novel capabilities
- `eval_score` written back after every run — higher-scoring specs win future resolution
- Ranking: `(eval_score DESC, version DESC)`; ungraded specs (`eval_score IS NULL`) rank last
- Two graders: deterministic code grader + LLM-as-judge rubric grader (opt-in)

### Governance / Sovereignty

| Mode | Meaning |
|---|---|
| `cloud_ok` | Gemini allowed everywhere |
| `on_prem_preferred` | Default on-prem; Gemini only with an ADR |
| `on_prem_required` | Hard block — no Gemini object constructed, provably |

`block_cloud_on_private=True` forces on-prem for any run that touches private data, even in `cloud_ok` mode.

**Search providers:** Gemini grounding · DuckDuckGo · Brave · SerpAPI · Google CSE · SearXNG

### Web UI — Project Lifecycle

```
Projects → KB → Research (Tasks) → Memory → Artifacts → Report
```

| Tab | What It Shows |
|---|---|
| Projects | Create/delete projects; website → auto-crawl trigger |
| KB | Crawled pages, KB chat panel, hybrid search |
| Research (Tasks) | Create objectives; plan review; approve & run |
| Memory | Episodic run history + entity memory cards |
| Artifacts | All produced artifacts; re-run / delete |
| Report | Consulting-grade written report from run results |

Per-task result page: inline result with citations, provenance bar (public/private split), quality grade, strategy section, thumbs up/down feedback.

### Eval / Grading

| Grader | Type | When |
|---|---|---|
| Code grader | Deterministic | Every run — schema validity, finding counts, boundary consistency, no private leakage |
| Model grader | LLM-as-judge | Opt-in (`SENTINEL_GRADE_SAMPLE=1`) — 5-axis rubric: relevance, faithfulness, completeness, actionability, persona fit |

---

## Who Benefits

### Sales Teams
Input: competitor name + your product website. Output in ≤ 60 seconds: pricing signals, recent moves, counter-positioning angles, next actions. Runs on your server — CRM data never leaves your network.

### Competitive / Market Intelligence Analysts
Run N competitor battlecards in parallel via the DAG. Program strategy synthesises across all. No manual aggregation.

### Engineering Teams
`software` mode: evaluate any tool, library, or API — tech stack, community health, API quality, pricing, alternatives. Structured, cited output.

### Financial Analysts / Investors
`finance` mode: key metrics, market position, risk signals, investment thesis. Evidence-only — every claim has a source URL.

### Researchers / Students
`academic` mode: literature survey on any topic. Cited findings, open gaps, notable researchers, methodology notes.

### Regulated-sector Organisations (Healthcare, BFSI, Government, Defence)
The only intelligence system with a **provable zero-egress mode**. Research, reasoning, and memory all run on your GPUs. Public web search uses DuckDuckGo or SearXNG; no Google, no cloud. Boundary-tagged output proves what came from where.

### Account Executives
`client` mode merges public news with your CRM history (MCP connector). The merged insight — what the public + private combination implies about the account — is the core value. Recommended actions included.

---

## What Sentinel Is NOT

- Not a clinical diagnosis or medical advice tool (high-stakes domains blocked at task creation)
- Not a legal research tool
- Not a general chatbot — every response is a structured, cited, schema-valid artifact
- Not a SaaS product — sovereign agent designed to run on your own infrastructure

---

## Stack Summary

| Layer | Technology |
|---|---|
| Agent framework | Google ADK 2.2.0 — LlmAgent, SequentialAgent, InMemoryRunner, AgentTool |
| LLM backend | Gemma-4 12B (tool-calling) / 26B (reasoning) via vLLM; Gemini (cloud fallback) |
| Embedding | Qwen3-VL-Embedding-2B |
| Vector store | ChromaDB |
| Keyword search | BM25 (rank_bm25) |
| Reranker | Cross-encoder (ms-marco variant) |
| Web framework | FastAPI + Jinja2 (server-rendered; no SPA) |
| Database | SQLite (projects, tasks, specs, memory, feedback, KB chunks) |
| Crawler | Playwright → httpx fallback; SSRF-safe |
| Testing | pytest · 539 tests |

---

*Last updated: 2026-06-09 · Sentinel v1.0 (Google AI Agents Challenge build)*
