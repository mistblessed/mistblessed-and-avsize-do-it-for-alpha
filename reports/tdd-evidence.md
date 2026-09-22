# Tests-first evidence

Observed during implementation on 2026-09-22:

| Change | Before behavior implementation | After |
|---|---|---|
| Core detection/transformation contracts | 55 failures, 4 passes; tests collected normally | Core checks pass |
| Stale policy replay and permissive proxy policies | 3 failing hardening tests | Conflicts/rejection implemented |
| NER form heading false positive | One failing `test_form_heading_is_not_a_person` | Contextual heading rule passes |
| Token-shaped user input hiding a card | One failing `test_user_supplied_token_shape_is_not_a_detection_exemption` | Only known session tokens are trusted |
| Provider usage callback | Missing-interface failure in focused test | Provider token usage is reported separately |
| Organizer ID over-validation | Three failing cases (empty/long/newline ID) | No undocumented ID format restriction |
| Initials and standalone street/house addresses | Four failing common-form cases | Added bounded recognition rules |
| Correlated stage logs | One failing trace-correlation test | Context-local technical trace and response header |

API/state tests were authored before their implementation; not every initial
service RED result was separately captured. This report does not claim complete
historical TDD provenance for every line. The executable `tools/tdd.py` helper
was added for subsequent team/model work and records test hashes, JUnit results,
and command output between RED and GREEN. A peer must still review test meaning.

Final pass counts and commands are in verification.md. No score or independent
holdout result is inferred from these development regressions.
