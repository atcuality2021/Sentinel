# /docs/DOCUMENTATION.md — Doc Index & Update Playbook

**Purpose:** The "where does X live?" map for this repo. Read this when you don't know where to put something or where to find something. Also the rules for keeping docs from drifting.

---

## Repo doc map

```
Repo root
├── README.md ........................... User-facing: what this repo is, how to install, quick start
├── CHANGELOG.md ........................ Every shipped change, in reverse chronological order
├── CLAUDE.md ........................... AI-IDE primary entry point (Claude Code reads this first)
├── AGENT_RULES.md ...................... Canonical agent rules — anti-patterns, conventions, compliance mode
├── MEMORY.md ........................... Living project state — current focus, gotchas
├── CHEATSHEET.md ....................... Daily printable cheatsheet
├── SECURITY.md ......................... Security policy & compliance posture
├── .cursorrules / .windsurfrules ....... IDE-specific adapters (point to AGENT_RULES.md)
├── .pre-commit-config.yaml ............. Local pre-commit gates (residue, banned vocab, bare-except)
│
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       └── biltiq-gates.yml ............ CI gates (anti-patterns, on-prem compliance, type strict)
│
├── docs/
│   ├── CONTEXT.md ...................... Company & product context (rare-change)
│   ├── GLOSSARY.md ..................... Domain vocabulary
│   ├── TESTING.md ...................... Testing strategy, the TDD loop, run commands, quality bar
│   ├── DOCUMENTATION.md ................ This file
│   │
│   ├── architecture/
│   │   ├── overview.md ................. System architecture for this repo
│   │   ├── stack.md .................... Libraries, wrappers, utilities (read before coding)
│   │   ├── approved-versions.md ........ Current vs deprecated APIs (Anti-Pattern #9 defense)
│   │   └── sop-onboarding.md ........... New-dev SOP
│   │
│   ├── adr/
│   │   ├── _template.md
│   │   └── NNNN-title.md ............... One file per architectural decision
│   │
│   ├── specs/
│   │   ├── _template/ .................. spec.html, design.html, plan.html, reflect.html scaffolds
│   │   └── <task-id>/
│   │       ├── spec.html ............... What & why (acceptance criteria)
│   │       ├── design.html ............. How, with alternatives + files-to-touch
│   │       ├── plan.html ............... Atomic implementation steps + test cases per step
│   │       └── reflect.html ............ Post-task reflection (metrics, what-went-wrong)
│   │
│   └── memory-archive/
│       └── YYYY-MM.md .................. Archived entries from MEMORY.md
│
└── tests/ .............................. Test code (mirrors source structure)
```

Skills, slash commands, and subagents live in the `biltiq-engineering` Claude Code plugin, not in this repo.

**Artifact format convention (AP #11):** human-facing artifacts under `docs/specs/` (`spec`, `design`, `plan`, `reflect`) are **HTML** with embedded inline CSS — they render styled in any browser without a build step. Agent-facing files (`SKILL.md`, `commands/*.md`, `MEMORY.md`, `AGENT_RULES.md`) stay Markdown. Delivering a spec/design/plan/reflect as `.md` is auto-blocked in `code-reviewer`. Test cases live in `plan.html` (per-step `Tests:` blocks + global Test Strategy table) — not in `spec` (which has acceptance criteria) or `design` (which has API contracts).

---

## "Where does X go?" — quick lookup

| You want to... | Put it in... |
|---|---|
| Document a new architectural decision | `/docs/adr/NNNN-title.md` |
| Describe what a new feature does for users | `README.md` (high-level) + spec.md (detailed) |
| List a new utility/wrapper available | `/docs/architecture/stack.md` |
| Note an API that's now deprecated | `/docs/architecture/approved-versions.md` |
| Define a new internal term | `/docs/GLOSSARY.md` |
| Understand how/where to write tests | `/docs/TESTING.md` |
| Document a system-level constraint or quirk | `MEMORY.md` (if recent) → `/docs/architecture/overview.md` (if permanent) |
| Capture a "we tried this and it didn't work" lesson | `MEMORY.md` (Known issues section) |
| Add a new agent skill | `biltiq-engineering` plugin's `skills/` (not this repo) |
| Document a one-time runbook for an operation | `/docs/RUNBOOK.md` (create if not present) |
| Note a security or compliance rule | `SECURITY.md` and `AGENT_RULES.md` § Compliance |
| Update what BiltIQ is/does | `/docs/CONTEXT.md` (rare; needs Harish approval) |

---

## Doc lifecycle

Stale docs are worse than missing docs because they actively mislead.

### When a doc is created
- Add it to this index.
- Reference it from where it's relevant.
- The author owns it for the first 30 days.

### When a doc must be updated
- API doc: when API surface changes (same PR).
- README: when user-visible behavior changes (same PR).
- CHANGELOG: every PR.
- ADR: never updated after `accepted`. To change a decision, write a new ADR that supersedes it.
- `architecture/overview.md`: whenever the answer to "how does this system work?" materially changes.
- `architecture/stack.md`: whenever a new utility/wrapper is added or an old one is deprecated.
- `approved-versions.md`: whenever a dependency is upgraded across a major version, or an API method is deprecated upstream.
- `MEMORY.md`: end of every meaningful session (`memory-curator` skill).
- `GLOSSARY.md`: when a new term gets used 2+ times in PRs or chats.

### When a doc must be retired
- Doc no longer reflects reality and won't be updated → move to `/docs/archive/` with a forwarding note.

### Audit cadence
- **Friday architecture review (weekly):** walk through ADRs created that week.
- **Monthly:** scan `/docs/architecture/` for docs untouched in >90 days but covering active code areas. Flag stale.

---

## What goes in CHANGELOG.md

One line per shipped change. Format: `- <type>: <description> (<task-id>)`. Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `breaking`. Group by version. Use `## [Unreleased]` for in-progress changes.

---

## What goes in README.md

User-facing only. Keep it focused:
1. **What this is** (2-3 sentences).
2. **Who it's for.**
3. **Install / quick start.**
4. **Architecture diagram link** (to `/docs/architecture/overview.md`).
5. **Where to go for more** (link to this DOCUMENTATION.md).

What does NOT go in README:
- Internal team conventions (those live in `AGENT_RULES.md`).
- Project state (lives in `MEMORY.md`).
- Architecture deep-dive (lives in `/docs/architecture/`).

---

## What goes in CHANGELOG vs MEMORY vs ADR — the common confusion

These three all touch "what happened":
- **CHANGELOG.md** — what *shipped* to users (every PR adds an entry).
- **MEMORY.md** — what's *currently happening* and what we *learned* (gotchas, in-flight work, recent decisions in summary form).
- **ADR** — *why* we chose what we chose (one file per decision, written once, never updated).

If you're confused about which to update: ship-related → CHANGELOG; context-for-next-session → MEMORY; decision-with-tradeoffs → ADR.

---

## Doc generation by AI-IDE

The `doc-generator` skill in the `biltiq-engineering` plugin handles auto-generation in the same pass as code:
- Inline doc comments / docstrings
- CHANGELOG entries
- README updates
- API doc (OpenAPI/Swagger)
- ADRs (when a non-trivial decision was made)

It does **not** auto-update `CONTEXT.md`, `GLOSSARY.md`, this `DOCUMENTATION.md`, or `architecture/sop-onboarding.md`. Those require human edits via PR.
