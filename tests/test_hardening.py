import asyncio
import secrets

import httpx
import pytest

from alfa_pii.api.app import create_app
from alfa_pii.config import Consumer, Settings
from alfa_pii.detection.engine import Detector, resolve
from alfa_pii.domain import Entity, Kind, ServiceError
from alfa_pii.service import InlineEngine, ProcessEngine, ProtectionService, protect
from alfa_pii.state.store import Cipher, MemoryStore
from alfa_pii.transformation.masking import restore


def test_specific_types_win_over_generic_nested_entities():
    spans = [Entity(Kind.PERSON, 0, 8, source="ner"), Entity(Kind.CARDHOLDER, 0, 12),
             Entity(Kind.PASSPORT, 15, 26), Entity(Kind.PHONE, 15, 26)]
    assert [e.kind for e in resolve(spans)] == [Kind.CARDHOLDER, Kind.PASSPORT]


def test_conditional_policy_and_custom_rule():
    detector = Detector(False, [{"kind": "EMPLOYEE_ID", "pattern": r"Employee: (?P<value>EMP-\d{5})"}])
    policy = Consumer(id="test", combinations={"PIN": {"PIN", "CARD"}},
                      detect_types={str(k) for k in Kind} | {"EMPLOYEE_ID"},
                      mask_types={str(k) for k in Kind} | {"EMPLOYEE_ID"})
    assert protect(detector, "PIN: 4321", policy, "layout_mask").text == "PIN: 4321"
    text = "PIN: 4321; карта: 4111 1111 1111 1111; Employee: EMP-12345"
    result = protect(detector, text, policy, "layout_mask")
    assert "4321" not in result.text and "EMP-12345" not in result.text


def test_no_recursive_token_restoration():
    first = "⟦PERSON:" + "a" * 24 + "⟧"
    second = "⟦PERSON:" + "b" * 24 + "⟧"
    from alfa_pii.domain import MaskResult
    mapping = MaskResult(first, tokens={first: second, second: "secret"})
    assert restore(first, mapping) == second


def test_user_supplied_token_shape_is_not_a_detection_exemption():
    text = "⟦PERSON:4111111111111111aaaaaaaa⟧"
    result = protect(Detector(False), text, Consumer(id="untrusted"), "typed_tokens")
    assert "4111111111111111" not in result.text


def test_chunk_boundary_preserves_complete_entity():
    value = "person@example.org"
    for offset in [4090, 4095, 4096, 4598, 8190]:
        text = " " * offset + value + " " * 600
        entities = resolve(Detector(False).detect(text))
        assert [(e.start, e.end) for e in entities] == [(offset, offset + len(value))]


@pytest.mark.slow
def test_large_text_with_100000_lexical_tokens():
    text = "слово " * 100_000 + " Email: large@example.org"
    result = protect(Detector(False), text, Consumer(id="large"), "layout_mask")
    assert "large@example.org" not in result.text
    assert restore(result.text, result) == text


@pytest.mark.ner
def test_real_ner_person_and_public_context():
    detector = Detector(True)
    text = "Алексей Сидоров обратился за кредитом."
    spans = resolve(detector.detect(text))
    assert any(e.kind == Kind.PERSON and text[e.start:e.end] == "Алексей Сидоров" for e in spans)
    assert not detector.detect("Поэт Александр Пушкин написал стихотворение.")


@pytest.mark.ner
def test_form_heading_is_not_a_person():
    text = "Анкета. Дата рождения: 23 февраля 1987 года;"
    assert all(text[e.start:e.end] != "Анкета" for e in Detector(True).detect(text))


@pytest.mark.slow
async def test_real_process_pool():
    engine = ProcessEngine(1, 2, 20, False, [])
    try:
        result = await engine.protect("Email: worker@example.org", Consumer(id="worker"), "typed_tokens")
        assert "worker@example.org" not in result.text
    finally:
        await asyncio.to_thread(engine.close)


