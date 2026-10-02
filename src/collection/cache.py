"""On-disk HTTP response cache (A4).

Caches sitemap, search and article responses under `.cache/http/`
(gitignored) with a per-status TTL, so retries within the same week,
interrupted runs and same-day re-runs stop re-hitting publishers.
Failures are negatively cached with a shorter TTL.

- 2xx: cached for 48h by default (24h for sitemaps/searches via `ttl`).
- 403/429 (blocks/throttles): 6h — the domain is blocked anyway.
- other 4xx: 24h (a 404 will not heal).
- 5xx: 15min.

Disable with `HTTP_CACHE_DISABLE=1`; relocate with `HTTP_CACHE_DIR`.
The environment is read on every call, so tests can toggle it.
"""

import base64
import hashlib
import json
import os
import time
from typing import Optional

TTL_OK_SECONDS = 48 * 3600
TTL_SITEMAP_SECONDS = 24 * 3600
TTL_BLOCKED_SECONDS = 6 * 3600
TTL_CLIENT_ERROR_SECONDS = 24 * 3600
TTL_SERVER_ERROR_SECONDS = 15 * 60

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def cache_enabled() -> bool:
    return os.environ.get("HTTP_CACHE_DISABLE", "") not in ("1", "true", "yes")


def cache_dir() -> str:
    return os.environ.get("HTTP_CACHE_DIR") or os.path.join(_ROOT, ".cache", "http")


def cache_key(url: str, params: Optional[dict] = None) -> str:
    raw = url
    if params:
        raw = f"{url}?{sorted(params.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ttl_for_status(status: int) -> int:
    if status < 300:
        return TTL_OK_SECONDS
    if status in (403, 429):
        return TTL_BLOCKED_SECONDS
    if status < 500:
        return TTL_CLIENT_ERROR_SECONDS
    return TTL_SERVER_ERROR_SECONDS


def _path(key: str) -> str:
    return os.path.join(cache_dir(), f"{key}.json")


def cache_get(url: str, params: Optional[dict] = None) -> Optional["CachedResponse"]:
    """Returns a cached response, or None on miss/expiry/disabled."""
    if not cache_enabled():
        return None
    path = _path(cache_key(url, params))
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - record.get("fetched_at", 0) > record.get("ttl", 0):
        return None
    try:
        body = base64.b64decode(record["body_b64"])
    except (KeyError, ValueError):
        return None
    return CachedResponse(status_code=record.get("status", 200), content=body)


def cache_put(
    url: str,
    status: int,
    content: bytes,
    params: Optional[dict] = None,
    ttl: Optional[int] = None,
) -> None:
    if not cache_enabled():
        return
    if ttl is None:
        ttl = ttl_for_status(status)
    directory = cache_dir()
    os.makedirs(directory, exist_ok=True)
    record = {
        "url": url,
        "status": status,
        "fetched_at": time.time(),
        "ttl": ttl,
        "body_b64": base64.b64encode(content or b"").decode("ascii"),
    }
    tmp = f"{_path(cache_key(url, params))}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f)
    os.replace(tmp, _path(cache_key(url, params)))


class CachedResponse:
    """Minimal read-only stand-in for a `requests.Response`."""

    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content or b""
        self.headers = {}
        self.text = self.content.decode("utf-8", "replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code} (cached)")
