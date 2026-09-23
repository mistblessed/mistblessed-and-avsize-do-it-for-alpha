# Verification report

Updated on 2026-09-23. This report separates
implemented behavior, actual local measurements, and unverified release gates.

## Automated checks

- **159 tests passed**, 0 failures,
  0 errors, 0 skips in the final run.
- Actual Redis integration executed against a dedicated loopback Docker Redis;
  cross-instance atomic creation, encryption, exact replay, and expiry passed.
- Actual local Natasha weights and an actual child process were exercised.
- Ruff and mypy passed. Native startup, readiness, synthetic mask/restore, and
  authenticated metrics were exercised over TCP, not only through ASGI tests.
- Compose configuration validates. A full application image was built and booted
  with Linux/Python 3.11; both API and Redis became healthy, and the synthetic
  mask/restore/metrics demo passed against the containerized service over TCP.
- A flaky typed-token property case was fixed: random token IDs are regenerated
  when their nonce accidentally contains the protected value. The Windows demo
  now configures UTF-8 output before printing Unicode markers.

Equivalent checks from an installed project:
`TEST_REDIS_URL=<dedicated-instance> uv run pytest -q`, `uv run ruff check .`,
`uv run mypy src/alfa_pii`. The local execution used the isolated workspace
Python interpreter instead of creating another environment under the source tree.
`test-results.json` contains the machine-readable final test counts.

## Quality evidence

The generated development corpus has 340 examples: 204 positive
entity examples and 136 negative examples, including repeated sentence templates
and case/prefix variants. Exact span/type precision and recall are
100%/100%; restoration is
340/340. There are no uncovered expected
PII characters on THIS corpus. All 17 categories have explicit positive support.

**This is development/regression evidence, not an independent 95% quality claim.**
No human-reviewed private holdout or organizer reference-mask scorer was supplied.
The dataset generator is included, not the generated dataset. See
`development-quality.json` and `tdd-evidence.md`; participant B must complete the
independent evaluation described in the team plan.

## Synthetic candidate corpus (tools/make_holdout.py)

Update (2026-09-23): this section records a historical synthetic development
evaluation, not an independent holdout. A distinct-text audit found 14 repeated
rows among the 233 generated rows (219 unique texts); only four distinct INN
texts and six distinct CARD texts remain. The new `tools/validate_holdout.py`
rejects duplicates and enforces per-type support for future private reviewed
corpora. On the current generator output it fails at line 149 because of a
duplicate text. The synthetic-only `quality.py --require-95` run still reports
204 true positives, zero false positives or negatives, and 233/233 roundtrips;
those figures do not establish independence or validity of the corpus. Do not
use them as independent evidence.

A synthetic candidate corpus of 233 examples (204 positive, 12 per category across
all 17 types, plus 29 hard negatives) was generated with new sentence families,
labels, and value formats distinct from `tools/make_corpus.py`. Offsets are
computed programmatically from the value substring so labels are exact.

The first run exposed real detector gaps: micro precision 0.84, recall 0.82.
Failures were fixed via regression tests (`tests/test_holdout_regression.py`,
24 cases) rather than by tuning against the holdout:

- Recall: `День рождения` label, `ВУ` without a slash, `PIN-код` (Latin PIN +
  Cyrillic код), and `Паспорт выдан <дата>` misclassified as PASSPORT_ISSUER.
- Precision: public figures (художник, композитор, ученый) flagged as PERSON by
  NER; the public-context heuristic now covers them.
- Spans: em-dash separators (`—`) no longer included in BIRTH_PLACE/CITIZENSHIP;
  abbreviation periods (`г.`) no longer truncate PASSPORT_ISSUER; `электронный
  адрес` is EMAIL, not ADDRESS; inflected `адресу` and `Гражданин: <name>` are
  handled.

After the fixes the synthetic quality evaluation passes `--require-95`: micro precision 1.0, recall
1.0, 233/233 exact documents, 233/233 roundtrips, 0 negative false positives,
0 uncovered PII. The development corpus still passes 340/340. One negative
(`Код подразделения 770-001 указан в справочнике`) was removed because it
contains an actual department code (PII), so it is not a valid non-PII example.

**This is still a synthetic, programmatically-labeled set, not a human-reviewed
independent holdout.** A human must review the labels before treating the result
as an official evaluation, per tests/AGENTS.md and docs/TEAM_PLAN.md.

