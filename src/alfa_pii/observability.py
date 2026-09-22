"""Per-request correlation independent of user identifiers and credentials."""
from contextvars import ContextVar

trace_id: ContextVar[str] = ContextVar("pii_trace_id", default="")
consumer_id: ContextVar[str] = ContextVar("pii_consumer_id", default="")
