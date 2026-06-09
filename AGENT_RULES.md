# BiltIQ Engineering — AGENT_RULES.md

# Canonical rules for any AI coding IDE (Claude Code default; Cursor, Windsurf, others compatible).
# Drop this in repo root. IDE-specific config files (CLAUDE.md, .cursorrules, .windsurfrules) point to this file.

## Project context

Sentinel (Sovereign Intelligence Agent) is an autonomous research agent for regulated
startups and SMBs in BFSI, healthcare, and government. A single orchestrator runs two
modes — **competitor intelligence** and **client/account intelligence** — over a shared
MCP tool layer. Given a target (a competitor or an account), the agent decomposes the
request, gathers public signal via grounded web search, pulls private context from
connected internal tools (CRM, document store, calendar/email) through scoped MCP
connections, reasons across both, and writes a structured battlecard or account brief
back to the user's own workspace as a durable artifact — not a chat reply.

**The architectural thesis:** public and private data are handled by *separate tool
boundaries*. Public competitor research runs on Gemini grounding; private account data is
reached only through scoped, user-authorized MCP connections and never leaves those
boundaries. The orchestration is cloud-portable, but the inference layer is swappable —
Gemini/Vertex AI in this build, customer-controlled GPU serving (vLLM) behind an LLM
gateway in regulated production — so the same agent runs sovereign on-premise without
rework.

**Users:** analyst / sales / strategy teams at data-sensitive regulated SMBs.
**Deployment:** demo runs cloud-native on Cloud Run + Vertex AI; production target is
customer-controlled on-prem inference. Built by Aarna Tech Consultants Pvt. Ltd.
(BiltIQ AI) for the Google for Startups AI Agents Challenge — Track 1 (Build).

## Compliance

**Mode:** `cloud_ok`

- `on_prem_required` — strict. No external AI / cloud LLM calls in production code paths. Local inference only — vLLM, internal MCP, local embeddings. **Default for healthcare with NHA / DPDP-sensitive workloads, defence (iDEX, ADITI, DRISHTI), government B2G, BFSI with regulated data, or any client contract that mandates data sovereignty.** Auto-block on violation.
- `on_prem_preferred` — external AI calls allowed only with an ADR documenting why local inference doesn't work, what data crosses the boundary, what fallback exists, and what the rollback plan is. An adapter / wrapper module must isolate the cloud call. Default for most BiltIQ products.
- `cloud_ok` — cloud APIs allowed. Any new AI dependency still requires an ADR for cost and lock-in tracking. Default for internal dev tools, prototypes, and deployments where the client has explicitly approved cloud AI in writing.

If this section is missing or unset, agents must default to `on_prem_preferred` and surface the missing declaration.

**Healthcare project:** `false`

- `false` (default) — `_llm_client.medical()` calls are refused; the medgemma endpoint is unreachable from this repo. Generic medical knowledge questions still go to the standard chat endpoint.
- `true` — `_llm_client.medical()` calls permitted. Requires: documented data-handling policy in `SECURITY.md`, audit log for every medical call (`memory-stream.jsonl` event type `medical_inference`), no patient identifiers in prompts unless a per-call ADR justifies it.

Runtime gate: `_llm_client.medical()` checks the `BILTIQ_HEALTHCARE_PROJECT=1` environment variable. The AGENT_RULES.md field above is the canonical declaration; the env var is the runtime enforcement. Both must align.

**Specific external services explicitly allowed for this project:**

- **Google Gemini 2.x** (reasoning + grounded web search) — public-research tool boundary only. Used under Google for Startups AI Agents Challenge terms.
- **Vertex AI** — model serving in the demo/challenge environment.
- **Google Cloud Run** — agent runtime.
- **Agent Development Kit (ADK)** — orchestration / multi-step reasoning loop.
- **MCP connectors** (CRM, document store, email/calendar) — private-data boundary; reached **only** through user-authorized, scoped connections. No private data is transmitted outside these boundaries.

> Production-portable design: inference layer is swappable to vLLM on customer-controlled GPUs behind an LLM gateway, with **no public-cloud dependency in the private-data path**. Each external dependency above should be tracked by an ADR under `docs/adr/`.

## Stack

- Language: Python (3.11+)
- Agent framework: Google Agent Development Kit (ADK) — orchestration + multi-step reasoning loop
- Tool layer: Model Context Protocol (MCP) — public + private tool connectors
- LLM / reasoning: Gemini 2.x (via Vertex AI in demo); swappable to vLLM on customer GPUs in prod
- Grounded search: Gemini grounded web search (public-data boundary)
- Web framework: FastAPI (HTTP surface for the agent runtime) — TBD if a thin ADK web entrypoint suffices
- Runtime / container: Google Cloud Run (containerized)
- LLM gateway: abstraction over inference backend (Vertex ↔ vLLM) — to be built
- Database / state: TBD (session + artifact metadata) — likely Firestore (demo) / Postgres (on-prem)
- Object / artifact store: written back to user's own workspace via MCP (CRM / doc store)
- Vector store / cache / queue: TBD — add when retrieval or async fan-out is introduced

## Working pattern (mandatory)

Every implementation task follows the BiltIQ Attack Loop: **Think → Plan → Build → Review → Test → Ship → Reflect.** When asked to implement a task:

