# /docs/TESTING.md — Testing Strategy & Conventions

**Purpose:** How testing works in this repo — the loop, the layout, the quality bar, and how to run it. Read this before writing a test, and before opening a PR that adds behavior. The discipline here is enforced by the `biltiq-engineering` plugin (the `test-driven-development`, `test-generator`, and `verification-before-completion` skills) and by CI (`.github/workflows/biltiq-gates.yml`).

---

## The core rule: test first

Every implementation step in the Attack Loop's **Build** phase follows **RED → GREEN → REFACTOR**. The point is not ceremony — it is that a test written *before* the code forces you to state the contract, and watching it fail before it passes proves the test actually exercises the code.

### RED — write a failing test first
- Write the test before the implementation exists.
- The test asserts what the `spec.html` **acceptance criterion** requires, not what the code happens to do.
- Name it `test_<unit>_<scenario>_<expected>` — e.g. `test_upload_pdf_with_no_text_returns_extraction_error`.
- Tie it to a specific acceptance criterion in a docstring/comment: `"""Covers AC2: PDF without extractable text returns extraction_error."""`.
- **Run it. It must fail.** If it passes, the test is vacuous — fix the test before continuing.

### GREEN — minimum code to pass
- Write the smallest code that makes the test pass. Nothing unrelated.
- Do not add error handling for cases no test covers. Do not add abstractions for a single caller.
- **Run it. It must pass.** Quote the actual output (`1 passed in 0.04s`) — never claim "passes" without seeing green (the `verification-before-completion` skill).

### REFACTOR — only if the code earned it
- With the test green, look again: factor out duplication, rename anything misleading.
- **Do not add new behavior in REFACTOR.** Tests must still pass unmodified.
- If the code is already simple, REFACTOR is a no-op. That is fine.

---

## When to use TDD — and when not

| Use TDD | Skip TDD (use characterization tests instead) |
|---|---|
| Every new public function or method | Pure refactors with no behavior change |
| Every bug fix (the failing repro test **is** RED) | Documentation-only changes |
| Every Build step of a feature | Tooling / CI / config changes with no testable behavior |

For a bug fix, the failing test that reproduces the bug is Phase 1. Do not fix before you can reproduce (the `systematic-debugging` skill).

---

## Per-language frameworks & run commands

Starter scaffolds for your language live under `test-scaffolds/<lang>/` (dropped in by `biltiq-init`). Copy one into your `tests/` tree as a starting point, then delete the scaffold.

| Language | Framework | Run with |
|---|---|---|
| Python | `pytest` (+ `pytest-asyncio` for async) | `pytest -q` |
| TypeScript / JavaScript | Vitest / Jest | `vitest run` / `npm test` |
| Go | stdlib `testing` | `go test ./...` |
| Rust | stdlib `testing` | `cargo test` |
| Java | JUnit 5 | `mvn test` / `gradle test` |
| C# | xUnit / NUnit | `dotnet test` |
| Ruby | RSpec | `bundle exec rspec` |
| PHP | PHPUnit | `vendor/bin/phpunit` |
| Kotlin | JUnit 5 | `gradle test` |
| Swift | XCTest | `swift test` |
| Solidity | Foundry | `forge test` |

Always quote the test count when reporting (`277 passed`) so the claim is verifiable.

---

## Test layout

```
Repo root
└── tests/ ............................ Test code — mirrors source structure
    ├── fixtures/ ..................... Static test data (sample inputs, recorded payloads)
    └── <module>/test_<unit>.py ....... One test module per source module
```

- `tests/` **mirrors** the source tree, so the test for `src/billing/invoice.py` lives at `tests/billing/test_invoice.py`.
- Static inputs (sample JSON, recorded payloads, log lines) go in `tests/fixtures/` — never inline a 200-line blob in a test.
- Test cases are **specified** in `plan.html` (per-step `Tests:` blocks + the global Test Strategy table) and **implemented** in `tests/`. The `spec.html` holds acceptance criteria; `design.html` holds API contracts — neither holds test code.

---

## Test quality rules

These are the bar a test must clear. CI and `code-reviewer` enforce several of them.

- **One assertion per test.** Multi-assert tests hide which assertion failed.
- **Each test ties to a `spec.html` acceptance criterion** — name the AC in a docstring/comment.
- **No more than 50% of dependencies mocked** in any single test. A test that mocks everything tests nothing.
- **No snapshot tests of the agent's / system's own output.** That is a tautology, not a test.
- **Tests run with no network and no hardware.** Mock external services; use `tests/fixtures/`.
- **A failure-path test is required**, not just the happy path. The exception branch is where bugs hide (Anti-Pattern #3).
- **Do not delete an inconvenient test.** Fix the test or fix the code — never suppress.

---

## Compliance mode and tests

Check this repo's compliance mode in `AGENT_RULES.md`:

- **`on_prem_required`** — include a test asserting that **no external AI / cloud LLM call fires** during a representative request. This is a hard gate: a feature that reaches a cloud endpoint in this mode is a release blocker.
- **`on_prem_preferred`** — an external call is allowed only behind an ADR; a test should pin which path is taken.
- **`cloud_ok`** — no test restriction, but a new AI dependency still needs an ADR.

---

## What testing defends against (the anti-patterns)

Writing the test first is the cheapest defense against three of the ten anti-patterns:

- **#10 Fake Test Coverage** — tests written *after* code assert "this is what the code does," not "this is what the spec requires." TDD inverts the order.
- **#3 Error Handling Gaps** — RED-first forces the failure-path test, so exception branches are not shipped as stubs.
- **#6 Dead Code / Over-engineering** — the test is the only consumer; you build exactly what it requires and no more.

---

## How tests run in CI

`.github/workflows/biltiq-gates.yml` runs the suite on every PR alongside the anti-pattern scan, the compliance gate, and the type-strict check. A PR is not mergeable until the suite is green. Locally, `.pre-commit-config.yaml` catches residue files, banned vocabulary, and bare-except before you ever push.

---

## Reporting tests back to the dev

When you finish a unit of work, report:

```
TDD cycle for <task-id> step N — <step description>

RED:    test_<name> failed as expected: <quoted error>
GREEN:  test_<name> passed (1 passed in 0.04s)
REFACTOR: <what was tightened, or "no refactor needed">

Acceptance criterion covered: AC2 (<criterion text>)
Failure-path test for this step: test_<name>_<failure-mode>
Mocking ratio: <e.g. 30%>
```
