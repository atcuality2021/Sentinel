# Competitive Feature Analysis — Sentinel vs the Incumbents

**Prepared:** 2026-06-07 · **Author:** BiltIQ AI · **Method:** parallel web research (6 vendors) + synthesis
**Purpose:** A factual, feature-by-feature inventory of the competitive/account-intelligence field, mapped
against Sentinel — for the challenge **Business Case (30%)** and to validate the 008/009/010 scope.
**Companion docs:** [`business-analysis.md`](./business-analysis.md) · [`srs.md`](./srs.md) ·
memory `sentinel-market` (positioning verdict).

> **Verification note.** Feature/governance facts below are from each vendor's public site + reputable
> third-party sources (each cluster cited in the per-vendor research). Pricing and any item marked
> *unverified* is third-party-estimated and should not be quoted as fact in the pitch without a primary source.
> Deployment/LLM-governance claims are the load-bearing ones for our wedge — they are stated conservatively
> ("no on-prem option **found**") because absence of a public option is strong but not the same as a vendor denial.

---

## 1. The field (who we benchmarked)

| Vendor | Category | AI layer |
|---|---|---|
| **Klue** | Competitive enablement (battlecards + win/loss) | Compete Agent; Ignition acq. (agentic PMM); MCP server |
| **Crayon** | Competitive intelligence | Sparks (AI agent) + Crayon Answers (gen-AI compete assistant) |
| **Clay / Claygent** | GTM data enrichment + AI web-research agent | Claygent + selectable frontier LLMs |
| **ZoomInfo** | B2B account/sales intelligence + data | Copilot; GTM.AI/MCP; native Claude connector (Jun 2026) |
| **6sense** | ABM / predictive account intelligence + intent | Next Best Actions; agent-powered Revenue AI |
| **Kompyte** (Semrush) | Automated competitive intelligence | Kompyte GPT (battlecard gen) |

Two distinct sub-markets: **competitor-centric** (Klue, Crayon, Kompyte) and **account/buyer-centric**
(Clay, ZoomInfo, 6sense). Sentinel plays in **both** (competitor mode + client mode) — which is unusual,
but each sub-market alone is a red ocean.

---

## 2. Feature matrix — capability parity

Legend: ✅ has it · 🟡 partial / user-assembled · ❌ not offered · 🔷 **Sentinel today** · 🔶 **Sentinel after 008/009/010**

### A. Research / data gathering

| Capability | Klue | Crayon | Clay | ZoomInfo | 6sense | Kompyte | Sentinel |
|---|---|---|---|---|---|---|---|
| Web/news monitoring | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🔷 grounded search (pluggable, sovereign) |
| Review mining (G2/Capterra) | ✅ | ✅ | 🟡 | ✅ | ❌ | ✅ | ❌ *(not planned)* |
| Job-posting / hiring signals | ❌ | ✅ | ✅ | ✅ | 🟡 | ✅ | ❌ *(not planned)* |
| Intent data / de-anon visitors | ❌ | ❌ | 🟡 | ✅ | ✅ | ❌ | ❌ *(out of scope, needs data co-op)* |
| Owned contact/firmographic DB | ❌ | ❌ | ✅ (150+ providers) | ✅ (500M contacts) | ✅ | ❌ | ❌ *(we never own data — by design)* |
| Call-recording ingestion (Gong) | ✅ | ✅ | ❌ | ❌ | 🟡 | ❌ | ❌ *(006 connector territory)* |
| **Private/CRM data merge** | 🟡 (CRM read) | 🟡 | ✅ | ✅ | ✅ | 🟡 | 🔷 **boundary-separated MCP merge** |
| Per-source extraction → synthesis | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🔶 **008 two-tier extract→synthesize** |
| "Since last run" / change diff | ✅ | ✅ (page diff) | ❌ | 🟡 | 🟡 | ✅ | 🔷 delta (002/004) → 🔶 008 provenance |

