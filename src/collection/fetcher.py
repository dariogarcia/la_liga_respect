from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
import json
import os
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .filtering import get_domain
from .models import SourceDocument
from .robots import RobotsPolicy, shared_robots_policy
from . import cache
from ..utils import http
from ..utils.ratelimit import FETCH_RATE_LIMITER, FETCH_DOMAIN_RATE_LIMITER
from ..utils.useragent import BOT_USER_AGENT

USER_AGENT = BOT_USER_AGENT

# Domains that persistently hard-block our user agent (403/406 WAF).
# They are never contacted directly - not even for robots.txt - and
# their articles are read from the Internet Archive's public Wayback
# Machine playback instead. Override with BLOCKED_DOMAINS (comma-
# separated; empty string disables the list).
DEFAULT_BLOCKED_DOMAINS = "as.com,sport.es"

# Set WAYBACK_FALLBACK=0 to also disable the archive fallback and fail
# hard on blocklisted domains.
WAYBACK_API = "https://archive.org/wayback/available?url="


def get_blocked_domains():
    raw = os.environ.get("BLOCKED_DOMAINS", DEFAULT_BLOCKED_DOMAINS)
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


def wayback_enabled() -> bool:
    return os.environ.get("WAYBACK_FALLBACK", "1") != "0"

# Total attempts per article before giving up (1 initial + retries).
MAX_ATTEMPTS = 3
# Statuses that are worth retrying: throttling and temporary failures.
RETRYABLE_STATUSES = {429, 503}
SERVER_ERROR_STATUSES = frozenset(range(500, 600))
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 60.0
# Retry-After is honored but capped so a huge value cannot stall a run.
RETRY_AFTER_CAP_SECONDS = 120.0


class RobotsDisallowedError(Exception):
    """Raised when robots.txt forbids fetching a URL."""


class DomainBlockedError(Exception):
    """Raised when the per-domain circuit breaker is open."""


def parse_retry_after(response: requests.Response) -> Optional[float]:
    """Parses the Retry-After header (delta-seconds or HTTP-date)."""
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class DomainCircuitBreaker:
    """Disables fetching from a domain after repeated block responses.

    After FAILURE_THRESHOLD consecutive 403/429 responses a domain is
    skipped for COOLDOWN_SECONDS, so a blocking publisher does not burn
    one slow request per candidate article for the rest of the run.
    Any successful response resets the counter.
    """

    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 900

    def __init__(self):
        self._consecutive_failures = {}
        self._open_until = {}

    def check(self, domain: str) -> None:
        until = self._open_until.get(domain, 0.0)
        if time.monotonic() < until:
            raise DomainBlockedError(
                f"domain {domain} is blocked for {int(until - time.monotonic())}s more "
                f"({self.FAILURE_THRESHOLD} consecutive 403/429 responses)"
            )

    def register_failure(self, domain: str) -> None:
        count = self._consecutive_failures.get(domain, 0) + 1
        self._consecutive_failures[domain] = count
        if count >= self.FAILURE_THRESHOLD:
            self._open_until[domain] = time.monotonic() + self.COOLDOWN_SECONDS
            print(
                f"Fetcher: {domain} returned {self.FAILURE_THRESHOLD} consecutive block "
                f"responses, skipping it for {self.COOLDOWN_SECONDS}s."
            )

    def register_success(self, domain: str) -> None:
        self._consecutive_failures.pop(domain, None)
        self._open_until.pop(domain, None)

DATE_META_PROPERTIES = [
    "article:published_time",
    "og:article:published_time",
    "article:modified_time",
    "og:updated_time",
]
DATE_META_NAMES = [
    "parsely-pub-date",
    "sailthru.date",
    "date",
    "DC.date.issued",
    "DC.date",
    "publish-date",
    "publication_date",
]
DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%Y/%m/%d",
]


def parse_date_string(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.split(" ")[0], fmt)
        except ValueError:
            continue
    return None


