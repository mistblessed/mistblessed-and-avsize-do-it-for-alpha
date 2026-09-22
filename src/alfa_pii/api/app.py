import asyncio
import hmac
import ipaddress
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis
from starlette.types import ASGIApp, Receive, Scope, Send

from alfa_pii.config import Consumer, Settings, load_policies
from alfa_pii.domain import Kind, MaskResult, ServiceError
from alfa_pii.llm import LLMClient
from alfa_pii.observability import trace_id
from alfa_pii.service import ProcessEngine, ProtectionService
from alfa_pii.state.store import Cipher, RedisStore
from alfa_pii.transformation.masking import restore

log = logging.getLogger("alfa_pii")


class ProcessRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    payload: str
    payload_id: str

    @field_validator("payload", "payload_id")
    @classmethod
    def valid_unicode(cls, value: str) -> str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Invalid Unicode") from None
        return value


class ProcessResponse(BaseModel):
    result: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f]+$")
    message: str
    @field_validator("request_id", "message")
    @classmethod
    def valid_unicode(cls, value: str) -> str:
        return ProcessRequest.valid_unicode(value)


class ChatResponse(BaseModel):
    request_id: str
    answer: str


class BodyLimit:
    def __init__(self, app: ASGIApp, maximum: int) -> None:
        self.app, self.maximum = app, maximum

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Buffer only up to the configured bound, before JSON parsing.
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            chunks.append(chunk)
            total += len(chunk)
            if total > self.maximum:
                await JSONResponse({"error": "request_too_large"}, 413)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        delivered = False
        async def replay() -> Any:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


class Observe:
    """Pure ASGI instrumentation: no per-request BaseHTTPMiddleware task groups."""
    def __init__(self, app: ASGIApp, state: Any, capacity: int, requests: Counter,
                 latency: Histogram, in_flight: Gauge, raise_unexpected: bool) -> None:
        self.app, self.state, self.capacity = app, state, capacity
        self.requests, self.latency, self.in_flight = requests, latency, in_flight
        self.raise_unexpected = raise_unexpected

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        route = path if path in {"/process", "/v1/chat", "/metrics", "/health/live", "/health/ready"} else "other"
        if self.state.active >= self.capacity:
            self.requests.labels(route, "429").inc()
            await JSONResponse({"error": "service_busy"}, 429, headers={"Retry-After": "1"})(scope, receive, send)
            return
        self.state.active += 1
        self.in_flight.inc()
        started = time.perf_counter()
        trace = secrets.token_hex(8)
        context_token = trace_id.set(trace)
        status, response_started = 500, False
        async def tracked_send(message: Any) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status, response_started = message["status"], True
                message["headers"] = list(message.get("headers", [])) + [(b"x-request-id", trace.encode())]
            await send(message)
        try:
            try:
                await self.app(scope, receive, tracked_send)
            except Exception:
                if self.raise_unexpected:
                    raise
                if not response_started:
                    await JSONResponse({"error": "internal_error"}, 500)(scope, receive, tracked_send)
        finally:
            elapsed = time.perf_counter() - started
            self.requests.labels(route, str(status)).inc()
            self.latency.labels(route).observe(elapsed)
            self.state.active -= 1
            self.in_flight.dec()
            log.info(json.dumps({"event": "http", "trace": trace,
                                 "route": route, "status": status,
                                 "duration_ms": round(elapsed * 1000, 2)}))
            trace_id.reset(context_token)


