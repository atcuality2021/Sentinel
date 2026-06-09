# Business Analysis — Sentinel (Sovereign Intelligence Agent)

**Prepared:** 2026-06-07 · **Author:** BiltIQ AI · **Context:** Google for Startups AI Agents Challenge — Track 1 (Build), APAC. Submission due 2026-06-11 17:00 PT.
**Maps to judging:** Business Case (30%), Innovation & Creativity (20%), and feeds Technical Implementation (30%).

---

## PROBLEM

Regulated startups and SMBs in BFSI, healthcare, and government need competitor and
client intelligence to win and defend deals — but every tool that does this well requires
uploading private CRM records, deal history, and proposal documents to third-party SaaS.
For data-sensitive teams under data-residency and sovereignty obligations, that tradeoff
is a non-starter. So the work stays manual: analysts hand-stitch public web research with
internal records, slowly and inconsistently. The outcome is intelligence that is either
**fast-but-leaky** (SaaS that exfiltrates private data) or **private-but-too-slow**
(manual research that misses the deal window). There is no option that is both fast *and*
sovereign.

## STAKEHOLDERS

| Stakeholder | Goal | Priority |
|---|---|---|
| Sales / strategy analyst (end user) | A complete, trustworthy battlecard or account brief in minutes, not days | High |
| CISO / compliance officer | Private CRM/deal data never leaves authorized boundaries; provable data residency | High (regulatory) |
| Account executive | Walk into a meeting with merged public + private context, not two disconnected docs | High |
| BiltIQ AI (vendor) | Demonstrate the cloud-demo → on-prem-production portability thesis | High (strategic) |
| Challenge judges (Google Cloud / DeepMind) | See declarative ADK orchestration + MCP-enforced security + real business impact | High (winning) |

## USER STORIES

1. **As an analyst, I want to give the agent a competitor name and get a structured
   battlecard** so that I can prep for a competitive deal without a day of manual research.
   - [ ] Given a competitor name, when I run competitor mode, then the agent returns a battlecard with positioning, strengths/weaknesses, pricing signals, and recent news, each tied to a public source citation, within the target time budget.
   - [ ] Given no private connectors, when I run competitor mode, then a complete public-only battlecard is still produced.

2. **As an account executive, I want to give the agent a client/account and get a brief
   that merges public firmographics with our private deal history** so that I walk into the
   meeting fully prepared.
   - [ ] Given an account with a connected CRM, when I run client mode, then the brief merges public signal (news, filings, profiles) with private signal (deal stage, prior proposals, last contact) into one coherent artifact — not two summaries.
   - [ ] Given a private source is unauthorized/unavailable, when I run client mode, then the artifact is still produced and explicitly flags the missing source.

3. **As a CISO, I want private data reached only through scoped, user-authorized
   connections** so that I can certify no private data crosses an external boundary.
   - [ ] Given the public research path, when the agent runs, then no private data is ever passed to the public (grounded-search) tool boundary.
   - [ ] Given an MCP connector, when the agent calls it, then it operates only within the scopes the user granted — verifiable at the tool layer, not just by prompt instruction.

4. **As the vendor, I want the inference layer swappable behind a gateway** so that the
   same agent runs cloud-native for demo and on-prem (vLLM) for regulated production.
   - [ ] Given the LLM gateway, when the backend is repointed from Vertex/Gemini to vLLM, then the orchestration and tools run unchanged (no code path in the private-data flow depends on a public cloud).

5. **As an analyst, I want the result written back to my workspace as a durable artifact**
   so that it lives where my team already works, not in a throwaway chat.
   - [ ] Given a completed run, when synthesis finishes, then the artifact is schema-validated and written to the user's doc store / CRM via MCP, with a returned reference.

## NON-FUNCTIONAL REQUIREMENTS

- **Performance:** end-to-end run (target → artifact) within a demo-credible budget — target ≤ 90s for competitor mode, ≤ 120s for client mode (multi-source). Stretch: streamed progress so the user sees the plan executing.
- **Reliability:** a single tool failure (public or private) degrades gracefully to a partial-but-flagged artifact; the run never hard-fails on one source.
- **Security / sovereignty:** strict public/private boundary enforced at the MCP/tool layer; private data never enters the grounded-search path; connectors operate under user-granted scopes only.
- **Portability:** inference backend swappable (Vertex/Gemini ↔ vLLM) with no change to orchestration or the private-data path.
- **Scalability:** stateless agent runtime on Cloud Run; concurrency bounded by inference quota — horizontally scalable for demo loads.
- **Observability:** every run emits a trace of plan → tool calls → merge → write, for debugging stalled reasoning and for the demo narrative.