async def test_policy_change_cannot_replay_old_weaker_mask():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    consumer = Consumer(id="a", mask_types={"EMAIL"})
    await service.process("id", "Email: old@example.org; PIN: 1234", consumer)
    consumer.mask_types.add("PIN")
    with pytest.raises(ServiceError) as error:
        await service.process("id", "Email: old@example.org; PIN: 1234", consumer)
    assert error.value.status == 409


async def test_benchmark_allowlist_uses_actual_peer_not_forwarded_header():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None, benchmark_cidrs="192.0.2.1/32"), service=service,
                     consumers={"benchmark": Consumer(id="benchmark")})
    for peer, expected in [("192.0.2.1", 200), ("192.0.2.2", 401)]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 123)), base_url="http://test") as c:
            response = await c.post("/process", json={"payload": "hello", "payload_id": "id"},
                                    headers={"X-Forwarded-For": "192.0.2.1"})
            assert response.status_code == expected


async def test_validation_size_limit_and_metrics():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None, max_body_bytes=1024), service=service,
                     consumers={"a": Consumer(id="a")}, credentials={"key": "a"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        oversized = await c.post("/process", content="x" * 1025)
        assert oversized.status_code == 413
        malformed = await c.post("/process", content='{"payload":"SENTINEL"')
        assert malformed.status_code == 422 and "SENTINEL" not in malformed.text
        assert (await c.get("/metrics")).status_code == 401
        metrics = await c.get("/metrics", headers={"Authorization": "Bearer key"})
        assert metrics.status_code == 200
        assert "pii_request_seconds" in metrics.text
        assert "pii_estimated_tokens_total" in metrics.text


async def test_per_consumer_rate_limit():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None), service=service,
                     consumers={"a": Consumer(id="a", rate_limit=2)}, credentials={"key": "a"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        first = await c.post("/process", json={"payload": "hello", "payload_id": "1"},
                             headers={"Authorization": "Bearer key"})
        second = await c.post("/process", json={"payload": "hello", "payload_id": "2"},
                              headers={"Authorization": "Bearer key"})
        third = await c.post("/process", json={"payload": "hello", "payload_id": "3"},
                             headers={"Authorization": "Bearer key"})
        assert first.status_code == 200 and second.status_code == 200
        assert third.status_code == 429
        assert third.json() == {"error": "rate_limited"}


async def test_metrics_include_consumer_label():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None), service=service,
                     consumers={"a": Consumer(id="a")}, credentials={"key": "a"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/process", json={"payload": "hello", "payload_id": "1"},
                     headers={"Authorization": "Bearer key"})
        metrics = await c.get("/metrics", headers={"Authorization": "Bearer key"})
        assert metrics.status_code == 200
        assert 'consumer="a"' in metrics.text


def test_settings_reject_inconsistent_capacity():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cpu_workers=8, cpu_capacity=4)


async def test_ready_checks_engine_health():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None), service=service,
                     consumers={"a": Consumer(id="a")}, credentials={"key": "a"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/health/ready")).status_code == 200


@pytest.mark.slow
async def test_process_engine_graceful_shutdown():
    engine = ProcessEngine(1, 2, 20, False, [])
    try:
        result = await engine.protect("Email: shutdown@example.org", Consumer(id="a"), "typed_tokens")
        assert "shutdown@example.org" not in result.text
        assert engine.health()["ok"] is True
    finally:
        await asyncio.to_thread(engine.close)
    assert engine.health()["ok"] is False


@pytest.mark.parametrize("options", [{"mask_types": set(), "detect_types": set()},
                                       {"combinations": {"PIN": {"PIN", "CARD"}}}])
async def test_chat_cannot_forward_intentionally_unprotected_policy(options):
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None), service=service, consumers={"a": Consumer(id="a", **options)}, credentials={"key": "a"})
    app.state.llm = object()  # Must be rejected before any LLM transport is reached.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/v1/chat", json={"request_id": "id", "message": "PIN: 1234"}, headers={"Authorization": "Bearer key"})
        assert response.status_code == 403