### B. Action / strategy / recommendations

| Capability | Klue | Crayon | Clay | ZoomInfo | 6sense | Kompyte | Sentinel |
|---|---|---|---|---|---|---|---|
| AI battlecards | ✅ | ✅ | ❌ | 🟡 | ❌ | ✅ | 🔷 Battlecard (structured, cited) |
| Account summary/brief | 🟡 | 🟡 | 🟡 | ✅ Copilot | ✅ | 🟡 | 🔷 AccountBrief (public+private) |
| **Structured recommended actions** | 🟡 | 🟡 | ❌ | ✅ next-best-action | ✅ NBA | ❌ | 🔶 **009 `action_plan{priority,timeline,rationale}`** |
| Objection handling | ✅ (FIA) | ✅ (Answers) | ❌ | 🟡 | ❌ | 🟡 | 🔶 **009 `objection_handling`** |
| Counter-positioning / "how to win" | ✅ | ✅ | ❌ | 🟡 | ❌ | ✅ | 🔷 `how_to_win` → 🔶 009 playbook-driven |
| Talking points / outreach copy | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 | ❌ *(we recommend; human acts — by design)* |
| **Editable strategy framework (no redeploy)** | ❌ | ❌ | 🟡 (user builds) | ❌ | ❌ | ❌ | 🔶 **009 Markdown playbooks — differentiator** |

### C. Prioritization / scoring / alerts

| Capability | Klue | Crayon | Clay | ZoomInfo | 6sense | Kompyte | Sentinel |
|---|---|---|---|---|---|---|---|
| Account/lead scoring | 🟡 threat | 🟡 importance | 🟡 user-built | ✅ Fit Score | ✅ predictive | 🟡 win-rate | 🔶 **010 weighted-signal score** |
| Ranked "who to focus on" list | 🟡 | 🟡 | 🟡 | ✅ | ✅ | ❌ | 🔶 **010 focus list** |
| **Explainable / cited score breakdown** | ❌ | ❌ | 🟡 | ❌ (black-box) | ❌ (black-box) | ❌ | 🔶 **010 deterministic, cited — differentiator** |
| Recency / time-decay weighting | 🟡 | 🟡 | 🟡 | ✅ | ✅ | 🟡 | 🔶 **010 half-life primitive** |
| Alerts / "what changed" | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🔷 delta only *(no push alerts yet)* |

### D. Delivery surfaces

| Surface | Klue | Crayon | Clay | ZoomInfo | 6sense | Kompyte | Sentinel |
|---|---|---|---|---|---|---|---|
| Dashboard / web app | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🔷 own dashboard |
| CRM embed (SFDC/HubSpot) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ *(006)* |
| Slack / Teams | ✅ | ✅ | ✅ | ✅ | 🟡 | ✅ | ❌ *(006)* |
| Browser extension | ✅ | 🟡 | ❌ | ✅ | ✅ | ✅ | ❌ *(not planned)* |
| **MCP / agent interop** | ✅ server | ❌ | ✅ | ✅ | ❌ | ❌ | 🔷 **MCP consumer (boundary-enforced)** |

### E. Deployment & data governance — **THE WEDGE**

