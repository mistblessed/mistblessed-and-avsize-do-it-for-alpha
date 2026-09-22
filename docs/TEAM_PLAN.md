# Two-person 48-hour execution plan

## Objective and scoring
Build a working CPU-only proxy and pass the exact `/process` contract. Scoring:
detection/masking 6, restoration 3, context/variants 4, configuration 4,
performance 4, privacy/metrics 3, extras 3, demo 3 (30 total).
README is mandatory for configuration points. Prioritize the first 13 quality
points, then reliable integration and measured performance. A live endpoint and
a clean source ZIP are both mandatory. Production readiness is not required.

The original statement targets <=1s/1000 RPS; the scoring sheet prefers
<=0.5s/1000 RPS. The checker times out at 10s, retries twice, and stops after
five consecutive invalid requests. The exact reference-mask metric is missing.
Never invent an equivalence between our quality report and the official score.

## Ownership and handoffs
Participant A owns detection, contextual rules, overlap resolution, transforms,
quality fixtures, and profiling the core. Participant B owns API/auth, shared
state, LLM transport, deployment, metrics, load, and the private holdout.
Use separate Git branches and model conversations. Agree on domain.py interfaces
before parallel work. Integrate every four hours; neither participant silently
changes shared interfaces. Each reviews the other's acceptance tests.

| Hours | Participant A | Participant B | Exit condition |
|---|---|---|---|
| 0-2 | Requirements and 17-type examples | CPU/RAM, LLM protocol, checker network | Unknowns recorded |
| 2-6 | Core behavior tests | API/state tests and private dataset | Meaningful RED evidence |
| 6-18 | Detection, context, transforms | API, encrypted state, errors | Mask/restore pair works |
| 18-28 | Coverage and false positives | Real LLM proxy and accessible URL | Complete integration |
| 28-36 | Long text and profiling | Load, retries, worker sizing | Measured report |
| 36-42 | Independent evaluation | Bonuses, README, rehearsal | Scored demo ready |
| 42-48 | Cross-review and regression | Clean launch, ZIP, availability | Submission plus buffer |

## Tests-first discipline
For every bounded task: requirement -> test -> meaningful failure -> implementation
-> relevant green checks -> refactor. Collection/import failures are environment
problems, not successful RED evidence. Test expectations change only when the
second participant confirms the original expectation contradicts the specification.
Never resolve failures by skipping tests, disabling a detector, or lowering gates.

Keep the private holdout outside the implementation workspace. B authors at least
10 examples per category using new sentence families and manually reviewed spans,
including hard negatives. Neither the generated development corpus nor test cases
derived from visible prompts are independent. After disclosing a failing example,
move it into regression data and replace the unseen control example.

## Practical DeepSeek loop
Load root AGENTS.md, the target folder AGENTS.md, the shared interfaces, and only
the relevant tests. Give one bounded task from PROMPTS.md. Run commands yourself
if the coding environment cannot execute them; paste complete error output into
the same task. Keep the model from reading unrelated folders or dumping the whole
repository into context. At handoff update the local Current state paragraph and
write a five-line note: completed behavior, tests, interface changes, blockers,
and the next concrete task.

## Early decisions still needed on the actual hackathon infrastructure
- Verify the provider's API format; the supplied adapter assumes chat completions.
- Obtain the checker source IP or a supported authentication arrangement.
- Confirm CPU/RAM/disk, Python/Docker, and download access before selecting workers.
- Request reference masks/scoring code; isolate any required change in the renderer.
- Obtain the model tokenizer before claiming exact model-token volume or TPS.

## Demonstration
Use synthetic data only. In 1-2 minutes explain consumer -> identification ->
masking -> LLM -> reply scan -> authorized restoration. Show all types through
5-10 prepared samples, a public/private context contrast, and a formatting variant.
Then show a repeated request, denied restoration for the second consumer, safe
logs, and actual metrics. Demonstrate tokens, configurable modes, and conditional
PIN+card rules as three extras. Keep conditional protection off the real proxy.
Answer honestly about ambiguous classification and measured throughput.

## Release gate
No mandatory test failures, no skipped Redis test in the release evidence, no
secrets in ZIP, a reproducible README launch, compatible API, completed reviewed
holdout report, and a reachable checker URL. If an item is missing, record it as
incomplete rather than reporting the project as fully submission-ready.

