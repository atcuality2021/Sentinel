# Security Policy

## Reporting a vulnerability

Email security@biltiq.ai with details. Do not file a public issue.

## Compliance posture

This repo's compliance mode is declared in `AGENT_RULES.md` § Compliance. Modes:

- `on_prem_required` — strict; no external AI/cloud LLM in production paths.
- `on_prem_preferred` — external AI allowed only with an ADR documenting the exception.
- `cloud_ok` — external AI allowed; ADR still required for any new dependency.

## Secrets

- No secrets in source. Read from environment or secret manager.
- No PII in logs. If unsure, treat as PII.
- Rotate any credential leaked into git history immediately.

## Auth & authz

- All API endpoints require auth unless explicitly marked public.
- All authz checks happen at the entry point, not deep in the call stack.
