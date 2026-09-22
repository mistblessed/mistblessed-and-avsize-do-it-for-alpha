"""Non-secret policies are YAML; all credentials are environment variables."""
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from alfa_pii.domain import Kind


class Consumer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    enabled: bool = True
    demask: bool = True
    mask_enabled: bool = True
    mode: Literal["layout_mask", "typed_tokens"] = "layout_mask"
    detect_types: set[str] = Field(default_factory=lambda: {str(k) for k in Kind})
    mask_types: set[str] = Field(default_factory=lambda: {str(k) for k in Kind})
    combinations: dict[str, set[str]] = Field(default_factory=dict)
    key_env: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> "Consumer":
        if not self.mask_types <= self.detect_types:
            raise ValueError("Mask types must be a subset of detection types")
        if any(not needed <= self.detect_types for needed in self.combinations.values()):
            raise ValueError("Combination types must be detectable")
        return self


class ExtraRule(BaseModel):
    kind: str = Field(pattern=r"^[A-Z_]{1,40}$")
    pattern: str = Field(max_length=1000)

    @model_validator(mode="after")
    def check_capture(self) -> "ExtraRule":
        import regex
        compiled = regex.compile(self.pattern)
        if "value" not in compiled.groupindex:
            raise ValueError("Custom rules require a named value capture")
        return self


class Policies(BaseModel):
    model_config = ConfigDict(extra="forbid")
    consumers: list[Consumer]
    extra_rules: list[ExtraRule] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    encryption_key: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    redis_password: SecretStr = SecretStr("")
    namespace: str = Field(default="alfa-pii-v1", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    state_ttl: int = Field(default=1800, ge=1)
    tombstone_ttl: int = Field(default=86400, ge=1)
    policies_path: Path = Path("config/consumers.yaml")
    use_ner: bool = True
    cpu_workers: int = Field(default=2, ge=1, le=64)
    cpu_capacity: int = Field(default=16, ge=1, le=256)
    cpu_timeout: float = Field(default=8, gt=0)
    request_capacity: int = Field(default=128, ge=1)
    max_body_bytes: int = Field(default=8_388_608, ge=1024)
    max_text_chars: int = Field(default=2_000_000, ge=1024)
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout: float = Field(default=30, gt=0)
    llm_max_response_bytes: int = Field(default=8_388_608, ge=1024)
    benchmark_cidrs: str = ""
    benchmark_consumer: str = "benchmark"
    allow_http_llm: bool = False

    def key_bytes(self) -> bytes:
        try:
            key = bytes.fromhex(self.encryption_key.get_secret_value())
        except ValueError:
            raise ValueError("ENCRYPTION_KEY must be 64 hex characters") from None
        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must be 64 hex characters")
        return key


def load_policies(path: Path) -> tuple[dict[str, Consumer], dict[str, str], list[dict[str, str]]]:
    data = Policies.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    consumers: dict[str, Consumer] = {}
    credentials: dict[str, str] = {}
    for c in data.consumers:
        if c.id in consumers:
            raise ValueError("Duplicate consumer ID")
        consumers[c.id] = c
        if c.key_env:
            if not re.fullmatch(r"[A-Z][A-Z0-9_]+", c.key_env):
                raise ValueError("Invalid credential environment name")
            key = os.environ.get(c.key_env, "")
            if c.enabled and len(key) < 24:
                raise ValueError("Enabled consumer requires a key of at least 24 characters")
            if key:
                if key in credentials:
                    raise ValueError("Duplicate consumer credential")
                credentials[key] = c.id
    return consumers, credentials, [r.model_dump() for r in data.extra_rules]

