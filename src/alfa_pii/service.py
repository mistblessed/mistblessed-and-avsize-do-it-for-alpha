import asyncio
import json
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from typing import Any, Protocol

from alfa_pii.config import Consumer
from alfa_pii.detection.engine import TOKEN, Detector, resolve
from alfa_pii.domain import MaskResult, ServiceError
from alfa_pii.observability import trace_id
from alfa_pii.state.store import Store
from alfa_pii.transformation.masking import mask, restore

log = logging.getLogger("alfa_pii")


def protect(detector: Detector, text: str, policy: Consumer, mode: str,
            trusted_tokens: tuple[str, ...] = ()) -> MaskResult:
    trusted = set(trusted_tokens)
    scan_text = TOKEN.sub(lambda m: " " * len(m.group()) if m.group() in trusted else m.group(), text) if trusted else text
    candidates = [e for e in detector.detect(scan_text) if str(e.kind) in policy.detect_types]
    types = {str(e.kind) for e in candidates}
    selected = [e for e in candidates if policy.mask_enabled and str(e.kind) in policy.mask_types
                and policy.combinations.get(str(e.kind), set()) <= types]
    result = mask(text, resolve(selected), mode)
    result.types = sorted(types)
    return result


class Engine(Protocol):
    async def protect(self, text: str, policy: Consumer, mode: str,
                      trusted_tokens: tuple[str, ...] = ()) -> MaskResult: ...


class InlineEngine:
    """Test-only engine; production uses a bounded process pool."""
    def __init__(self, detector: Detector) -> None:
        self.detector = detector

    async def protect(self, text: str, policy: Consumer, mode: str,
                      trusted_tokens: tuple[str, ...] = ()) -> MaskResult:
        return protect(self.detector, text, policy, mode, trusted_tokens)


_detector: Detector | None = None


def init_worker(use_ner: bool, extra_rules: list[dict[str, str]]) -> None:
    global _detector
    _detector = Detector(use_ner, extra_rules)


def run_worker(text: str, policy: dict[str, Any], mode: str,
               trusted_tokens: tuple[str, ...]) -> MaskResult:
    if _detector is None:
        raise RuntimeError("Worker is not initialized")
    return protect(_detector, text, Consumer.model_validate(policy), mode, trusted_tokens)


class ProcessEngine:
    def __init__(self, workers: int, capacity: int, timeout: float, use_ner: bool,
                 extra_rules: list[dict[str, str]]) -> None:
        self.pool = ProcessPoolExecutor(max_workers=workers,
            mp_context=multiprocessing.get_context("spawn"), initializer=init_worker,
            initargs=(use_ner, extra_rules))
        self.capacity, self.timeout, self.pending = capacity, timeout, 0

    async def protect(self, text: str, policy: Consumer, mode: str,
                      trusted_tokens: tuple[str, ...] = ()) -> MaskResult:
        if self.pending >= self.capacity:
            raise ServiceError(429, "cpu_busy")
        self.pending += 1
        loop = asyncio.get_running_loop()
        try:
            future = loop.run_in_executor(self.pool, run_worker, text, policy.model_dump(), mode, trusted_tokens)
        except Exception as exc:
            self.pending -= 1
            raise ServiceError(503, "worker_unavailable") from exc
        # Retain capacity until the process REALLY finishes, even after HTTP timeout.
        future.add_done_callback(lambda _: setattr(self, "pending", self.pending - 1))
        try:
            return await asyncio.wait_for(asyncio.shield(future), self.timeout)
        except TimeoutError as exc:
            raise ServiceError(503, "processing_timeout") from exc
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(503, "worker_failed") from exc

    def close(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)


class ProtectionService:
    def __init__(self, store: Store, engine: Engine) -> None:
        self.store, self.engine = store, engine

    def key(self, consumer: Consumer, identifier: str, scope: str = "process") -> str:
        return self.store.cipher.fingerprint(json.dumps([scope, consumer.id, identifier]))

    async def prepare(self, identifier: str, text: str, consumer: Consumer,
                      mode: str | None = None, scope: str = "process") -> tuple[dict[str, Any], bool]:
        if not consumer.enabled:
            raise ServiceError(403, "consumer_disabled")
        key = self.key(consumer, identifier, scope)
        record = await self.store.get(key)
        created = record is None
        if record is None:
            started = time.perf_counter()
            result = await self.engine.protect(text, consumer, mode or consumer.mode)
            policy = consumer.model_dump(mode="json")
            record = await self.store.create_or_get(key, {
                "original_hash": self.store.cipher.fingerprint(text),
                "masked_hash": self.store.cipher.fingerprint(result.text),
                "mapping": asdict(result), "consumer": consumer.id, "policy": policy,
            })
            log.info(json.dumps({"event": "protection", "trace": trace_id.get(), "types": result.types,
                                 "duration_ms": round((time.perf_counter() - started) * 1000, 2)}))
        effective = {"enabled", "demask", "key_env"}
        if (Consumer.model_validate(record["policy"]).model_dump(exclude=effective)
                != consumer.model_dump(exclude=effective)):
            raise ServiceError(409, "policy_changed")
        return record, created

    async def process(self, identifier: str, text: str, consumer: Consumer) -> str:
        record, _ = await self.prepare(identifier, text, consumer)
        digest = self.store.cipher.fingerprint(text)
        mapping = MaskResult(**record["mapping"])
        log.info(json.dumps({"event": "process", "trace": trace_id.get(), "types": mapping.types,
                             "direction": "mask" if digest == record["original_hash"] else "restore"}))
        if digest == record["original_hash"]:
            return mapping.text
        if digest == record["masked_hash"]:
            if not consumer.demask or not record["policy"]["demask"]:
                raise ServiceError(403, "restoration_disabled")
            return restore(text, mapping)
        raise ServiceError(409, "payload_id_conflict")