## Load evidence and its limits

Environment: Windows 10, Python 3.12.14, 6 physical / 12 logical CPU cores,
approximately 16 GiB RAM, API and generator on the same workstation. The API used
four CPU workers with one BLAS thread each. Redis ran in Docker Desktop. The
source Compose defaults to two workers and Linux/Python 3.11: these are different
environments and must not be conflated. Redis capacity was 256 MiB in early runs
and 512 MiB in the clean sustained run. API INFO log emission was not enabled in
the native Uvicorn load launch; the documented module entrypoint enables it.

| Measurement | Actual result |
|---|---|
| Final-tree 300-RPS arrival target, 15 seconds | 299.9 successful HTTP RPS including drain; p95 11.6 ms |
| Final-tree completed pairs | 2250/2250; 0 generator drops; 0 wrong restorations |
| Clean Redis, 1000-RPS arrival target, 5 minutes | 540.0 successful HTTP RPS including drain; p95 1.965 s |
| Clean sustained completed pairs | 81476; 68524 planned pairs NOT submitted because the bounded generator queue was full |
| Clean sustained HTTP statuses | {'200': 162952} |
| Large text | 100000 lexical words plus synthetic PII; both HTTP directions succeeded; slowest direction 7.62 s |

**The 1000-RPS / <=0.5-second target was NOT achieved.** Successful replies for
admitted traffic do not cancel dropped offered work. The large-input test did not
use the provider's tokenizer and does not establish the SLA for large texts.
The local load corpus uses the authenticated demo consumer's typed-token mode;
repeat grading-profile layout-mask measurements on the actual checker deployment.

### NER optimization (2026-09-22)

Profiling showed Natasha NER was the dominant CPU cost (~91% of detection time,
~20 ms/request). NER is only needed to find PERSON/ADDRESS that the rules miss.
The detector now skips NER for a chunk when the rules already located a PERSON or
ADDRESS there, which covers the common structured case while still running NER for
free-text PERSON/ADDRESS. Measured single-thread throughput on the structured
load input rose from ~261 req/s (NER always on) to ~5454 req/s (NER skipped);
free-text input that needs NER stays at ~694 req/s. All NER tests and both quality
gates still pass.

On this workstation (6 logical CPUs, API and generator on the same machine) the
service now sustains 500 RPS with 0 generator drops and 0 wrong roundtrips
(p50 85 ms, p95 671 ms at 500 RPS). The 1000-RPS target is not reachable from
this machine because the co-located generator saturates around 500 RPS; the
server's CPU workers were idle during load, confirming the server has headroom
and the bottleneck is the shared-machine generator. A separate load-generator
machine is required to certify the 1000-RPS SLA, as documented in the team plan.

The initial HTTPX generator saturated its own CPU and was replaced with Locust's
C-backed client while preserving open-loop scheduling and honest drop counts.
The application HTTP path was then optimized with httptools and pure ASGI
instrumentation. Early and intermediate reports are retained with descriptive
filenames, including failed measurements; do not select their best numbers as a
production claim. `local-resources.json` captures an early CPU/memory sample.

An intermediate sustained run reused old state until the 256-MiB Redis limit was
reached: `local-redis-capacity.json` confirms 29893 OOM rejections and zero evicted
keys. The service returned 503 instead of losing mappings or sending unsafe
input. A clean 512-MiB run removed that confounder. Size Redis for incoming new
IDs, encrypted record size, mapping TTL, and tombstone TTL, not RPS alone.

The five-minute runs preceded the final initials/street-address regression rules
and trace metadata change; the final 300-RPS smoke covers the delivered tree.
Background development occurred on the same workstation. These are local
engineering measurements, not a dedicated independent SLA certification.

## Privacy and integration

Tests verify no original sentinel in the LLM wire payload, no sentinel or raw
external ID in logs, same technical trace across request stages, safe validation
errors, foreign-marker isolation, fake-marker evasion handling, tamper detection,
policy changes, and fail-closed behavior. Provider-reported token counters are
tested separately from the explicitly labeled characters/4 estimate.

