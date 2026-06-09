# Pull Request

**Task ID:** <!-- e.g., BILTIQ-123 -->
**Type:** <!-- feature | bug | refactor | spike | docs -->

## Problem
<!-- 1-3 sentences. What was wrong / what was missing? Link spec.md. -->

## Approach
<!-- 1-3 sentences. What did you do? Link design.md. -->

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual verification against acceptance criteria
- [ ] Lint + type check pass (strict mode)

<!-- Paste curl examples for backend changes, screenshots/video for UI changes -->

## Documentation
- [ ] `spec.md`, `design.md`, `plan.md` present in `/docs/specs/<task-id>/`
- [ ] `reflect.md` present (Step 7)
- [ ] ADR added if architectural decision was made
- [ ] CHANGELOG.md updated
- [ ] README.md updated if user-facing change
- [ ] API docs updated if API change

## Compliance
- [ ] `on-prem-compliance` skill verdict (or N/A): _____
- [ ] No external AI/cloud-LLM use that violates the declared compliance mode
- [ ] If external AI added, ADR is included or referenced

## Anti-pattern check
- [ ] No #5 (Security) findings
- [ ] No #7 (Debugging Residue) — no `*_v2.*`, `*_new.*`, `*_old.*`, `*.bak` files
- [ ] No banned vocabulary in code, comments, or commit messages

## Tech debt added
<!-- Anything cut to ship. Link the follow-up ticket. "None" is acceptable. -->

## Reviewer notes
<!-- Anything the reviewer should know — risky areas, things you weren't sure about. -->
