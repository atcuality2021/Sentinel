# Sentinel — Sovereign Intelligence Agent

> Built for the **Google for Startups AI Agents Challenge** (Track 1: Build, APAC)

**Sentinel** is an autonomous multi-agent research platform for regulated SMBs. Give it a research objective and it plans, executes, and delivers a structured intelligence report — with every finding tagged by the source boundary it came from (public web vs. private data).

**Live demo:** [sentinel.atcuality.com](https://sentinel.atcuality.com)

---

## What makes Sentinel different

Most AI research tools are either fast-but-leaky (cloud LLM reads your private data) or safe-but-siloed (can't touch the web). Sentinel keeps both, separated by structure:

| | Public boundary | Private boundary |
|---|---|---|
| Sources | Open web (Gemini grounded search, DDG, SearchAPI) | Your CRM, Docs, Email (scoped MCP connectors) |
| Enforcement | Public agents **cannot hold** private MCP tools | Private agents never touch the web |
| Output | Every finding tagged `public` or `private` | Gap analysis when private data unavailable |

The separation is enforced in **code**, not in a prompt. You can verify it: `tests/test_boundary.py` fails if anyone wires a private connector into the public pipeline.

The same agent runs cloud-native (Gemini 2.5 Flash) **or** fully on-prem (Gemma-4 dual-tier: 12B tool-caller + 26B reasoner via vLLM) — a config-only swap, no code change.

---

## Core features

- **9 research domains** — competitor, client, market, finance, software, academic, nutrition, travel, e-commerce/deals
- **Multi-agent DAG pipeline** — planner + parallel researchers + synthesizer, shown live as a step-by-step animated pipeline
- **Sovereign mode** — Gemma-4 on-prem dual-tier (12B tool-calling + 26B reasoning); zero cloud egress, proven by test suite
- **Self-driving memory** — episodic run history, semantic entity memory (SM-2 reinforced), per-source knowledge base (ChromaDB + BM25)
- **Project workspace** — organize research into Projects → Tasks → Reports, with KB, memory, and artifact tabs
- **Personas** — analyst presets (board member, SMB owner, policy analyst…) shaping depth and tone
- **Live pipeline UI** — real-time agent handover animation: which agent is running, on which model, and model transitions (12B → 26B)
- **Citations** — every finding attributed to a public or private source

---

## Architecture

```
Browser (Next.js 16)
    │
    ▼ (Next.js rewrites → relative URL, no CORS)
FastAPI backend  (:8094)
    │
    ├── Planner  ─────────────────── LLM: Gemini 2.5 Flash / Gemma-4-12B
    │     └── DAG of agent steps
    │           ├── Public researcher  (Gemini grounded search / DDG / SearchAPI)
    │           ├── Private researcher (scoped MCP: CRM, Docs, Calendar)
    │           ├── Synthesizer        (Gemma-4-26B reasoner / Gemini)
    │           └── Grader             (quality score + gap analysis)
    │
    ├── Memory harness
    │     ├── Episodic store   (SQLite run history)
    │     ├── Semantic store   (ChromaDB vector + BM25 + SM-2 reinforcement)
    │     └── Knowledge Base   (per-project crawled sources)
    │
    └── Memory worker (background)
          └── 4 connectors: web crawler, YouTube, email, social
```

**Tech stack:**
- Python 3.12 · FastAPI · Google ADK 2.x (`LlmAgent`, `AgentTool`, `google_search`, `McpToolset`)
- Next.js 16 · TypeScript · Tailwind CSS · SWR (live polling)
- Gemini 2.5 Flash (cloud) + Gemma-4 12B/26B via vLLM (on-prem sovereign)
- SQLite · ChromaDB · BM25 · Firecrawl MCP · SearchAPI MCP

---

## Quick start

### Option A — Live demo

Go to [sentinel.atcuality.com](https://sentinel.atcuality.com), log in (ask for credentials), and create a new task inside any project.

### Option B — Run locally

**Prerequisites:** Python 3.12+, Node.js 20+, a Gemini API key from [aistudio.google.com](https://aistudio.google.com/apikey)

```bash
# 1. Clone
git clone https://github.com/atcuality2021/Sentinel.git
cd Sentinel

# 2. Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Set env (copy template and add your Gemini key)
cp .env.example .env
# Edit .env: set GOOGLE_API_KEY=AIza...

# Run backend
uvicorn sentinel.web.app:app --host 0.0.0.0 --port 8094

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev   # → http://localhost:3001
```

On first visit, you'll be prompted to set a password.

### Option C — On-prem sovereign (Gemma-4, no Gemini key)

```bash
# 1. Serve Gemma-4 locally via vLLM
HF_TOKEN=hf_xxx docker compose -f deploy/vllm-compose.yml up

# 2. Set backend to vllm in .env
export SENTINEL_LLM_BACKEND=vllm
export VLLM_API_BASE=http://localhost:8000/v1

# 3. Start backend + frontend as above
```

Switch between Gemini and vLLM at runtime from the Settings page — no restart needed.

---

## Testing

```bash
# Unit + integration (no API key needed — all mocked)
pytest -q                    # ~946 tests

# E2E against a live backend
SENTINEL_URL=http://localhost:8094 pytest tests/test_e2e_full.py -v
```

Key test files:
- `tests/test_boundary.py` — structural public/private separation
- `tests/test_gateway.py` — cloud↔on-prem model routing
- `tests/test_memory_brain_connectors.py` — memory worker and connectors
- `tests/test_e2e_memory_brain.py` — end-to-end memory pipeline

---

## Project structure

```
src/sentinel/
├── agent/          # Agent builder, DAG runner, mode pipelines
├── artifacts/      # Schemas (Battlecard, AccountBrief, etc.) + writer
├── config/         # Prompt registry, YAML config, governance
├── llm/            # Model gateway — Gemini + vLLM, dual-tier routing
├── memory/         # Episodic + semantic + KB stores; memory worker + connectors
├── web/            # FastAPI app, JSON API, HTML render
└── strategy/       # Playbook loader + overlay agents

frontend/           # Next.js 16 app
├── app/(app)/      # Projects, Tasks, Agents, Settings, Memory pages
├── components/     # UI components (TextureCard, AnimatedNumber, TerminalAnimation…)
└── lib/            # API client, fetcher, typed interfaces

docs/
├── architecture/   # Overview, stack, ADRs
├── specs/          # Per-task specs (HTML)
└── CONTEXT.md      # Product vision and non-goals
```

---

## Docs

- Architecture overview → [`docs/architecture/overview.md`](docs/architecture/overview.md)
- Tech stack + wrappers → [`docs/architecture/stack.md`](docs/architecture/stack.md)
- ADR-0001 (A2A coordinator + dual-tier) → [`docs/adr/ADR-0001-coordinator-a2a.md`](docs/adr/)
- Business case → [`docs/business-analysis.md`](docs/business-analysis.md)
- Compliance mode → [`AGENT_RULES.md`](AGENT_RULES.md)
