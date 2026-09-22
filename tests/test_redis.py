import asyncio
import os
import secrets

import pytest
from redis.asyncio import Redis

from alfa_pii.config import Consumer
from alfa_pii.detection.engine import Detector
from alfa_pii.domain import ServiceError
from alfa_pii.service import InlineEngine, ProtectionService
from alfa_pii.state.store import Cipher, RedisStore


@pytest.mark.redis
async def test_real_redis_cross_instance_atomicity_expiry_and_encryption():
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL not provided; real Redis test was NOT executed")
    client = Redis.from_url(url)
    prefix = "test:" + secrets.token_hex(12)
    cipher = Cipher(secrets.token_bytes(32))
    stores = [RedisStore(client, cipher, prefix, ttl=1, tombstone_ttl=30) for _ in range(2)]
    services = [ProtectionService(s, InlineEngine(Detector(False))) for s in stores]
    consumer = Consumer(id="test", mode="typed_tokens")
    original = "Email: REDIS_SENTINEL@example.org"
    try:
        answers = await asyncio.gather(*[services[i % 2].process("id", original, consumer) for i in range(12)])
        assert len(set(answers)) == 1
        assert await services[1].process("id", answers[0], consumer) == original
        for key in await client.keys(prefix + "*"):
            assert b"REDIS_SENTINEL" not in (await client.get(key) or b"")
        await asyncio.sleep(1.1)
        with pytest.raises(ServiceError) as error:
            await services[0].process("id", original, consumer)
        assert error.value.status == 409
    finally:
        keys = await client.keys(prefix + "*")
        if keys:
            await client.delete(*keys)
        await client.aclose()

