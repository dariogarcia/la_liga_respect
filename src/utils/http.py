"""Shared HTTP plumbing for the whole pipeline (D3 + D5).

- One shared `requests.Session` (connection pooling, fewer handshakes).
- A per-run request budget (`MAX_REQUESTS_PER_RUN`, default 600, `0`
  disables): every network call made through `http_get`/`http_post`
  counts against it, so a bad week cannot hammer publishers or run
  away on a misconfigured loop.

All pipeline HTTP should go through these helpers instead of calling
`requests` directly, so the budget cannot be bypassed by accident.
"""

import os
from typing import Optional

import requests

DEFAULT_MAX_REQUESTS_PER_RUN = 600


class RequestBudgetExceeded(RuntimeError):
    """Raised when the run has exhausted its HTTP request budget."""


class _RequestBudget:
    def __init__(self):
        self.limit = _max_requests()
        self.count = 0

    def acquire(self) -> None:
        if self.limit and self.count >= self.limit:
            raise RequestBudgetExceeded(
                f"HTTP request budget exhausted ({self.count}/{self.limit} requests). "
                f"Raise MAX_REQUESTS_PER_RUN to allow more."
            )
        self.count += 1


def _max_requests() -> int:
    raw = os.environ.get("MAX_REQUESTS_PER_RUN")
    if raw is None:
        return DEFAULT_MAX_REQUESTS_PER_RUN
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_REQUESTS_PER_RUN


_BUDGET: Optional[_RequestBudget] = None
_SESSION: Optional[requests.Session] = None


def request_budget() -> _RequestBudget:
    """Process-wide budget; reads MAX_REQUESTS_PER_RUN on first use."""
    global _BUDGET
    if _BUDGET is None:
        _BUDGET = _RequestBudget()
    return _BUDGET


def reset_request_budget() -> None:
    """Starts a fresh budget (used by tests and new runs)."""
    global _BUDGET
    _BUDGET = _RequestBudget()


def shared_session() -> requests.Session:
    """The one Session reused by every pipeline component (D5)."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def http_get(url: str, **kwargs) -> requests.Response:
    request_budget().acquire()
    return shared_session().get(url, **kwargs)


def http_post(url: str, **kwargs) -> requests.Response:
    request_budget().acquire()
    return shared_session().post(url, **kwargs)