1. **Read first.** Open `/docs/specs/<task-id>/spec.md`, `design.md`, `plan.md`. If any are missing, stop and tell the dev. Read `/docs/architecture/stack.md` to know what wrappers and utilities exist before writing new code.
2. **One step at a time.** Implement the next atomic step from `plan.md`. Don't jump ahead.
3. **Code + tests + docs in same pass.** Generate all three before declaring the step done.
4. **Commit message format:** `<task-id>: <step description>` (e.g., `BILTIQ-123: add document upload endpoint`).
5. **No silent assumptions.** If `spec.md` is ambiguous, ask. Do not guess.
6. **Clean up after yourself.** If you create a test file, throwaway script, or experimental version, delete it before committing — no `*_v2.*`, `*_new.*`, `*_old.*`, `*.bak` files left behind.

## Anti-patterns — these are defects in BiltIQ code

The agent must actively avoid all 10. The dev must scan for them in Review.

The canonical list of the 10 anti-patterns — descriptions, detection signals, and per-language examples (Python, TypeScript / JavaScript, Java, C# / .NET, Go, Rust, C / C++, PHP, Ruby, Solidity) plus a blockchain-specific appendix — lives in **`/docs/architecture/anti-patterns.md`**. That file is the single source of truth; this section is a stub that points there.

Quick reference (full text in canonical):

1. **Duplication** — reuse existing utilities; check `stack.md` first.
2. **Abstraction Bypass** — use the project wrapper, not the raw library.
3. **Error Handling Gaps** — no catch-all handlers that swallow errors; decide explicitly.
4. **Type Safety Violations** — no escape-hatch types; no unjustified type-checker overrides.
5. **Security Anti-Patterns** — parameterized queries, no hardcoded secrets, validate at trust boundaries.
6. **Dead Code / Over-engineering** — build what `spec.md` requires.
7. **Debugging Residue** — no shadow-version files, debug prints, or commented-out code in committed PRs.
8. **Async Misuse** — no blocking I/O on event-loop / coroutine boundaries.
9. **Deprecated API Usage** — check `/docs/architecture/approved-versions.md`.
10. **Fake Test Coverage** — each test asserts one behavior tied to a spec criterion.
11. **HTML/MD boundary violation** — human-facing artifacts (`spec`, `design`, `plan`, `reflect`, reports, EOD summaries) must be `.html` files. Any of these delivered as `.md` under `docs/specs/` is auto-blocked in `code-reviewer` (same severity as #5 and #7). Agent-facing files (`SKILL.md`, `commands/*.md`, `MEMORY.md`, `AGENT_RULES.md`) remain Markdown.

## Code conventions

- **Type hints:** required on all public functions. Strict mode in CI.
- **Error handling:** all I/O, network, and external calls wrapped with explicit error handling. No bare `except`.
- **Logging:** use `logging` module. No `print()` in production code. Log at appropriate level (DEBUG verbose, INFO state changes, WARNING recoverable, ERROR failures).
- **Secrets:** never in code or config files. Read from env or secret manager.
- **PII:** never log PII. If unsure whether a field is PII, treat it as PII.
- **Docstrings:** Google style for Python; JSDoc for JS/TS.

## Banned vocabulary in any output (code comments, docs, commit messages)

The full banned-vocabulary list (with "why" + "say this instead" for each term) lives in **`/docs/architecture/anti-patterns.md` § Banned vocabulary**.

The list is canonical there. Locked terms include "cutting-edge", "revolutionary", "empowering", "seamless", "future-ready" plus an expanded set of consultant-speak and vendor-hype terms. Use plain, specific language — describe what the code does, not how impressive it is.

## Banned in product specs

- Cloud AI models listed as components (GPT-4, Claude Cloud API, Gemini in production paths) — unless the project's compliance mode is `cloud_ok` and an ADR documents the use.
- Unverified compliance claims (SOC 2, ISO 27001, HIPAA, GDPR, FedRAMP).
- Stock-photo style hyperbole.

## Architectural decisions

- Any new dependency requires an ADR before merge.
- Any schema change requires an ADR + migration plan.
- Any new external service integration requires an ADR + threat model note.
- Any cloud AI usage in `on_prem_preferred` mode requires an ADR.
- Any new AI dependency in any mode requires an ADR.

## Test rules

- Every public function: at least one unit test (happy path) AND at least one failure-path test.
- Every API endpoint: at least one integration test.
- Tests must run without network or hardware (mock vLLM, mock external services).
- For `on_prem_required` projects: include a test asserting no external AI API call is made.
- No more than 50% of dependencies mocked in any single test.

## When asked to generate documentation

- Use the `doc-generator` skill (in plugin `biltiq-engineering`).
- Update CHANGELOG.md, README.md, API docs, and ADRs as applicable in the same pass.
- No marketing language.

## When asked to review a plan

- Use the `plan-reviewer` skill.
- Output verdict: `approved` or `needs revision` with specific issues.

## When asked to review code

- Use the `code-reviewer` skill.
- Check the diff against `design.md` AND the 10 anti-patterns above.
- Output verdict and specific file:line issues.

## When asked to scan for anti-patterns

- Use the `anti-pattern-scanner` skill.
- For large scopes, dispatch the `biltiq-anti-pattern-auditor` subagent in parallel.