class ArticleFetcher:
    """Fetches an article URL and extracts clean text, title and publish date.

    Politeness: robots.txt is checked per origin (cached per process),
    requests are rate limited, 429/503 responses are retried with the
    server's Retry-After (capped) or exponential backoff, and a domain
    that keeps answering 403/429 is circuit-broken for the rest of the
    run.
    """

    def __init__(
        self,
        robots: Optional[RobotsPolicy] = None,
        circuit_breaker: Optional[DomainCircuitBreaker] = None,
    ):
        self.robots = robots if robots is not None else shared_robots_policy()
        self.circuit_breaker = circuit_breaker or DomainCircuitBreaker()

    def _get_with_retries(self, url: str, headers: dict) -> requests.Response:
        domain = get_domain(url)
        # On-disk cache (A4): a hit avoids the network entirely. Cached
        # errors raise immediately (retrying a stored failure is
        # pointless) but still feed the circuit breaker.
        cached = cache.cache_get(url)
        if cached is not None:
            if cached.status_code < 400:
                self.circuit_breaker.register_success(domain)
            else:
                self.circuit_breaker.register_failure(domain)
                cached.raise_for_status()
            return cached
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self.circuit_breaker.check(domain)
            FETCH_RATE_LIMITER.wait()
            FETCH_DOMAIN_RATE_LIMITER.wait(domain)
            response = http.http_get(url, timeout=15, headers=headers)
            if response.status_code == 429:
                self.circuit_breaker.register_failure(domain)
            if response.status_code in RETRYABLE_STATUSES or (
                response.status_code in SERVER_ERROR_STATUSES
            ):
                if attempt >= MAX_ATTEMPTS:
                    self._cache_response(url, response)
                    response.raise_for_status()
                time.sleep(self._retry_delay(response, attempt))
                continue
            if response.status_code == 403:
                self.circuit_breaker.register_failure(domain)
            if response.status_code < 400:
                self.circuit_breaker.register_success(domain)
            self._cache_response(url, response)
            response.raise_for_status()
            return response
        raise requests.HTTPError(f"exhausted retries for {url}")

    @staticmethod
    def _cache_response(url: str, response) -> None:
        content = getattr(response, "content", None)
        if content is None:
            content = (response.text or "").encode("utf-8", "replace")
        cache.cache_put(url, response.status_code, content)

    @staticmethod
    def _retry_delay(response: requests.Response, attempt: int) -> float:
        backoff = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2 ** (attempt - 1))
        retry_after = parse_retry_after(response)
        if retry_after is not None:
            # Honor the server's hint, capped so a huge value cannot
            # stall the whole run.
            return min(retry_after, RETRY_AFTER_CAP_SECONDS)
        return backoff

    def fetch(self, url: str) -> SourceDocument:
        domain = get_domain(url)
        # Blocklisted publishers are never contacted directly; their
        # articles are read from the public Wayback Machine copy.
        if domain in get_blocked_domains():
            return self._fetch_via_wayback(url, domain)
        if not self.robots.allowed(url):
            raise RobotsDisallowedError(f"robots.txt disallows fetching {url}")
        try:
            response = self._get_with_retries(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
                },
            )
        except (requests.HTTPError, DomainBlockedError) as e:
            # A hard block (403/401/406 or an open circuit breaker) means
            # the publisher refuses us: fall back to the archive copy
            # rather than hammering the server with retries.
            if wayback_enabled() and self._is_hard_block(e):
                return self._fetch_via_wayback(url, domain)
            raise

        soup = BeautifulSoup(response.text, "html.parser")
        return SourceDocument(
            url=url,
            title=self.extract_title(soup),
            text=self.extract_text(soup),
            published_at=self.extract_published(soup),
            source_name=get_domain(url),
        )

    @staticmethod
    def _is_hard_block(error: Exception) -> bool:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status in (401, 403, 406):
            return True
        return isinstance(error, DomainBlockedError)

    def _fetch_via_wayback(self, url: str, domain: str) -> SourceDocument:
        """Reads a hard-blocked article from the Internet Archive.

        Ethical ground rules: the publisher's server is never contacted
        (it already refused this bot); the Wayback Machine playback and
        its documented availability API are public services consulted at
        the same rate-limited, budgeted, cached pace as every other
        fetch; robots.txt is honored for the archive origins; and the
        document keeps the original publisher URL for attribution.
        """
        if not wayback_enabled():
            raise requests.HTTPError(
                f"{domain} is blocklisted and WAYBACK_FALLBACK=0: {url}"
            )
        snapshot = self._wayback_snapshot(url)
        if snapshot is None:
            raise requests.HTTPError(
                f"no Wayback snapshot available for blocklisted {domain}: {url}"
            )
        response = self._get_with_retries(
            snapshot,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
            },
        )
        soup = BeautifulSoup(response.text, "html.parser")
        self._strip_wayback_chrome(soup)
        return SourceDocument(
            url=url,
            title=self.extract_title(soup),
            text=self.extract_text(soup),
            published_at=self.extract_published(soup),
            source_name=domain,
        )

    def _wayback_snapshot(self, url: str) -> Optional[str]:
        """Resolves the closest archived snapshot via the public API."""
        api_url = WAYBACK_API + quote(url, safe="")
        try:
            if not self.robots.allowed(api_url):
                print("Wayback fallback skipped: robots.txt disallows archive.org.")
                return None
            response = self._get_with_retries(
                api_url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            data = json.loads(response.text)
            closest = (data.get("archived_snapshots") or {}).get("closest") or {}
            if closest.get("available") and closest.get("status") == "200":
                snapshot = closest.get("url") or ""
                return snapshot.replace("http://", "https://", 1)
        except (requests.HTTPError, DomainBlockedError, ValueError) as e:
            print(f"Wayback availability lookup failed for {url}: {e}")
        return None

    @staticmethod
    def _strip_wayback_chrome(soup: BeautifulSoup) -> None:
        """Removes the Wayback playback toolbar from an archived page."""
        for element_id in ("wm-ipp", "wm-ipp-base", "wm-ipp-print"):
            for el in soup.find_all(id=element_id):
                el.decompose()

    def extract_title(self, soup: BeautifulSoup) -> str:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            return og["content"].strip()
        twitter = soup.find("meta", attrs={"name": "twitter:title"})
        if twitter and twitter.get("content"):
            return twitter["content"].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return "Unknown Title"

    def extract_published(self, soup: BeautifulSoup) -> Optional[datetime]:
        for prop in DATE_META_PROPERTIES:
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content"):
                dt = parse_date_string(tag["content"])
                if dt:
                    return dt
        for name in DATE_META_NAMES:
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                dt = parse_date_string(tag["content"])
                if dt:
                    return dt
        for el in soup.find_all("time"):
            raw = el.get("datetime") or el.get_text(strip=True)
            dt = parse_date_string(raw)
            if dt:
                return dt
        return None

    def extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                         "figure", "noscript", "form", "iframe", "svg"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
