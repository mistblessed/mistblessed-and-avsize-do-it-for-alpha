# Purpose
CPU-only detection and overlap resolution. No HTTP, credentials, or Redis here.

# Interfaces
Detector.detect(text) returns Entity values with original Python Unicode offsets
[start, end), kind, confidence, and source. resolve() selects non-overlapping
entities. Rules can extend categories with named value captures.

# Invariants
Never normalize the source string. Case-insensitive matching preserves positions.
Explicit context overrides public-person heuristics. Checksums supplement labeled
matches rather than rejecting all synthetic identifiers. A detector timeout fails
closed. Built-in rule spans fit within the 512-character overlap; custom rules
must respect that bound. Only known session markers are excluded by the caller;
user-supplied token-shaped strings are never a detection exemption.

# Verification
`uv run pytest tests/test_core.py tests/test_hardening.py -q`.
`uv run python tools/quality.py --corpus <reviewed.jsonl> --output <report.json>`.

# Current state
17 categories, Natasha PER/LOC support, typed contextual rules, two checksum
validators, labeled initials, street/house address forms, chunk overlap, and a
public-context heuristic. Free-text boundary and
context accuracy still needs human-reviewed independent evaluation. Avoid adding
example-specific name allowlists to improve a score.
