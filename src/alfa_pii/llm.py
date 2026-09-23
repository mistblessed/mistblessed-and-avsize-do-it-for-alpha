"""OpenAI-compatible transport. Does not log URLs, credentials, or upstream bodies."""
import json
import ssl
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from alfa_pii.domain import ServiceError


def build_tls_context(ca_bundle: str) -> ssl.SSLContext:
    """Use platform trust by default or an explicitly supplied corporate CA bundle."""
    return ssl.create_default_context(cafile=ca_bundle or None)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30,
                 max_response_bytes: int = 8_388_608, allow_http: bool = False,
                 transport: httpx.AsyncBaseTransport | None = None,
                 on_usage: Callable[[int, int], None] | None = None,
                 ca_bundle: str = "") -> None:
        parsed = urlsplit(base_url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM base URL must be an absolute URL without credentials or query")
        if parsed.scheme != "https" and not (allow_http and parsed.scheme == "http"):
            raise ValueError("HTTPS required for the LLM connection")
        if not api_key or not model:
            raise ValueError("LLM API key and model are required")
        self.model, self.max_response_bytes = model, max_response_bytes
        self.on_usage = on_usage
        self.client = httpx.AsyncClient(base_url=base_url.rstrip("/") + "/", timeout=timeout,
            headers={"Authorization": "Bearer " + api_key}, transport=transport,
            follow_redirects=False, trust_env=False, verify=build_tls_context(ca_bundle))

    async def complete(self, text: str) -> str:
        try:
            async with self.client.stream("POST", "chat/completions", json={
                "model": self.model, "stream": False,
                "messages": [
                    {"role": "system", "content": "Preserve every opaque marker in ⟦ ⟧ exactly. Do not infer or invent hidden personal data."},
                    {"role": "user", "content": text},
                ],
            }) as response:
                if response.status_code != 200:
                    raise ServiceError(502, "llm_unavailable")
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > self.max_response_bytes:
                        raise ServiceError(502, "llm_response_too_large")
                data = json.loads(raw)
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise ValueError("Invalid response")
                content.encode("utf-8")
                usage = data.get("usage")
                if self.on_usage is not None and isinstance(usage, dict):
                    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
                    if type(prompt) is int and type(completion) is int and min(prompt, completion) >= 0:
                        self.on_usage(prompt, completion)
                return content
        except httpx.TimeoutException as exc:
            raise ServiceError(504, "llm_timeout") from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ServiceError(502, "llm_invalid_response") from exc

    async def close(self) -> None:
        await self.client.aclose()
