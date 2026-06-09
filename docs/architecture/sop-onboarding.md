# SOP — New Developer Onboarding

**Audience:** Engineer joining this repo on Day 1.
**Time to first commit:** ~half a day.
**Maintainer:** [PROJECT: @owner]

---

## Day 0 — before your first session

1. Install the `biltiq-engineering` Claude Code plugin from the internal marketplace. Verify by opening a session in this repo — the SessionStart hook should inject the BiltIQ bootstrap (you'll see `<EXTREMELY_IMPORTANT>` block at top of context).
2. Install pre-commit hooks: `pre-commit install`.
3. Read the BiltIQ Engineering Process v1.2 doc (in the team drive). One time. End-to-end.
4. Print `CHEATSHEET.md`. Pin it.

## Day 1 — read order

In this exact order:

1. `AGENT_RULES.md` — what the agent (and you) must / must not do. Note the **compliance mode** of this repo.
2. `MEMORY.md` — what's currently happening, what was recently decided, the gotchas list.
3. `/docs/CONTEXT.md` — what BiltIQ is, what this product does. (You can skim if you've read it for another repo.)
4. `/docs/GLOSSARY.md` — vocabulary. ATC product names, infra terms.
5. `/docs/architecture/overview.md` — what runs in this repo, the data flow, the failure modes.
6. `/docs/architecture/stack.md` — **important.** What wrappers exist. You will be told to use them.
7. `/docs/architecture/approved-versions.md` — what is deprecated.
8. `README.md` — quick start (install, run tests, run dev server).

## Day 1 — environment

- Clone the repo and `cd` in.
- Run the project's setup command (see `README.md` Quick start).
- Run the test suite and confirm a clean baseline:
  ```
  pytest -q
  ruff check .
  mypy --strict .
  ```
- All three must pass before you start coding. If any fail, **stop and ask** — the baseline is broken and that is not a "your task" problem.

## Day 1 — first task

- Pick a `good-first-issue` from the sprint board.
- Run `/biltiq-engineering:new-task <task-id>` to scaffold the spec/design/plan/reflect files.
- Walk through `/biltiq-engineering:think → /biltiq-engineering:plan → ...` for the full Attack Loop. Get someone to peer-review your `plan.md` before Build.
- Announce yourself in `#engineering` Slack with the task ID — that's your standup, day 1.

## The 3 conversations every new dev has on Day 1

1. **With @harish (or architecture owner)** — "what's the most important thing for this product right now, and how does my work plug in?"
2. **With your engineering lead** (Bijendra or Anil) — "what do I need to know about the *people* working in this codebase that isn't in MEMORY.md?"
3. **With Sam (process auditor)** — "where do you see Day-1 devs trip up most often?"

## Tools

- **Slack:** `#engineering` (everyone), `#engineering-process` (process discussions), `#oncall` (incidents).
- **Tracker:** [PROJECT: Linear / Jira / GitHub Issues link].
- **Wiki:** [PROJECT: Notion / Confluence link].
- **Repo browser:** GitHub (or GitLab).
- **AI-IDE:** Claude Code (default), Cursor, Windsurf — same `AGENT_RULES.md` works in all three.

## Working hours & rituals

- **09:30 IST** — standup post in Slack (use `/biltiq-engineering:standup` to generate the template).
- **17:30 IST** — EOD post in Slack (use `/biltiq-engineering:eod`).
- **Friday 17:00 IST** — architecture review (live, 30 min).

Async-first; live calls only when blocked or for the Friday review.

## When you get stuck

In order:
1. Re-read the spec.
2. Drop a question in `#engineering` Slack with the task ID.
3. Tag @harish for architecture, @bijendra/@anil for implementation, @sam for process.
4. After 30 min stuck → switch tasks, come back fresh.

## What "done" looks like

- All 8 mandatory artifacts present (spec, design, plan, code, tests, ADR if applicable, PR, reflect).
- CI green on the PR.
- Reviewer approved.
- Merged.
- `MEMORY.md` updated (`memory-curator` skill).
- Worktree removed.
- You filed a `reflect.md` honestly — including what you missed.

That's it. Welcome.
