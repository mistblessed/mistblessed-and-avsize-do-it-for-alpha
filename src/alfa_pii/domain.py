"""Shared contracts. Offsets are Python Unicode code-point offsets, end-exclusive."""

from dataclasses import dataclass, field
from enum import StrEnum


class Kind(StrEnum):
    PERSON = "PERSON"
    BIRTH_DATE = "BIRTH_DATE"
    BIRTH_PLACE = "BIRTH_PLACE"
    PASSPORT = "PASSPORT"
    CITIZENSHIP = "CITIZENSHIP"
    PASSPORT_ISSUER = "PASSPORT_ISSUER"
    DEPARTMENT_CODE = "DEPARTMENT_CODE"
    ISSUE_DATE = "ISSUE_DATE"
    DRIVER_LICENSE = "DRIVER_LICENSE"
    ADDRESS = "ADDRESS"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    INN = "INN"
    CARD = "CARD"
    CVV = "CVV"
    PIN = "PIN"
    CARDHOLDER = "CARDHOLDER"


@dataclass(frozen=True)
class Entity:
    kind: Kind | str
    start: int
    end: int
    confidence: float = 1.0
    source: str = "rule"
    components: tuple[tuple[int, int], ...] = ()


@dataclass
class MaskResult:
    text: str
    replacements: list[dict[str, str | int]] = field(default_factory=list)
    tokens: dict[str, str] = field(default_factory=dict)
    types: list[str] = field(default_factory=list)


class ServiceError(Exception):
    """Only fixed public messages may be passed here; never include user input."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code

    def __reduce__(self):  # type: ignore[no-untyped-def]
        return (ServiceError, (self.status, self.code))