def create_app(settings: Settings | None = None, *, service: ProtectionService | None = None,
               consumers: dict[str, Consumer] | None = None,
               credentials: dict[str, str] | None = None) -> FastAPI:
    settings = settings or Settings()
    injected = service is not None
    registry = CollectorRegistry()
    requests = Counter("pii_requests", "HTTP responses", ["route", "status"], registry=registry)
    latency = Histogram("pii_request_seconds", "HTTP latency including queue and I/O", ["route"], registry=registry,
                        buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2, 5, 10, 30))
    chars = Counter("pii_characters", "Accepted input Unicode code points", registry=registry)
    estimated_tokens = Counter("pii_estimated_tokens", "Estimate: Unicode characters / 4; NOT model tokens", registry=registry)
    llm_tokens = Counter("pii_llm_tokens", "Token usage reported by the LLM provider", ["direction"], registry=registry)
    usage_responses = Counter("pii_llm_usage_responses", "Responses with valid provider usage metadata", registry=registry)
    in_flight = Gauge("pii_in_flight", "Active HTTP handlers", registry=registry)
    cidrs = [ipaddress.ip_network(item.strip()) for item in settings.benchmark_cidrs.split(",") if item.strip()]

    def record_usage(prompt: int, completion: int) -> None:
        llm_tokens.labels("input").inc(prompt)
        llm_tokens.labels("output").inc(completion)
        usage_responses.inc()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if injected:
            yield
            return
        load_dotenv(override=False)
        try:
            policies, keys, extra_rules = load_policies(settings.policies_path)
            cipher = Cipher(settings.key_bytes())
        except Exception:
            # Startup must not dump Pydantic input values or environment secrets.
            raise RuntimeError("Invalid application configuration; inspect local settings") from None
        redis = Redis.from_url(settings.redis_url.get_secret_value(),
            password=settings.redis_password.get_secret_value() or None,
            socket_connect_timeout=1, socket_timeout=1, max_connections=128)
        store = RedisStore(redis, cipher, settings.namespace, settings.state_ttl, settings.tombstone_ttl)
        engine = ProcessEngine(settings.cpu_workers, settings.cpu_capacity,
            settings.cpu_timeout, settings.use_ner, extra_rules)
        app.state.service = ProtectionService(store, engine)
        app.state.consumers, app.state.credentials = policies, keys
        try:
            await store.ping()
            warmup = Consumer(id="warmup")
            await asyncio.gather(*[engine.protect("", warmup, "layout_mask") for _ in range(settings.cpu_workers)])
            if settings.llm_base_url:
                app.state.llm = LLMClient(settings.llm_base_url, settings.llm_api_key.get_secret_value(),
                    settings.llm_model, settings.llm_timeout, settings.llm_max_response_bytes, settings.allow_http_llm,
                    on_usage=record_usage)
            yield
        finally:
            if app.state.llm:
                await app.state.llm.close()
            await asyncio.to_thread(engine.close)
            await redis.aclose()

    app = FastAPI(title="AlfaGen PII Protection", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit, maximum=settings.max_body_bytes)
    app.state.service = service
    app.state.consumers = consumers or {}
    app.state.credentials = credentials or {}
    app.state.llm = None
    app.state.active = 0
    app.add_middleware(Observe, state=app.state, capacity=settings.request_capacity,
                       requests=requests, latency=latency, in_flight=in_flight,
                       raise_unexpected=injected)

    def authorize(request: Request, benchmark: bool = False) -> Consumer:
        header = request.headers.get("authorization", "")
        identity = None
        if header.startswith("Bearer "):
            supplied = header[7:].encode()
            for key, consumer_id in app.state.credentials.items():
                if hmac.compare_digest(supplied, key.encode()):
                    identity = consumer_id
        elif benchmark and request.client:
            try:
                peer = ipaddress.ip_address(request.client.host)
                if any(peer in network for network in cidrs):
                    identity = settings.benchmark_consumer
            except ValueError:
                pass
        if identity is None or identity not in app.state.consumers:
            raise ServiceError(401, "unauthorized")
        consumer = app.state.consumers[identity]
        if not consumer.enabled:
            raise ServiceError(403, "consumer_disabled")
        return consumer

    def check_size(text: str) -> None:
        if len(text) > settings.max_text_chars:
            raise ServiceError(413, "text_too_large")
        chars.inc(len(text))
        estimated_tokens.inc(len(text) / 4)

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse({"error": exc.code}, exc.status,
                            headers={"Retry-After": "1"} if exc.status == 429 else None)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"error": "invalid_request"}, 422)

    @app.post("/process", response_model=ProcessResponse)
    async def process(body: ProcessRequest, request: Request) -> ProcessResponse:
        consumer = authorize(request, benchmark=True)
        check_size(body.payload)
        result = await app.state.service.process(body.payload_id, body.payload, consumer)
        return ProcessResponse(result=result)

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request) -> ChatResponse:
        consumer = authorize(request)
        check_size(body.message)
        if app.state.llm is None:
            raise ServiceError(503, "llm_not_configured")
        # The proxy requires tokens; layout mode is for exact /process pairs only.
        if (not consumer.mask_enabled or not {str(k) for k in Kind} <= consumer.mask_types
                or consumer.mask_types != consumer.detect_types or consumer.combinations):
            raise ServiceError(403, "proxy_requires_full_protection")
        svc = app.state.service
        record, _ = await svc.prepare(body.request_id, body.message, consumer, "typed_tokens", "chat")
        if svc.store.cipher.fingerprint(body.message) != record["original_hash"]:
            raise ServiceError(409, "request_id_conflict")
        mapping = MaskResult(**record["mapping"])
        started = time.perf_counter()
        reply = await app.state.llm.complete(mapping.text)
        log.info(json.dumps({"event": "llm_complete", "trace": trace_id.get(),
                             "duration_ms": round((time.perf_counter() - started) * 1000, 2)}))
        if len(reply) > settings.max_text_chars:
            raise ServiceError(502, "llm_response_too_large")
        cleaned = await svc.engine.protect(reply, consumer, "typed_tokens", tuple(mapping.tokens))
        answer = restore(cleaned.text, mapping) if consumer.demask and record["policy"]["demask"] else cleaned.text
        return ChatResponse(request_id=body.request_id, answer=answer)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        await app.state.service.store.ping()
        return {"status": "ready"}

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        authorize(request)
        return Response(generate_latest(registry), media_type="text/plain; version=0.0.4")

    return app
