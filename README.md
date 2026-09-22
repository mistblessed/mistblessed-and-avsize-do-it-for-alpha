# AlfaGen PII Protection

A CPU-only Python protection module with the organizer's `/process` contract,
exact restoration, per-consumer policies, an authenticated LLM proxy, encrypted
Redis state, and executable evidence. **This is a hackathon implementation, not a
certification of banking compliance or a demonstrated 1000-RPS deployment.**

Start with [the team plan](docs/TEAM_PLAN.md), [DeepSeek prompts](docs/PROMPTS.md),
and [verification evidence](reports/verification.md). Documentation and code are
English; short folder-level `AGENTS.md` files provide model context.

## Quick start

Requirements: Docker with Compose, or Python 3.11/3.12 and a reachable Redis.
Dependencies and packaged Natasha weights are pinned in `uv.lock`; downloads are
needed at build/install time, never during request processing.

```sh
python tools/bootstrap.py
# Edit .env locally: LLM connection and exact checker source CIDRs.
docker compose up --build -d
curl http://127.0.0.1:8000/health/ready
uv sync --frozen
uv run python tools/demo.py
uv run python tools/demo.py --chat
```

`bootstrap.py` generates credentials without printing or overwriting them.
The final command requires a real, configured OpenAI-compatible LLM endpoint.
Empty LLM settings leave `/process` available but make `/v1/chat` return 503.
Native alternative: start Redis, set `REDIS_URL` and `REDIS_PASSWORD` correctly,
run `uv sync --frozen`, then `uv run python -m alfa_pii` from this directory.
The module binds port 8000; use a firewall or bind Uvicorn explicitly to loopback
when running outside Docker. Compose publishes to loopback by default.

## Configuration in five sentences

1. Generate `.env` with `python tools/bootstrap.py` and set Redis and LLM connection values locally.
2. Edit `config/consumers.yaml` to enable consumers and choose `detect_types`, `mask_types`, `mask_enabled`, `demask`, `mode`, and `combinations`.
3. Put each enabled consumer's credential in the environment variable named by its `key_env`; never put keys in YAML.
4. Set `BENCHMARK_CIDRS` to the checker's verified peer addresses and configure the published host/port without trusting forwarded headers.
5. Restart the service to apply settings, check `/health/ready`, and run the demo and tests before using the new policy.

The default consumers are `benchmark`, `demo`, `no-restore`, and `conditional`.
The first accepts only allowlisted peers, the others require their Bearer keys.
An empty allowlist grants no anonymous access. `/metrics` always needs a key.
Never allow all addresses just to make the grader connect; agree on network
access or a trusted ingress with source-IP enforcement. Uvicorn forwarded-header
parsing is disabled. TLS must be terminated by the approved deployment ingress;
the local Compose setup is HTTP on loopback.

## Organizer contract

```http
POST /process
Content-Type: application/json

{"payload":"Клиент: Иванов Иван Иванович; Email: demo@example.org", "payload_id":"unique-id"}
```

Success is exactly `{"result":"..."}`. Send that result back with the same ID to
restore the original. Authorized clients may use `Authorization: Bearer ...`;
the checker need not add headers if its peer address is allowlisted.

| Input for an existing ID | Behavior |
|---|---|
| Same original | Same stored mask |
| Same mask | Exact original, if restoration remains allowed |
| Other content | 409 conflict |
| Original equals mask because no data was selected | Unchanged text on every retry |
| Expired record with a live tombstone | 409 expired |
| Changed effective policy | 409 policy changed; use a fresh ID |

State is scoped by consumer and endpoint. A changed restoration permission is
checked immediately. Redis is shared across API processes; responses are not
released before atomic state storage. Retention defaults to 30 minutes plus
24-hour ID tombstones; after the tombstone expires the ID can be reused.
Redis has no eviction, AOF, or RDB persistence in Compose. A Redis restart loses
mappings and tombstones: restart an evaluation run with fresh IDs. No Redis HA or
permanent exactly-once guarantee is claimed.

Errors use `{"error":"stable_code"}` without echoing input: 401/403 for access,
409 for conflicts/expiry, 413 for size, 422 for malformed input, 429 with
`Retry-After` for overload, and 503 for unavailable protection/storage.

## Detection and mask policies

All 17 categories are represented: `PERSON`, `BIRTH_DATE`, `BIRTH_PLACE`,
`PASSPORT`, `CITIZENSHIP`, `PASSPORT_ISSUER`, `DEPARTMENT_CODE`, `ISSUE_DATE`,
`DRIVER_LICENSE`, `ADDRESS`, `EMAIL`, `PHONE`, `INN`, `CARD`, `CVV`, `PIN`,
`CARDHOLDER`. Contextual rules supplement local Natasha NER. Case-insensitive
matching does not change source offsets. Checksums provide extra evidence.

`layout_mask` replaces letters/digits inside selected values with `*`, retaining
punctuation and whitespace. **This is an assumption, not an official reference
mask.** `typed_tokens` uses opaque 96-bit markers and retains identity within a
request. Restoration is one-pass and cannot resolve another session's markers.

Add an `extra_rules` entry with `kind` and a regex containing a named `value`
capture; add that kind to the consumer's detection and masking sets. Custom rules
are trusted administrator configuration, have a match timeout, and should match
spans shorter than the 512-character chunk overlap. For example:

```yaml
extra_rules:
  - kind: EMPLOYEE_ID
    pattern: 'Employee: (?P<value>EMP-\d{5})'
```

