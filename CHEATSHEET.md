# BiltIQ Engineering — Daily Cheatsheet

**Print this. Pin it.**

## Every task — 7 steps:

```
1. THINK    →  /biltiq-engineering:think <id>     Read task. Read existing code. Confirm AC. No existing utility? Then design new.
2. PLAN     →  /biltiq-engineering:plan <id>      Write spec.md + design.md + plan.md. plan-reviewer skill.
3. BUILD    →  /biltiq-engineering:build <id>     Implement next step. Code + tests + docs same pass. Commit per atomic step.
4. REVIEW   →  /biltiq-engineering:review <id>    code-reviewer skill on staged diff. Block on #5/#7.
5. TEST     →  /biltiq-engineering:test <id>      Tests pass. Lint + strict type check. Acceptance criteria checked manually.
6. SHIP     →  /biltiq-engineering:ship <id>      PR using template. CHANGELOG. ADR if applicable.
7. REFLECT  →  /biltiq-engineering:reflect <id>   reflect.md. No close without it.
```

Or invoke the `attack-loop-orchestrator` skill to drive all 7.

## Every day — 3 rituals:

| Time   | What                                                    | Command |
|--------|---------------------------------------------------------|---------|
| 09:30  | Standup post in Slack: yesterday / today / blockers     | `/biltiq-engineering:standup` |
| 17:30  | EOD post in Slack: shipped / WIP / tomorrow / debt      | `/biltiq-engineering:eod` |
| Friday | Architecture review live, 30 min, 17:00 IST             | — |

## The 10 anti-patterns — scan your diff for these every Review

1. **Duplication** — Did I check what already exists? Is there a utility 3 dirs away?
2. **Abstraction Bypass** — Am I using the raw library when we have a wrapper?
3. **Error Handling Gaps** — Bare `except`? Missing `finally`? Swallowed errors?
4. **Type Safety Violations** — Any `any` / untyped returns? Strict mode on?
5. **Security Anti-Patterns** — SQL interpolation? Hardcoded secrets? Missing input validation?
6. **Dead Code / Over-engineering** — Unused imports? Abstractions for one caller? Config for constants?
7. **Debugging Residue** — Any `*_v2.py`, `*_new.py`, `*_old.py`, `*.bak` left behind?
8. **Async Misuse** — Blocking call inside `async def`? Missing `await`?
9. **Deprecated APIs** — `datetime.utcnow()`? `pkg_resources`? React class components? Check approved-versions.md.
10. **Fake Test Coverage** — Tests assert intent or just AI's assumptions? Over-mocked?

## Hard rules — don't break these

1. **No code before spec + plan.** This is the rule that prevents vibe coding.
2. **One task in progress at a time.** Context switching destroys velocity and quality.
3. **Code + tests + docs in the same AI-IDE pass.** Not three separate efforts.
4. **Honor the compliance mode** declared in AGENT_RULES.md § Compliance.
5. **No task closes without `reflect.md`.** The learning loop is mandatory.
6. **Every PR has all 8 mandatory artifacts.** Missing artifacts = auto-reject.

## The 8 mandatory artifacts per task

1. spec.md
2. design.md
3. plan.md
4. Code (with inline doc comments)
5. Tests (unit + integration)
6. ADR (if non-trivial decision)
7. PR using template
8. reflect.md

## When stuck

1. Re-read the spec. Most "stuck" is unclear scope.
2. Drop a question in `#engineering` Slack with the task ID.
3. Tag @harish for architectural calls, @bijendra/@anil for implementation, @sam for process.
4. After 30 min stuck → drop the task, move to a different one, come back fresh.
