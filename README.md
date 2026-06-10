<h1>Sentinel — Sovereign Intelligence Agent</h1>

**One agent, two modes, two trust boundaries.** Sentinel is an autonomous research agent
for regulated SMBs (BFSI, healthcare, government). It gathers **public** signal via Gemini
grounded search and **private** context via scoped MCP connectors (CRM, Docs, Calendar),
reasons across both, and writes a structured **battlecard** or **account brief** back to
your own workspace — with every fact tagged by the boundary it came from.

> Built for the **Google for Startups AI Agents Challenge** (Track 1: Build, APAC).

---

## The one thing that makes Sentinel different

Public-data agents are fast but leak. Private-data tools are safe but slow and siloed.
Sentinel keeps both — and keeps them **structurally separated**:

| | Public boundary | Private boundary |
|---|---|---|
| Tool | `google_search` (Gemini-native grounding) | scoped Workspace MCP (read-only) |
| Data | open web | your CRM / Docs / Calendar |
| Enforcement | the public agent **cannot hold** an MCP tool | the private agent never touches the web |

The separation is enforced **in code, not in a prompt** — and proven by a test
([`tests/test_boundary.py`](tests/test_boundary.py)) that fails if anyone ever wires a
private connector into the public pipeline.

Because the boundary is structural, the **same agent** runs cloud-native for the demo
(Gemini on Cloud Run) and **sovereign on-prem** for production (vLLM on the customer's own
GPUs) — a config-only swap, proven by [`tests/test_gateway.py`](tests/test_gateway.py).

---

## Who it's for

Revenue and strategy teams at regulated SMBs who need competitor and account intelligence
but **cannot** send private client data to a third-party SaaS or cloud LLM.

---

## Quick start (local)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                   # 693 tests, no API key needed

# add a Gemini key for a live run (https://aistudio.google.com/apikey)
cp .env.example .env && $EDITOR .env        # set GOOGLE_API_KEY=...

# CLI
python -m sentinel "Stripe" --mode competitor

# Dashboard UI (live demo surface) → http://localhost:8080
sentinel-web
```

The dashboard has a collapsible sidebar and pages for **Dashboard** (KPI cards + live charts,
including the public-vs-private *provenance* donut), **New Run** (with the Cloud/On-prem
backend toggle), **Artifacts**, and **Backends**.

## Deploy a live URL (Cloud Run)

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
GOOGLE_API_KEY=AIza... ./deploy/cloudrun.sh   # prints the public HTTPS URL
```

## Run on-prem (sovereign) instead of cloud

```bash
# 1) serve Gemma locally with vLLM (one command)
HF_TOKEN=hf_xxx docker compose -f deploy/vllm-compose.yml up

# 2) point Sentinel at it — no code change (or just flip the UI toggle)
export SENTINEL_LLM_BACKEND=vllm          # or: cp .env.vllm .env
export VLLM_API_BASE=http://localhost:8000/v1
export VLLM_MODEL=google/gemma-3-4b-it
python -m sentinel "Acme Corp" --mode client --backend vllm
```

Two ready presets: `.env.gemini` (cloud) and `.env.vllm` (on-prem Gemma) — `cp` either to `.env`.

---

## How it works

| Stage | What happens |
|---|---|
| **Plan** | Orchestrator routes the request to the boundaries the mode needs |
| **Public research** | `public_research` agent runs Gemini grounded search over the open web |
| **Private research** | `private_research` agent reads scoped Workspace data via MCP (client mode) |
| **Synthesize** | A schema-bound synthesizer merges both into a `Battlecard` / `AccountBrief` |
| **Write** | A pluggable writer persists it (Markdown today; Google Doc / CRM via MCP) |

Diagram: [`docs/architecture/diagram.html`](docs/architecture/diagram.html) (open in a
browser) · source [`docs/architecture/diagram.mmd`](docs/architecture/diagram.mmd).

If a private source is unavailable, the brief **degrades gracefully** — it still ships,
with the missing source recorded as a flagged `Gap` (never silently dropped).

---

## Tech

Python 3.11+ · **Google ADK 2.2** (`LlmAgent`, `AgentTool`, `google_search`, `McpToolset`) ·
**Gemini 2.x** via AI Studio / Vertex · **Gemma-4 dual-tier** (12B tool-caller + 26B reasoner,
on-prem via LiteLLM → vLLM) · **MCP** for private connectors ·
**FastAPI** server-rendered UI · **Cloud Run** hosting.

Research domains: competitor · client · finance · software · academic · nutrition · travel.
Memory: episodic (SQLite run store) + semantic (ChromaDB + BM25 + reranker) + procedural (playbooks).
Evaluation: built-in grader + score write-back + telemetry.

## Project docs

- Business case → [`docs/business-analysis.md`](docs/business-analysis.md)
- Requirements (SRS) → [`docs/srs.md`](docs/srs.md)
- Architecture → [`docs/architecture/overview.md`](docs/architecture/overview.md)
- Compliance mode → [`AGENT_RULES.md`](AGENT_RULES.md) § Compliance (`cloud_ok` for demo;
  architecture is `on_prem_required`-portable by design)
