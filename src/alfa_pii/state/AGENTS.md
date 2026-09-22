# Purpose
Shared encrypted correlation records and retention limits.

# Interfaces
Store.get(key), create_or_get(key, record), ping(). Production uses RedisStore;
MemoryStore is an injected test double only. Cipher binds ciphertext to a scoped
HMAC-derived record key. The caller includes consumer and endpoint in that scope.

# Invariants
Never store plaintext original fragments or raw external IDs in Redis. Write the
tombstone before the data inside the atomic Lua operation: partial OOM failure
must not publish a mask or permit recreation. Respond only after storing state.
Never evict active records. Missing state with a live tombstone produces 409.
Records expire after STATE_TTL; tombstones after TOMBSTONE_TTL. This is a finite
replay-protection window, not permanent idempotency.

# Verification
`TEST_REDIS_URL=redis://127.0.0.1:16379/0 uv run pytest -m redis` on POSIX.
The Redis test uses a unique namespace and removes only its own keys.

# Current state
Single Redis instance, atomic creation, encryption, cross-instance reads, and TTL
are tested. Redis loss invalidates mappings; no Redis persistence or HA claim.

