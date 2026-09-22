# Requirement-to-test matrix

Source documents: the user-supplied AlfaGen task, ds.pdf onboarding (9 pages),
and scoring criteria (4 pages). No source PDF is redistributed in this package.

| Requirement | Implementation | Executable evidence |
|---|---|---|
| All 17 types and original offsets | detection/engine.py | test_required_category_offsets (three case variants) |
| Public names/branch addresses | contextual suppression | test_public_and_non_personal_text; real NER test |
| Text dates, separators, reordered dates | bounded contextual rules | core category fixtures |
| Exact layout and token restoration | transformation/masking.py | Unicode property test; exact roundtrip |
| No recursive/foreign token expansion | one-pass scoped lookup | test_no_recursive_token_restoration; scoped tokens test |
| Exact process JSON schema | api/app.py | test_contract_replays_and_conflict |
| Retries and concurrent first request | content fingerprints + atomic state | service replay/concurrency tests; real Redis test |
| Shared state across processes | RedisStore | test_real_redis_cross_instance_atomicity_expiry_and_encryption |
| Authorized restoration, disabled consumer | per-request consumer policy | isolation and disabled-consumer tests |
| Policy changes | stored effective policy comparison | test_policy_change_cannot_replay_old_weaker_mask |
| State expiry and integrity | TTL/tombstones; AEAD binding | expiry and cipher tests |
| Fail closed on unavailable Redis | fixed safe 503 | test_state_failure_fails_closed |
| Real proxy transport behavior | LLMClient | mock HTTP wire-body inspection; real provider demo remains external |
| New reply data protected | reply scan before restoration | test_proxy_masks_wire_data_and_restores_only_known_tokens |
| No public default access | keys and actual peer CIDRs | allowlist/forwarded-header test |
| Safe validation and bounded input | model validation; ASGI body bound | test_validation_size_limit_and_metrics |
| No PII logs | fixed structured metadata | test_payloads_absent_from_logs with logging enabled |
| CPU work outside event loop | bounded ProcessPoolExecutor | test_real_process_pool |
| Long text/chunk edges | block processing with overlap | large lexical-token test; boundary tests |
| Extend rules without core edits | YAML extra_rules | test_conditional_policy_and_custom_rule |
| Modes/conditional bonus | consumer policies | policy test and demo consumers |
| Metrics and load evidence | Prometheus; tools/load.py | metrics test; saved load JSON |
| README and source-only ZIP | README; tools/package.py | package inspection and clean-launch procedure |

## Assumptions and non-equivalences
- Default star masks are not established official reference masks.
- Provider protocol is assumed OpenAI-compatible until confirmed with a real call.
- A 100000-word/lexical-token example is not a verified 100000-DeepSeek-token input.
- Estimated TPS is characters/4, explicitly labeled as an estimate.
- Generated 340-case development data is not independent and has repeated negatives.
- Single Redis instance and bounded tombstones do not promise HA or indefinite replay safety.
- Linux/Python 3.11 is the Docker target; local verification used Windows/Python 3.12.

