# Purpose
Executable acceptance, regression, property, API, and integration checks.

# Workflow
Write behavior tests before production changes. Confirm meaningful RED, implement
GREEN, then refactor. Do not alter expected behavior just to accept a failure.
Synthetic data only; real customer data is prohibited in fixtures and reports.

# Verification
`uv run pytest -q` runs all tests; the real Redis case skips without TEST_REDIS_URL.
Use `uv run pytest -m ner` to check actual packaged Natasha weights.
Use `uv run pytest -m slow` for long input and a real child process.

# Independence
tools/make_corpus.py generates development examples only. Repeated casing and
prefix variants are not independent samples. Participant B must curate at least
10 unseen examples per category outside this repository and manually verify
labels. Never open that holdout in the implementation-model context. After error
disclosure, move that example into regression data and replace the private case.

# Reporting
Report skips and environment failures separately. Count actual passed checks;
never claim official mask scoring or the 1000-RPS SLA from unit tests.

