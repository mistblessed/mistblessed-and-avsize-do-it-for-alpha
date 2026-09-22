import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Awaitable, Protocol, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from redis.asyncio import Redis
from redis.exceptions import RedisError

from alfa_pii.domain import ServiceError


class Cipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AES-256 key required")
        self.aead = AESGCM(key)
        self.mac_key = hmac.digest(key, b"alfa-pii/fingerprint/v1", "sha256")

    def fingerprint(self, value: str) -> str:
        return hmac.new(self.mac_key, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def encrypt(self, record: dict[str, Any], binding: str) -> bytes:
        nonce = secrets.token_bytes(12)
        raw = json.dumps(record, ensure_ascii=True, separators=(",", ":")).encode()
        return nonce + self.aead.encrypt(nonce, raw, binding.encode())

    def decrypt(self, value: bytes, binding: str) -> dict[str, Any]:
        try:
            return json.loads(self.aead.decrypt(value[:12], value[12:], binding.encode()))
        except (InvalidTag, ValueError, TypeError) as exc:
            raise ServiceError(503, "state_integrity_failure") from exc


class Store(Protocol):
    cipher: Cipher
    async def get(self, key: str) -> dict[str, Any] | None: ...
    async def create_or_get(self, key: str, record: dict[str, Any]) -> dict[str, Any]: ...
    async def ping(self) -> None: ...


# Single Redis instance: a script atomically reads or writes both related keys.
# AOF/RDB are disabled in the supplied deployment; no eviction of active records.
GET = """
local value = redis.call('GET', KEYS[1])
if value then return value end
if redis.call('EXISTS', KEYS[2]) == 1 then return 'EXPIRED' end
return false
"""
CREATE = """
local value = redis.call('GET', KEYS[1])
if value then return value end
if redis.call('EXISTS', KEYS[2]) == 1 then return 'EXPIRED' end
redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return ARGV[1]
"""


class RedisStore:
    def __init__(self, client: Redis, cipher: Cipher, namespace: str,
                 ttl: int = 1800, tombstone_ttl: int = 86400) -> None:
        self.client, self.cipher, self.namespace = client, cipher, namespace
        self.ttl, self.tombstone_ttl = ttl, max(ttl + 1, tombstone_ttl)

    def keys(self, key: str) -> list[str]:
        base = f"{self.namespace}:{{{key}}}"
        return [base + ":data", base + ":seen"]

    async def ping(self) -> None:
        try:
            await self.client.ping()
        except RedisError as exc:
            raise ServiceError(503, "state_unavailable") from exc

    async def _call(self, script: str, key: str, *args: Any) -> dict[str, Any] | None:
        try:
            raw = await cast(Awaitable[Any], self.client.eval(script, 2, *self.keys(key), *args))
        except RedisError as exc:
            raise ServiceError(503, "state_unavailable") from exc
        if raw == b"EXPIRED":
            raise ServiceError(409, "state_expired")
        return self.cipher.decrypt(raw, key) if raw else None

    async def get(self, key: str) -> dict[str, Any] | None:
        return await self._call(GET, key)

    async def create_or_get(self, key: str, record: dict[str, Any]) -> dict[str, Any]:
        result = await self._call(CREATE, key, self.cipher.encrypt(record, key), self.ttl, self.tombstone_ttl)
        if result is None:
            raise ServiceError(503, "state_write_failed")
        return result


class MemoryStore:
    """Test-only implementation. Production startup always constructs RedisStore."""
    def __init__(self, cipher: Cipher, ttl: int = 1800, tombstone_ttl: int = 86400) -> None:
        self.cipher, self.ttl, self.tombstone_ttl = cipher, ttl, tombstone_ttl
        self.clock = 0.0
        self.available = True
        self.records: dict[str, tuple[float, bytes]] = {}
        self.seen: dict[str, float] = {}

    async def ping(self) -> None:
        if not self.available:
            raise ServiceError(503, "state_unavailable")

    async def get(self, key: str) -> dict[str, Any] | None:
        await self.ping()
        now = time.monotonic() + self.clock
        item = self.records.get(key)
        if item and item[0] > now:
            return self.cipher.decrypt(item[1], key)
        if self.seen.get(key, 0) > now:
            raise ServiceError(409, "state_expired")
        return None

    async def create_or_get(self, key: str, record: dict[str, Any]) -> dict[str, Any]:
        current = await self.get(key)
        if current is not None:
            return current
        now = time.monotonic() + self.clock
        self.records[key] = (now + self.ttl, self.cipher.encrypt(record, key))
        self.seen[key] = now + self.tombstone_ttl
        return record
