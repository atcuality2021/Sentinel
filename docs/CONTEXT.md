# /docs/CONTEXT.md — Company & Product Context

**Purpose:** Background context the AI agent needs for any task involving documentation, marketing, communications, strategy, or anything user-facing. Read alongside `MEMORY.md` for any task that's not pure code.

---

## Who we are

**BiltIQ AI** (legal entity: Aarna Tech Consultants Private Limited) is a DPIIT-recognised startup and NVIDIA Inception Partner based in Jamshedpur, Jharkhand, India. We build agentic AI systems across deployment models — on-premise for regulated / sovereign-data work, cloud-native for non-regulated products and internal tools, and hybrid where the contract calls for it. Compliance posture is **declared per project** in `AGENT_RULES.md` § Compliance, not assumed by default.

**Positioning lines** (used in marketing for the on-premise category specifically): "Your Data. Your Premises. Your AI." For non-regulated cloud work, frame around capability and cost — not data sovereignty.

[PROJECT: customize below — not every BiltIQ repo is about a regulated-sector product.]

---

## What we make (the ATC product suite)

All products carry the **ATC** prefix. Never drop or modify it.

- **ATC Manthan** — Document AI / RAG
- **ATC Quest** — AI-native LMS (paying customers, TRL 8)
- **ATC Campus** — Edge AI for schools
- **ATC Chat** — Conversational AI with RAG + MCP
- **ATC Voice** — ASR / TTS / speech intelligence
- **ATC Flow** — Workflow automation
- **ATC CommandCenter** — AI-native CRM
- **ATC Connect**, **ATC Social**, **ATC CMS**, **ATC Ops** — supporting suite

**In development:**
- **Sehat Saathi** — WhatsApp-native health companion (TRL 5)
- **ATC HealthBridge** — B2G FHIR R4 infrastructure for NHA
- **CDSCO RegAI** — regulatory AI platform

---

## What we explicitly do NOT do (default — overridden by per-project compliance mode)

These defaults apply unless the repo's `AGENT_RULES.md` § Compliance declares otherwise:

- Do not deploy on public cloud for production workloads of regulated-sector products.
- Do not call external AI APIs in production paths of `on_prem_required` projects.
- Do not list cloud AI models as components in product specs of `on_prem_required` projects.
- Do not claim certifications we don't hold (no SOC 2, ISO 27001, HIPAA/GDPR/FedRAMP claims unless audited).
- Do not use stock photography in BiltIQ assets.
- Do not use marketing hyperbole — banned vocabulary list is in `AGENT_RULES.md`.

For `on_prem_preferred` and `cloud_ok` projects, cloud AI use is allowed per the compliance mode rules.

---

## Who we serve

Regulated sectors (default `on_prem_required` or `on_prem_preferred`):
- **Healthcare** — hospitals, clinics, pharmacy chains, B2G health (NHA, CDSCO)
- **Education** — schools, colleges, training institutes
- **BFSI** — banks, NBFCs, insurance
- **Manufacturing** — SMB and enterprise
- **Government** — state and central, including defence (active iDEX, ADITI, DRISHTI bids)

Non-regulated and internal-tools projects (often `cloud_ok` or `on_prem_preferred`):
- Internal automation tools.
- Prototypes and spikes.
- Client-approved cloud deployments.

If a task involves drafting customer-facing material, default tone is direct, technical, evidence-led.

---

## Infrastructure context

**GPU nodes (4):**
- Node 1 (192.168.1.252): Qwen3-Omni-30B — multimodal/vision
- Node 2 (192.168.1.245 / 192.168.1.113): ASR, VL embeddings, MedGemma-4b-it, Qwen3-VL-Embedding-2B
- Node 3 (192.168.1.113): Qwen3.5-35B-A3B MoE — primary reasoning
- Node 4 (192.168.1.139): ATC-System — FastAPI + PostgreSQL + pgvector + Qdrant + Redis + MinIO + Docker; RTX PRO 6000 Blackwell + RTX 4070; training/fine-tuning node

**Stack:** vLLM (OpenAI-compatible local endpoints), FastAPI, PostgreSQL, Qdrant, MinIO, Redis, Celery, MCP. Containerized with Docker Compose.

**Active safety flag:** Qwen3.5-9B-Uncensored at Node 2 port 8102 has stripped alignment fine-tuning. **Do not use it in any user-facing medical orchestration role.** Replace with aligned instruct variant before any deployment.

[PROJECT: replace with actual deploy infra for this repo if different.]

---

## Brand rules (enforced in code, docs, and copy)

- **"IQ"** in BiltIQ wordmark is always Signal Green: `#11BB5B` (light contexts) / `#00E676` (dark contexts).
- **"Bilt"** and **"AI"** are black or white depending on surface — never optional.
- **ATC** product prefix is retained across all products. Never modified.
- Pricing is always in INR.

---

## Commercial context

- **Bootstrapped.** ~₹3 Cr FY26 revenue, ₹4 Cr expansion pipeline, ₹15 Cr FY27 target.
- **Phase-gated capital deployment:** hires and hardware only after project closure/payment.
- **Funding sequence:** non-dilutive grants (iDEX, NASSCOM/MeitY) → revenue-based financing → angel/seed post-Google Accelerator.

---

## Communications

- **Primary contact:** hello@biltiq.ai · +91 8986860088
- **Hiring:** career@biltiq.ai
- **Active domain:** biltiq.ai (atcuality.com retired; retained only for email aliases)
- **Registered address:** 72 G Road, Kadma, Jamshedpur 831005

---

## Updates to this file

- This file changes rarely. When it does, the change requires Harish's approval.
- Anything in flux (current pipeline, active bids, sprint state) lives in `MEMORY.md`, not here.
- Anything specific to one repo (e.g., a single product's architecture) lives in that repo's `/docs/architecture/`, not here.
