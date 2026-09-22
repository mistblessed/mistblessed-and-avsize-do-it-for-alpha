# Verification report

Recorded on 2026-09-22. This report separates
implemented behavior, actual local measurements, and unverified release gates.

## Automated checks

- **101 tests passed**, 0 failures,
  0 errors, 0 skips in the final run.
- Actual Redis integration executed against a dedicated loopback Docker Redis;
  cross-instance atomic creation, encryption, exact replay, and expiry passed.
- Actual local Natasha weights and an actual child process were exercised.
- Ruff and mypy passed. Native startup, readiness, synthetic mask/restore, and
  authenticated metrics were exercised over TCP, not only through ASGI tests.
- Compose configuration validates; the pinned uv image manifest exists.
- A full application Docker image build and Linux/Python 3.11 boot were **not
  verified**. The first build attempt stopped during environment preparation
  because drive C: ran out of space. Only project-generated caches were removed,
  and the disposable project environment was transparently compressed.

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

The external LLM API was **not called**: its endpoint/protocol details and
credentials were not supplied. The adapter is OpenAI-compatible and its HTTP
transport behavior is tested with a mock; this is not presented as a real-provider
demo. The current deployment is loopback-only, not a public checker URL.

## Remaining release gates

1. Curate and manually review at least 170 independent control examples, then
   run the quality gate without exposing them to the implementation model.
2. Confirm reference mask formatting and official scoring behavior with organizers.
3. Build and boot the Linux image on a machine with sufficient disk, configure the
   real provider, and demonstrate the complete live LLM chain.
4. Configure the actual checker peer allowlist / ingress and externally reachable
   URL; repeat a five-minute workload on that hardware with production logging.
5. Meet the throughput/latency target through measured HTTP/runtime tuning and,
   if needed, multiple API containers sharing Redis, with properly sized retention.

Source ZIP generation and archive/secret verification are performed after this
report is written. The project is implemented and locally exercised, but these
external and performance gates prevent claiming complete submission readiness.