`combinations: {PIN: [PIN, CARD]}` demonstrates the optional contextual mode on
`/process`. Do not use it as the normal safety policy: the default masks an
explicit PIN without requiring a card. Rule or model failure blocks processing.

## LLM proxy

```http
POST /v1/chat
Authorization: Bearer <local consumer credential>
Content-Type: application/json

{"request_id":"unique-chat-id", "message":"Summarize this synthetic customer record: ..."}
```

Response: `{"request_id":"unique-chat-id","answer":"..."}`.
The proxy uses typed tokens even if the consumer selects layout masking for
`/process`, because changed model output cannot be restored by original offsets.
It rejects disabled/partial protection and conditional unmasking configurations.
Newly detected data in the model reply is masked before authorized original
values are restored. Unknown or damaged markers are left unresolved.

Set `LLM_BASE_URL` to the API base including `/v1` where applicable,
`LLM_MODEL` to the provider's actual model name, and `LLM_API_KEY` locally.
The only implemented wire protocol is non-streaming OpenAI-compatible chat
completions. HTTPS is required unless an explicitly approved local HTTP endpoint
is configured. Redirects and ambient proxy settings are disabled. Chat retries
reuse mappings but may call the model again; exactly-once LLM billing is not
promised. No raw PII is intentionally sent to the model, but detector accuracy
still requires independent evaluation.

## Tests, quality, and load

```sh
uv run pytest -q
TEST_REDIS_URL=redis://127.0.0.1:16379/0 uv run pytest -m redis -q
uv run ruff check .
uv run mypy src/alfa_pii
uv run python tools/make_corpus.py --output /tmp/development.jsonl
uv run python tools/quality.py --corpus /tmp/development.jsonl --output reports/development-quality.json --require-95
uv run python tools/quality.py --corpus /secure/reviewed-holdout.jsonl --output reports/holdout-quality.json --require-95
uv run python tools/load.py --rps 1000 --seconds 300 --output reports/load-1000.json
uv run python tools/load.py --rps 20 --seconds 30 --long-every 10 --output reports/load-mixed.json
```

On PowerShell set `$env:TEST_REDIS_URL = 'redis://127.0.0.1:16379/0'` separately.
Create a disposable local test instance, if needed:
`docker run -d --name alfa-pii-test-redis -p 127.0.0.1:16379:6379 redis:7.4-alpine redis-server --save '' --appendonly no`.
Use a dedicated Redis for tests: each integration test cleans only its random
namespace. An unset test URL skips the real Redis test and must be reported.
The native process-pool test and NER test exercise real implementations.

The 340 generated examples are DEVELOPMENT data: 20 per category, with repeated
negative templates and no independent human review. Participant B must supply
at least 170 genuinely unseen, manually reviewed control examples using the
same JSONL schema. `quality.py` reports exact span/type metrics, document leakage,
negative false positives, and exact roundtrips; it does not implement the unknown
organizer's span-based edit-distance score. `--require-95` also requires no
uncovered expected PII, exact restoration, and at least five expected positive
entities per category (`--minimum-support`) on the supplied corpus.

`load.py` schedules arrivals independently of completion and reports generator
lag, dropped pairs, retries, actual successful throughput, and latency including
failures. It uses Locust's C-backed FastHttpSession and waits for readiness and
an authenticated warmup before measurement. Measure 100/300/600/1000 RPS first;
attempt 2000 only with capacity.
Use a separate load-generator machine for an SLA claim. `tools/locustfile.py`
is an interactive closed-loop alternative, not evidence of offered arrival rate.

## Observability and privacy

Structured application logs contain only stages, types, counts/timings, and
random technical traces; access logs and upstream HTTP debug logs are disabled
by the module entrypoint. All stage events share the generated `X-Request-ID`
response-header trace, never the raw correlation ID supplied by the caller.
Never enable request-body middleware in deployment.
Prometheus counters/histograms expose RPS through `rate(pii_requests_total[1m])`,
latency through `pii_request_seconds`, and processing volume through
`pii_characters_total` and `pii_estimated_tokens_total`. Estimated tokens are
characters/4, explicitly not DeepSeek tokenizer counts. When the provider returns
valid usage metadata, `pii_llm_tokens_total{direction="input|output"}` records its
actual reported counts; `pii_llm_usage_responses_total` distinguishes that evidence
from missing metadata. Labels exclude user IDs and arbitrary paths.

AES-GCM encrypts stored records with associated scoped keys. HMAC fingerprints
avoid raw IDs and unkeyed hashes of predictable data. PII necessarily exists in
process memory during detection/restoration; do not claim secure memory erasure.

## Limits and next steps

Context, free-text address boundaries, unusual documents, and ambiguous dates
need a larger independently annotated corpus. Address components are detected
as candidates but are not exposed as a separate public address schema. A maximum
input of two million Unicode characters / 8 MiB supports the tested large text,
but the 100,000-token check currently uses lexical tokens, not the provider's
unavailable tokenizer. Do not generalize short-request load results to large
texts. Bounds, process count, and timeouts must fit the deployment CPU/RAM.

Full container-build evidence, real LLM connectivity, and public checker access
are separately reported in `reports/verification.md`. After the hackathon:
calibrate context on reviewed data, obtain the official mask scorer, add provider
tokenization, confirm infrastructure sizing, and design Redis HA/key rotation.

## Source-only ZIP

```sh
uv run python tools/package.py --output ../alfa-pii-source.zip
```

The packager uses an explicit file allowlist and excludes `.env`, dependencies,
caches, model binaries, and large files. Review reports before submission. A ZIP
and a live externally reachable checker URL are both required by the onboarding.