| Property | Klue | Crayon | Clay | ZoomInfo | 6sense | Kompyte | **Sentinel** |
|---|---|---|---|---|---|---|---|
| **On-prem / self-host / VPC** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ **runs on customer GPUs** |
| **Data stays off third-party cloud LLMs** | ❌ (Claude/Azure/GPT) | ❓ undisclosed | ❌ (OpenAI/etc.) | ❌ (OpenAI/Claude) | ❓ undisclosed | ❓ ("GPT") | ✅ **vLLM/Gemma, structural** |
| EU / data-residency option | ❌ not advertised | ❓ | ❌ | ❌ US-only | ❌ | ❌ US-stored | ✅ **wherever you host it** |
| Provable no-egress (introspectable) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ **SENTINEL-005 introspection** |
| Public boundary-separation of private data | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ **SENTINEL-002 invariant** |
| SOC2 | ✅ | ✅ | ✅ | ✅ | ✅ | ❓ | n/a (self-hosted: customer's controls) |
| Documented GDPR exposure | — | — | — | ⚠ **yes** (EU data, class actions) | — | — | none (no data brokering) |

---

## 3. What this tells us (honest read)

**1. Our 009 + 010 features are table stakes, not novelty.** Every serious incumbent already ships
AI battlecards, account summaries, recommended/next-best actions, objection handling, and account scoring.
Building `action_plan` + `objection_handling` (009) and a focus list (010) makes Sentinel **credible** —
it does **not** make it special. We must build them to not look like a toy, but we should not pitch them as
the innovation.

**2. The only defensible differentiation is the combination no incumbent can copy quickly:**
   - **Sovereign** — runs entirely on the customer's own GPUs; data never touches a third-party cloud LLM,
     *provably* (introspection, not a promise). **0 of 6** competitors offer on-prem; **4 of 6** confirm or
     strongly imply customer data transits OpenAI/Anthropic/Azure.
   - **Explainable & cited** — deterministic priority scores with a cited breakdown, vs ZoomInfo/6sense
     black-box ML scores. A regulated buyer can audit *why* an account ranked high.
   - **Boundary-separated** — public vs private data structurally walled (SENTINEL-002); the action loop
     respects it. No competitor separates provenance this way.
   - **Editable strategy as data** — Markdown playbooks an admin edits without a redeploy (009). The
     incumbents' frameworks are vendor-baked.

**3. Where we deliberately lose, and must say so.** We will **never** match their *data scale* (ZoomInfo's
500M contacts, Clay's 150+ providers, 6sense's intent co-op) or their *delivery reach* (CRM embed, Slack,
extensions — that's 006). Chasing those is the red ocean. The pitch is **not** "a cheaper Klue" — it is
"the intelligence-to-action agent a bank/hospital/agency can legally run, that the others can't sell to them."

**4. Scope-validation for the build:**
   - **008 / 009 / 010 confirmed in scope** — they close the credibility gap to parity.
   - **Reframe the emphasis:** every increment's spec must foreground its *sovereign + explainable* angle
     (it's the differentiator), not the feature itself (which is parity). The per-increment sovereignty
     introspection test (NFR-3) is therefore a **demo asset**, not just a guardrail.
   - **Consciously NOT building** (record so it's not a silent gap): review mining, job/intent signals,
     owned contact DB, outreach-copy generation, CRM/Slack push, browser extension, alerts. The first four
     are red-ocean data plays; the last three are 006/connectors or product-surface bets for later.
   - **One gap worth reconsidering post-challenge:** "what changed" **push alerts** — all 6 have it, we only
     have a passive delta. Cheap to add on top of 008 provenance; candidate for a fast-follow.

---

## 4. One-line Business-Case framing (derived from this matrix)

> "Klue, Crayon, Clay, ZoomInfo, 6sense and Kompyte all generate battlecards, briefs, recommended actions
> and account scores — **in their cloud, through OpenAI/Anthropic, with your data leaving your walls.**
> Sentinel does the same intelligence-to-action loop **inside your perimeter, on your GPUs, with a provable
> zero-egress guarantee and a cited, auditable rationale for every recommendation.** It is the only one a
> regulated buyer can actually deploy."

---

## 5. Source agents

Six parallel research passes (2026-06-07) — Klue, Crayon, Clay/Claygent, ZoomInfo, 6sense+Kompyte. Raw
per-vendor inventories with citations are in the session transcript; key governance facts re-verified inline
in the matrix above. Re-run before the final pitch to catch vendor changes (this is a fast-moving field —
ZoomInfo shipped a native Claude connector on 2026-06-05, two days before this analysis).
