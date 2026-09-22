import asyncio
import json
import secrets

import httpx
import pytest

from alfa_pii.api.app import create_app
from alfa_pii.config import Consumer, Settings
from alfa_pii.detection.engine import Detector
from alfa_pii.domain import ServiceError
from alfa_pii.service import InlineEngine, ProtectionService
from alfa_pii.state.store import Cipher, MemoryStore


@pytest.fixture
def setup_service():
    cipher = Cipher(secrets.token_bytes(32))
    store = MemoryStore(cipher, ttl=60, tombstone_ttl=120)
    engine = InlineEngine(Detector(use_ner=False))
    service = ProtectionService(store, engine)
    return service, store


@pytest.fixture
def consumers():
    return {"a": Consumer(id="a"), "b": Consumer(id="b", demask=False)}


@pytest.fixture
def app(setup_service, consumers):
    service, _ = setup_service
    return create_app(Settings(_env_file=None), service=service, consumers=consumers,
                      credentials={"key-a": "a", "key-b": "b"})


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def process(client, payload, identifier="sample", key="key-a"):
    return await client.post("/process", json={"payload": payload, "payload_id": identifier},
                             headers={"Authorization": f"Bearer {key}"})


async def test_contract_replays_and_conflict(client):
    original = "Клиент: Иванов Иван Иванович; email: secret@example.org"
    forward = await process(client, original)
    assert forward.status_code == 200
    assert set(forward.json()) == {"result"}
    masked = forward.json()["result"]
    assert "Иванов" not in masked and "secret@example.org" not in masked
    assert (await process(client, original)).json() == {"result": masked}
    for _ in range(3):
        assert (await process(client, masked)).json() == {"result": original}
    assert (await process(client, "different content")).status_code == 409


async def test_concurrent_first_requests(client):
    responses = await asyncio.gather(*[process(client, "Email: private@example.org") for _ in range(12)])
    assert {r.status_code for r in responses} == {200}
    assert len({r.json()["result"] for r in responses}) == 1


async def test_consumer_isolation_and_authorization(client):
    masked = (await process(client, "Email: secret@example.org")).json()["result"]
    other = await process(client, masked, key="key-b")
    assert "secret@example.org" not in other.text
    forward = await process(client, "Email: second@example.org", identifier="b", key="key-b")
    assert (await process(client, forward.json()["result"], identifier="b", key="key-b")).status_code == 403
    assert (await process(client, "hello", key="unknown")).status_code == 401


async def test_no_pii_and_validation_do_not_echo_input(client):
    for _ in range(3):
        assert (await process(client, "Hello world")).json() == {"result": "Hello world"}
    response = await client.post("/process", json={"payload": {"secret": "LEAK_SENTINEL"}},
                                 headers={"Authorization": "Bearer key-a"})
    assert response.status_code == 422
    assert "LEAK_SENTINEL" not in response.text


async def test_no_default_public_access(client):
    response = await client.post("/process", json={"payload": "hello", "payload_id": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize("identifier", ["", "x" * 256, "line\nbreak"])
async def test_organizer_id_has_no_undocumented_format_constraint(client, identifier):
    assert (await process(client, "hello", identifier=identifier)).status_code == 200


async def test_state_failure_fails_closed(client, setup_service):
    _, store = setup_service
    store.available = False
    response = await process(client, "Email: secret@example.org")
    assert response.status_code == 503
    assert "secret@example.org" not in response.text


async def test_state_expiry_does_not_recreate_original(setup_service, consumers):
    service, store = setup_service
    await service.process("one", "Email: secret@example.org", consumers["a"])
    store.clock += 61
    with pytest.raises(ServiceError) as error:
        await service.process("one", "Email: secret@example.org", consumers["a"])
    assert error.value.status == 409


async def test_cipher_binding_and_plaintext_absence(setup_service, consumers):
    service, store = setup_service
    await service.process("one", "Email: LEAK_SENTINEL@example.org", consumers["a"])
    values = list(store.records.values())
    assert values and b"LEAK_SENTINEL" not in values[0][1]
    with pytest.raises(ServiceError):
        store.cipher.decrypt(values[0][1], "wrong-binding")


async def test_payloads_absent_from_logs(client, caplog):
    caplog.set_level("INFO", logger="alfa_pii")
    await process(client, "Email: LOG_SENTINEL@example.org", identifier="ID_SENTINEL")
    assert '"event": "process"' in caplog.text
    assert "LOG_SENTINEL" not in caplog.text
    assert "ID_SENTINEL" not in caplog.text


async def test_stage_logs_correlate_without_using_external_id(client, caplog):
    caplog.set_level("INFO", logger="alfa_pii")
    response = await process(client, "Email: trace@example.org", identifier="private-id")
    events = [json.loads(r.message) for r in caplog.records if r.name == "alfa_pii"]
    assert {e["event"] for e in events} >= {"protection", "process", "http"}
    assert all(e.get("trace") == response.headers.get("X-Request-ID") for e in events)
    assert response.headers.get("X-Request-ID")
    assert "private-id" not in caplog.text


async def test_proxy_masks_wire_data_and_restores_only_known_tokens(app, client):
    seen = []

    async def handler(request):
        seen.append(request.content.decode())
        body = __import__("json").loads(request.content)
        text = body["messages"][-1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": text + " new@example.org"}}]})

    from alfa_pii.llm import LLMClient
    transport = httpx.MockTransport(handler)
    llm = LLMClient("https://llm.invalid/v1", "test-only-key", "test-model", transport=transport)
    app.state.llm = llm
    response = await client.post("/v1/chat", json={"request_id": "chat-one", "message": "Email: original@example.org"},
                                 headers={"Authorization": "Bearer key-a"})
    await llm.close()
    assert response.status_code == 200
    assert "original@example.org" not in seen[0]
    assert "original@example.org" in response.json()["answer"]
    assert "new@example.org" not in response.json()["answer"]


async def test_disabled_consumer_checked_before_replay(client, consumers):
    forward = await process(client, "Email: secret@example.org")
    consumers["a"].enabled = False
    assert (await process(client, forward.json()["result"])).status_code == 403
