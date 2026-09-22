# Purpose
Mask selected intervals and restore exact authorized values. Detection and
authorization belong to callers.

# Interfaces
mask(text, entities, mode) returns MaskResult; restore(text, mapping) returns str.
layout_mask preserves string length, punctuation, and whitespace. typed_tokens
uses random 96-bit IDs with type prefixes, stable only within one request.

# Invariants
Reject overlaps and invalid offsets. Keep untouched text unchanged. Never use
global string replacement for layout restoration. Tokens from another mapping
remain unresolved. Restore in a single pass: a replacement containing another
token must not recursively expose its mapped value. Layout restoration accepts
only the exact stored masked text. Mappings are sensitive and must not be logged.

# Verification
`uv run pytest tests/test_core.py tests/test_hardening.py -q`.

# Current state
Both renderers, property tests over Unicode, exact layout restoration, and scoped
token restoration are implemented. Organizer reference mask format is unknown;
change the renderer independently if official examples become available.

