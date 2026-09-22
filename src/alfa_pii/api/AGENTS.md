# Purpose
HTTP contracts, authentication, safe errors, demo proxy, metrics, and lifecycle.

# Interfaces
/process accepts payload and payload_id, returns only result on success.
/v1/chat accepts request_id and message, returns request_id and answer.
/metrics needs authentication. Health endpoints expose no payloads.

# Invariants
Authorize every request, including retries. Resolve identity from Bearer keys or
the actual benchmark peer CIDR; do not trust forwarded headers. Validation errors
must not echo input. Restrict request body size before parsing JSON. Proxy calls
require full protection and typed tokens. Scan LLM output before restoring known
session values. HTTPX does not follow redirects or read ambient proxy settings.

# Verification
`uv run pytest tests/test_service.py tests/test_hardening.py -q`.
Use real Redis and the process engine for integration and load evidence.

# Current state
OpenAI-compatible non-streaming transport is implemented but external provider
compatibility requires its documentation and credentials. Do not replace missing
external connectivity with a mock while claiming a real LLM demo.

