"""Fuzz the /process contract: random payloads, ids, replays, and concurrency."""
import asyncio
import secrets

import httpx
from hypothesis import given, settings
from hypothesis import strategies as st

from alfa_pii.api.app import create_app
from alfa_pii.config import Consumer, Settings
from alfa_pii.detection.engine import Detector
from alfa_pii.service import InlineEngine, ProtectionService
from alfa_pii.state.store import Cipher, MemoryStore


def make_app():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    return create_app(Settings(_env_file=None), service=service,
                      consumers={"a": Consumer(id="a")}, credentials={"key": "a"})


@settings(max_examples=50, deadline=None)
@given(st.text(min_size=0, max_size=200), st.text(min_size=0, max_size=64))
async def test_fuzz_process_roundtrip(payload, payload_id):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url="http://test") as c:
        headers = {"Authorization": "Bearer key"}
        forward = await c.post("/process", json={"payload": payload, "payload_id": payload_id}, headers=headers)
        if forward.status_code != 200:
            # Empty payload or oversized should still be a defined error, not 500.
            assert forward.status_code in {200, 413, 422}
            return
        masked = forward.json()["result"]
        # Replay the original -> same mask.
        replay = await c.post("/process", json={"payload": payload, "payload_id": payload_id}, headers=headers)
        assert replay.status_code == 200
        assert replay.json()["result"] == masked
        # Restore the mask -> exact original.
        restored = await c.post("/process", json={"payload": masked, "payload_id": payload_id}, headers=headers)
        assert restored.status_code == 200
        assert restored.json()["result"] == payload


@settings(max_examples=20, deadline=None)
@given(st.text(min_size=1, max_size=100))
async def test_fuzz_process_conflict(payload):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url="http://test") as c:
        headers = {"Authorization": "Bearer key"}
        first = await c.post("/process", json={"payload": payload, "payload_id": "fixed-id"}, headers=headers)
        if first.status_code != 200:
            return
        masked = first.json()["result"]
        # A different payload with the same id must conflict (unless it equals the mask).
        other = payload + "X"
        if other == masked:
            return
        conflict = await c.post("/process", json={"payload": other, "payload_id": "fixed-id"}, headers=headers)
        assert conflict.status_code == 409


async def test_fuzz_concurrent_first_requests():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app()), base_url="http://test") as c:
        headers = {"Authorization": "Bearer key"}
        payload = "Email: fuzz@example.org"
        responses = await asyncio.gather(*[
            c.post("/process", json={"payload": payload, "payload_id": "conc-id"}, headers=headers)
            for _ in range(20)
        ])
        assert {r.status_code for r in responses} == {200}
        assert len({r.json()["result"] for r in responses}) == 1