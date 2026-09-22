# Project
Python CPU-only PII protection proxy for AlfaGen. Cover all 17 required types.

# Invariants
- POST /process: {payload, payload_id} -> {result}.
- Original-input retries return the same mask; mask retries restore exact text.
- Never select direction by request count.
- Scope state and restoration by authenticated consumer and endpoint.
- Fail closed before LLM calls when protection or storage fails.
- Never log payloads, mappings, credentials, raw IDs, or original PII.
- Secrets come from .env; commit only .env.example.
- Preserve source offsets, whitespace, punctuation, and Unicode.

# Workflow
Read this file, the target folder AGENTS.md, and relevant tests.
Write and run failing behavior tests before changing behavior.
Implement, verify, then refactor; do not weaken tests or invent results.
Report commands, failures, behavior changes, and unresolved risks.
Update local context when interfaces or behavior change.

# Ownership
A: detection, policies, transformations, quality.
B: API, state, auth, LLM transport, metrics, deployment.

# Verification
`uv run pytest`; set TEST_REDIS_URL for the real Redis test.
`uv run ruff check .`; `uv run mypy src/alfa_pii`.
Read README.md for quality/load commands and reports/verification.md for evidence.

# Limits
Use synthetic fixtures only. Generated development fixtures are not an independent
holdout. Organizer mask scoring is unspecified; local metrics are not official.
Production uses Redis + process workers + Natasha; test doubles are never selected
by production configuration. External LLM access and external deployment require
user-supplied environment configuration. See docs/TEAM_PLAN.md and docs/PROMPTS.md.