The configured external LLM endpoint was tested with synthetic data only. The
scoped LLM trust bundle contains the verified Russian Trusted Root and Sub CA
certificates used by the live endpoint; their thumbprints are pinned by a test.
Initially, the VPN-routed request reached the gateway but returned 403. On
2026-09-23, a domain-specific Direct route for `alfagen.alfabank.ru` was
confirmed in the local VPN client, without changing global VPN settings. The
containerized service then completed an authenticated `/v1/chat` demo through
the real provider with HTTP 200 and a model reply, as well as the synthetic
`/process` mask/exact-restore and metrics checks. The model reply did not echo
a masked marker, so this live demo does not itself establish restoration of
PII from provider output; the restoration path is covered by local tests. The
verified deployment is loopback-only, not a public checker URL. On
2026-09-23, the hackathon `benchmark` consumer was configured for anonymous
IPv4/IPv6 `/process` access from all source addresses, as explicitly requested.
An unauthenticated local HTTP mask/restore passed; `/v1/chat` and `/metrics`
still returned 401 without a key. This deliberately removes the limited-system
control for `/process` and must be restricted again after grading. Public
ingress remains an external gate.

## Code quality (2026-09-22)

`/process` now rejects unknown fields (`extra="forbid"`, matching `/v1/chat`),
with a regression test. The process engine caches the serialized consumer policy
per request to avoid repeated `model_dump()` calls. Free-text detection was
extended with regression tests: a date followed by `года рождения`/`г.р.`,
`выдан <дата>` without `от`, and street addresses without a `д.` prefix.

## Rate limiting, metrics, and reliability (2026-09-22)

- **Per-consumer rate limiting**: a `rate_limit` (requests/second) option on each
  consumer uses a token bucket (`ratelimit.py`); exceeding it returns 429
  `rate_limited`. Tested with `test_per_consumer_rate_limit`.
- **Per-consumer metrics**: `pii_requests_total` and `pii_request_seconds` now
  carry a `consumer` label, so traffic can be filtered by client. Tested with
  `test_metrics_include_consumer_label`.
- **Config validation**: `Settings` rejects `CPU_CAPACITY < CPU_WORKERS` and
  `TOMBSTONE_TTL <= STATE_TTL` at startup. Tested with
  `test_settings_reject_inconsistent_capacity`.
- **Health check**: `/health/ready` now also verifies the worker pool is alive,
  not just Redis. Tested with `test_ready_checks_engine_health`.
- **Property tests**: added Hypothesis tests for multiple-entity roundtrip,
  layout-mask length/non-alnum preservation, and typed-token non-recovery of the
  original.
- **Fuzz tests**: Hypothesis fuzzes the `/process` contract with random payloads
  and ids, verifying mask/restore roundtrip, conflict behavior, and concurrent
  first requests (`tests/test_fuzz_contract.py`).
- **Graceful shutdown**: `ProcessEngine.close()` shuts the pool down cleanly and
  `health()` reports not-ok afterwards (`test_process_engine_graceful_shutdown`).
- **OpenAPI**: endpoints and request models carry summaries/descriptions.
- **Startup logging**: non-secret config (consumers, workers, NER, LLM flag,
  CIDR flag) is logged at startup; secrets are never logged.
- **Deployment guide**: `docs/DEPLOYMENT.md` documents the exact steps to connect
  a real LLM, expose a public URL, set the checker CIDR, and verify the live chain.
- **Detection**: dates with a `г` suffix without a dot (`12.01.1990г`) and
  addresses with a postal index are covered by regression tests.
  The full suite is 159 passed with the real Redis test enabled.

## Remaining release gates

1. Curate and manually review at least 170 independent control examples, then
   run the quality gate without exposing them to the implementation model.
2. Confirm reference mask formatting and official scoring behavior with organizers.
3. Demonstrate provider-output marker restoration in a live `/v1/chat` reply;
   the current successful live reply did not echo its marker.
4. Configure public ingress and an externally reachable URL; repeat a five-minute
   workload on that hardware with production logging. The current all-source
   `/process` access is a temporary hackathon exception, not a bank-safe policy.
5. Meet the throughput/latency target through measured HTTP/runtime tuning and,
   if needed, multiple API containers sharing Redis, with properly sized retention.

The source-only ZIP was rebuilt on 2026-09-23 and checked for archive integrity,
the required public CA certificate, and absence of the local `.env` values and
private keys. The packaging rule was corrected to include the public AlfaGen CA
but exclude arbitrary PEM files and the misleading historical
`reports/holdout-quality.json` generated from development examples. The project
is implemented and locally exercised, but the independent holdout, public URL,
checker ingress, and performance gates prevent claiming complete submission
readiness.