## SUCCESS METRICS

| Metric | Baseline (manual) | Target |
|---|---|---|
| Time to a deal-ready battlecard / brief | 0.5–1 working day | < 5 minutes |
| Private data egress to third-party SaaS | required by incumbents | **zero** (architecturally enforced) |
| Public + private merged into one artifact | rare (two disconnected docs) | every client-mode run |
| Cloud → on-prem port effort | full rewrite (incumbents) | inference repoint only, zero orchestration change |
| Challenge outcome | — | Win Build track / regional (APAC) / grand prize |

## OUT OF SCOPE (for the challenge build)

- Continuous monitoring / scheduled re-runs of a competitor or account (one-shot on demand for now).
- Write-back to arbitrary third-party CRMs beyond the demoed connector(s).
- Multi-tenant SaaS hardening (auth, billing, org isolation) — PoC is single-operator.
- Fine-tuning or custom model training — uses Gemini 2.x / vLLM-served base models as-is.
- A polished end-user web UI beyond what the demo requires.

## DEPENDENCIES

| Dependency | Type | Status | Risk if delayed | Mitigation |
|---|---|---|---|---|
| ADK orchestration | Hard | In use | No agent loop | Core; build first |
| Gemini 2.x + grounded search (Vertex) | Hard | Available (challenge credits) | No public research | $500 challenge credits cover demo |
| MCP connectors (CRM / docs / cal) | Hard (≥1 for client mode) | To build | No private signal → client mode degraded | Demo with one well-chosen connector (e.g. a doc store / mock CRM) |
| LLM gateway abstraction | Soft | To build | Portability claim unproven | Even a thin adapter + a vLLM smoke test proves the thesis |
| Cloud Run deploy | Hard (demo) | Standard | No live demo URL | Required for "testing access" submission artifact |
| Artifact schema + writer | Hard | To build | Output is a chat reply, not a durable artifact | Define battlecard + brief schemas early |

## RISKS

- **Risk:** 4-day window; scope creep across two modes + connectors + portability.
  **Mitigation:** vertical-slice competitor mode end-to-end first (public-only, fully working + deployed), then layer client mode + one MCP connector, then the vLLM portability proof.
- **Risk:** judges discount the sovereignty claim as a slide, not a fact.
  **Mitigation:** enforce the boundary at the MCP/tool layer and *show it* — a vLLM smoke test + an architecture diagram where the private path has no cloud edge.
- **Risk:** multi-step reasoning stalls on vague targets (the team's own stated hard part).
  **Mitigation:** explicit decompose→plan step with bounded retries and a trace; treat reasoning reliability as an engineering discipline (aligns with the challenge's Optimize ethos even on the Build track).
- **Risk:** demo depends on a live private data source.
  **Mitigation:** ship a seeded mock CRM / doc store so the demo is deterministic and offline-safe.

## RACI (challenge build)

| Deliverable | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Orchestrator + modes | Eng | BiltIQ AI lead | — | Judges (via demo) |
| MCP boundary + connectors | Eng | BiltIQ AI lead | CISO persona (boundary design) | — |
| LLM gateway + vLLM proof | Eng | BiltIQ AI lead | — | — |
| Demo video + architecture diagram | Eng/PM | BiltIQ AI lead | — | Judges |
| Business case narrative | PM | BiltIQ AI lead | — | Judges |

## OPEN QUESTIONS FOR STAKEHOLDERS

1. **Which MCP connector do we demo for the private boundary?** A seeded mock CRM is safest/deterministic; a real connector (e.g. Google Workspace docs/calendar) is more impressive but riskier in 4 days. (Recommend: seeded mock CRM + a doc store, with one real read-only Workspace connector if time allows.)
2. **Artifact write-back target for the demo** — Google Doc? A CRM record? Returned + persisted? (Recommend: write a Google Doc / Markdown artifact to a connected doc store — visually convincing on video.)
3. **How far do we take the vLLM portability proof?** A full on-prem deploy is out of scope in 4 days; a gateway + a local vLLM smoke test on one prompt proves it. (Recommend: thin gateway + recorded vLLM smoke test.)
4. **Region declaration** — APAC (BiltIQ AI is India-based)? Confirm for the regional-winner track.
5. **Target verticals to feature in the narrative** — lead with BFSI, or healthcare, or government? (Affects the demo persona and sample data.)
