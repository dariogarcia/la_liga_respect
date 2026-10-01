import os
import time
from typing import Optional


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


class RateLimiter:
    """Enforces a minimum interval between successive calls to wait()."""

    def __init__(self, min_interval: float = 0.0):
        self.min_interval = max(0.0, float(min_interval))
        self._last: Optional[float] = None

    def wait(self) -> None:
        if self._last is not None and self.min_interval > 0.0:
            elapsed = time.monotonic() - self._last
            remaining = self.min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.monotonic()

    def reset(self) -> None:
        self._last = None


# Politeness limits for outbound HTTP. Override via environment variables
# (set to 0 to disable, e.g. in tests).
FETCH_RATE_LIMITER = RateLimiter(_env_float("RATE_LIMIT_FETCH", 1.0))
SEARCH_RATE_LIMITER = RateLimiter(_env_float("RATE_LIMIT_SEARCH", 2.0))
SITEMAP_RATE_LIMITER = RateLimiter(_env_float("RATE_LIMIT_SITEMAP", 1.0))
