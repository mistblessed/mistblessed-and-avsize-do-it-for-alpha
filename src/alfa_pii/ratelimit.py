"""Per-consumer token-bucket rate limiting. Single-threaded (event loop) safe."""
import time


class TokenBucket:
    """Fixed-rate token bucket. capacity is the burst; refill is rate per second."""

    __slots__ = ("rate", "capacity", "tokens", "updated")

    def __init__(self, rate: int) -> None:
        self.rate = float(rate)
        self.capacity = float(rate)
        self.tokens = float(rate)
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False