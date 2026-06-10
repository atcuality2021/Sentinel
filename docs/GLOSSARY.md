# /docs/GLOSSARY.md — Project Vocabulary

**Purpose:** Domain terms specific to this project (and BiltIQ's shared vocabulary). The agent reads this so it doesn't misinterpret internal vocabulary or invent its own definitions.

**Update rules:**
- Alphabetical within each section.
- One line per term where possible.
- New entries require no approval — anyone can add. Removals/edits go through PR review.

---

## Products & Platforms (BiltIQ-wide)

- **ATC Campus** — Edge AI product for schools.
- **ATC Chat** — BiltIQ's conversational AI product with RAG + MCP support.
- **ATC CMS** — Content management system in the BiltIQ suite.
- **ATC CommandCenter** — AI-native CRM. ~117K LOC, 590 endpoints.
- **ATC Connect** — Communication/integration product.
- **ATC Flow** — Workflow automation product.
- **ATC HealthBridge** — B2G FHIR R4 infrastructure for India's National Health Authority. In development.
- **ATC Manthan** — Document AI / RAG product.
- **ATC Ops** — Operations product.
- **ATC Quest** — AI-native LMS. Paying customers; TRL 8.
- **ATC Raksha** — Defence-focused submission to iDEX Open Challenge.
- **ATC Social** — Social media scheduling product.
- **ATC Voice** — ASR/TTS/speech intelligence product.
- **ATCUALITY** — Legacy brand. Retired. Domain (atcuality.com) retained only for email aliases.
- **BiltIQ** — Active brand and active domain (biltiq.ai). The "IQ" is always Signal Green.
- **CDSCO RegAI** — BiltIQ's regulatory AI platform for pharma compliance. In development.
- **ManthanQuant** — Open-sourced quantization library. 3-bit KV cache compression, 5.12x compression ratio on GB10.
- **Sehat Saathi** — WhatsApp-native health companion. TRL 5.

---

## Infrastructure & Tech

- **ATC-System** — Internal name for Node 4 (192.168.1.139), the training/fine-tuning node.
- **GB10** — NVIDIA Grace Blackwell unified memory platform (~900 GB/s bandwidth).
- **Node 1 / 2 / 3 / 4** — The four GPU nodes. See `/docs/architecture/overview.md` or `CONTEXT.md` for IP and role mapping.
- **Sovereign AI** — On-premise AI positioning, used in customer-facing material for `on_prem_required` projects. Synonyms: private AI, data-residency AI.
- **vLLM** — Local LLM inference server we use across all nodes. Exposes OpenAI-compatible endpoints.

---

## Compliance & Regulatory

- **DPDP Act** — India's Digital Personal Data Protection Act.
- **DPIIT** — Department for Promotion of Industry and Internal Trade. BiltIQ holds DPIIT recognition (DIPP239966).
- **FHIR R4 NRCES v6.5.0** — Indian healthcare interoperability standard. Includes ICD-10, SNOMED CT, LOINC.
- **NHA** — National Health Authority of India. Counterpart for HealthBridge.
- **CDSCO** — Central Drugs Standard Control Organization. Counterpart for CDSCO RegAI.
- **CIN** — Corporate Identification Number. BiltIQ: U72900JH2021PTC017244.
- **GSTIN** — BiltIQ: 20AAVCA7572K1Z7.
- **IEC** — Import Export Code. BiltIQ: AAVCA7572K.
- **Udyam** — MSME registration. BiltIQ: UDYAM-JH-06-0038439.

---

## Defence & Government Programs

- **ADITI 4.0** — DRDO's Acing Development of Innovative Technologies with iDEX. BiltIQ has active bids on PS 18 and PS 24.
- **DRISHTI** — Defence challenge. BiltIQ has active bids on GSL #82 and MDL #70.
- **iDEX** — Innovations for Defence Excellence. The umbrella defence innovation program.
- **iDEX DISC 14** — Defence India Startup Challenge round 14.
- **iDEX Open Challenge** — Submission category for ATC Raksha.
- **JIADA** — Jharkhand Industrial Area Development Authority.
- **JSTAC** — Jharkhand State Technology Advisory Council.

---

## Process & Engineering Terms

- **Anti-Pattern (1-10)** — The 10 categories of AI coding mistake documented in `AGENT_RULES.md`. Defects, not preferences.
- **Attack Loop** — The 7-step task workflow: Think → Plan → Build → Review → Test → Ship → Reflect.
- **ADR** — Architecture Decision Record. Lives in `/docs/adr/NNNN-title.md`.
- **AGENT_RULES.md** — Canonical rules file for any AI-IDE in a BiltIQ repo. IDE-specific files (CLAUDE.md, .cursorrules, .windsurfrules) point to it.
- **Compliance mode** — Per-project posture toward external AI/cloud APIs. One of `on_prem_required`, `on_prem_preferred`, `cloud_ok`. Declared in `AGENT_RULES.md` § Compliance.
- **Mandatory artifacts** — The 8 files every task must produce: `spec.md`, `design.md`, `plan.md`, code, tests, ADR (if applicable), PR, `reflect.md`.
- **Reflect (the step)** — Step 7 of the Attack Loop. Produces `reflect.md`.
- **Skill** — A markdown file with `name`/`description` frontmatter that the agent loads via the `Skill` tool. Lives in the `biltiq-engineering` plugin.
- **Three agents, one session** — The rule that code, tests, and docs come from the same AI-IDE session, not three separate runs.

---

## Brand & Visual

- **Midnight** — `#0D1117`. Used for dark contexts and "Bilt"/"AI" wordmark on light surfaces.
- **Montserrat** — Primary typeface.
- **JetBrains Mono** — Monospace typeface for code and technical contexts.
- **Signal Green** — `#11BB5B` (light contexts) / `#00E676` (dark contexts). The color of "IQ" in BiltIQ.

---

## People & Partners

- **Anthropic** — Provider of Claude models. BiltIQ uses Claude Code as default AI-IDE. Anthropic Cloud API use depends on per-project compliance mode.
- **NVIDIA Inception** — Partner program BiltIQ is enrolled in.
- **Sarvam AI** — Partner (application submitted) for vernacular voice gap.
- **Sam Polsky** — Process auditor.
- **Vikram Pagaria, IRS** — Director, NHA. HealthBridge counterpart.

---

## Project-specific terms

| Term | Definition |
|---|---|
| **two-tier** | 12B tool-callers (pass1, `StreamingMode.NONE`) → 26B reasoners (pass2, `StreamingMode.SSE`). Config: `backend.roles`. Default off (`two_tier=False`). Fixes Cloudflare 524 timeouts on long non-streamed 26B generations. |
| **SearXNG** | Self-hosted metasearch engine; primary sovereign keyless search provider. URL via `SEARXNG_URL` env var. Registered as provider `searxng` in `get_search_tool()`. |
| **_leaf_semaphore** | Process-wide `asyncio.Semaphore` in `orchestrator.py` bounding concurrent ADK `run_step` calls. Sized by `BackendConfig.max_concurrency` (default 3). Loop-bound; auto-recreated on new event loop for test isolation. |
| **parallel per-source extract** | SENTINEL-013 Phase 3. Instead of one extractor reading all `{public_findings}`, `_run_parallel_extract` splits into N per-source units via `_split_findings` and runs one 12B extractor per source concurrently under `_leaf_semaphore`. |
| **ResearchModeSpec** | Declarative mode descriptor in `agent/modes/spec.py`. A new research mode is config+data (a `ResearchModeSpec` with ordered `list[StepSpec]` + output schema), not engine code. |
| **ExtractionSet** | Pydantic v2 schema (`sentinel.artifacts.schemas`). `extractions: list[Extraction]` + `gaps: list[Gap]`. Output of the two-tier extractor stage; consumed by the 26B synthesizer. |
| **_split_findings** | Helper in `agent/dag.py`. Parses `public_findings` into per-source units: JSON list → N items; `{"results":[...]}` envelope → unwrapped; free text → single-source fallback. |
| **gate_proposal** | `sentinel.agent.orchestrator_planner.gate_proposal`. Enforces the autonomy gate: `propose` mode shows the plan without running; `autonomous` runs immediately. The human Approve button calls the `run` route which invokes `gate_proposal(autonomy="autonomous")`. |
| **_run_policy** | `web/app.py` helper. Resolves `{backend, search_provider}` from config + `cloud_allowed` for a project-scoped run. User-selected backend (form toggle) overrides it when present; sovereignty (`on_prem_required`) blocks cloud regardless. |

---

## When to update this file

- Any time a new internal term gets used in Slack, PR, or doc more than twice.
- Any time the agent (or a new dev) asks "what does X mean?" — answer here, not just in chat.
- Major reorganization through PR review. Adding new entries: free-for-all.
