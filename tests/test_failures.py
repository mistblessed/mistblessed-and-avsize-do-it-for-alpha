import asyncio
import secrets

import httpx
import pytest

from alfa_pii import llm as llm_module
from alfa_pii.api.app import create_app
from alfa_pii.config import Consumer, Settings
from alfa_pii.detection.engine import Detector
from alfa_pii.domain import ServiceError
from alfa_pii.llm import LLMClient
from alfa_pii.service import InlineEngine, ProcessEngine, ProtectionService
from alfa_pii.state.store import Cipher, MemoryStore
from tools import demo


def test_demo_configures_utf8_output(monkeypatch):
    configured = []

    class Output:
        def reconfigure(self, **kwargs):
            configured.append(kwargs)

    monkeypatch.setattr(demo.sys, "stdout", Output())

    demo.configure_output()

    assert configured == [{"encoding": "utf-8"}]


def test_llm_tls_context_uses_system_trust_and_optional_ca(monkeypatch):
    contexts = []
    expected = object()

    def create_default_context(*, cafile=None):
        contexts.append(cafile)
        return expected

    monkeypatch.setattr(llm_module.ssl, "create_default_context", create_default_context)

    assert llm_module.build_tls_context("") is expected
    assert llm_module.build_tls_context("corporate-ca.pem") is expected
    assert contexts == [None, "corporate-ca.pem"]


@pytest.mark.parametrize("behavior,expected", [("timeout", 504), ("redirect", 502), ("invalid", 502), ("oversized", 502)])
async def test_upstream_failures_are_safe(behavior, expected):
    async def handler(request):
        if behavior == "timeout":
            raise httpx.ReadTimeout("PRIVATE_UPSTREAM_DETAIL")
        if behavior == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.invalid"})
        if behavior == "invalid":
            return httpx.Response(200, json={"PRIVATE_UPSTREAM_DETAIL": "not a completion"})
        return httpx.Response(200, content=b"PRIVATE_UPSTREAM_DETAIL" * 100)
    llm = LLMClient("https://llm.invalid/v1", "test-key", "test-model", max_response_bytes=128,
                    transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ServiceError) as error:
            await llm.complete("masked")
        assert error.value.status == expected
        assert "PRIVATE_UPSTREAM_DETAIL" not in str(error.value)
    finally:
        await llm.close()


async def test_provider_token_usage_is_reported_without_estimating():
    usage = []
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "safe"}}],
                                        "usage": {"prompt_tokens": 17, "completion_tokens": 3}})
    llm = LLMClient("https://llm.invalid/v1", "test-key", "test-model",
                    transport=httpx.MockTransport(handler), on_usage=lambda p, c: usage.append((p, c)))
    try:
        assert await llm.complete("masked") == "safe"
        assert usage == [(17, 3)]
    finally:
        await llm.close()


async def test_http_overload_has_retry_after():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    app = create_app(Settings(_env_file=None, request_capacity=1), service=service,
                     consumers={"a": Consumer(id="a")}, credentials={"key": "a"})
    app.state.active = 1
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/process", json={"payload": "hello", "payload_id": "x"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"


@pytest.mark.slow
async def test_timed_out_cpu_work_retains_capacity_until_completion():
    engine = ProcessEngine(1, 1, 1e-9, False, [])
    try:
        with pytest.raises(ServiceError) as error:
            await engine.protect("Email: synthetic@example.org", Consumer(id="a"), "typed_tokens")
        assert error.value.status == 503
        assert engine.pending == 1
        with pytest.raises(ServiceError) as overload:
            await engine.protect("another", Consumer(id="a"), "typed_tokens")
        assert overload.value.status == 429
    finally:
        await asyncio.to_thread(engine.close)
    await asyncio.sleep(0)
    assert engine.pending == 0


async def test_concurrent_different_content_is_not_a_cross_payload_restore():
    service = ProtectionService(MemoryStore(Cipher(secrets.token_bytes(32))), InlineEngine(Detector(False)))
    consumer = Consumer(id="a")
    results = await asyncio.gather(service.process("id", "Email: one@example.org", consumer),
                                   service.process("id", "Email: two@example.org", consumer), return_exceptions=True)
    assert sum(isinstance(result, str) for result in results) == 1
    assert any(isinstance(result, ServiceError) and result.status == 409 for result in results)
