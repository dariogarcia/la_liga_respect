import base64
import json
import os
import re
import time
from datetime import date as date_type, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional, Protocol, Tuple
from urllib.parse import parse_qs, quote, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from . import cache
from .models import SearchResult
from ..utils import http
from ..utils.ratelimit import SEARCH_RATE_LIMITER
from ..utils.useragent import BROWSER_USER_AGENT

# Scraped-engine endpoints (DuckDuckGo HTML, Bing) reject non-browser
# agents, so these two providers must send a browser User-Agent. This is
# the only place a browser UA is allowed: everything that touches
# publisher infrastructure identifies itself as RespectRankBot (see
# src/utils/useragent.py).
USER_AGENT = BROWSER_USER_AGENT


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        max_results: int = 10,
        date_range: Optional[Tuple[date_type, date_type]] = None,
    ) -> List[SearchResult]:
        ...


class WebSearchProvider:
    """SerpApi-based search provider. Requires SERPAPI_KEY."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.serpapi.com/search"

    def search(self, query: str, max_results: int = 10, date_range=None) -> List[SearchResult]:
        params = {
            "q": query,
            "api_key": self.api_key,
            "num": max_results,
        }
        try:
            response = http.http_get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            results = []
            for org_result in data.get("organic_results", []):
                results.append(SearchResult(
                    url=org_result.get("link", ""),
                    title=org_result.get("title", ""),
                    snippet=org_result.get("snippet", "")
                ))
            return results
        except Exception as e:
            print(f"Search error for query '{query}': {e}")
            return []


class DuckDuckGoSearchProvider:
    """Keyless fallback provider scraping DuckDuckGo's HTML endpoint.

    Includes a circuit breaker: after FAILURE_THRESHOLD consecutive
    failed requests (throttle responses or network errors) the provider
    is skipped for COOLDOWN_SECONDS, so a dead endpoint does not burn
    one slow request per query for the rest of the run.
    """

    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 900

    def __init__(self):
        self.url = "https://html.duckduckgo.com/html/"
        self._consecutive_failures = 0
        self._disabled_until = 0.0

    def _register_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.FAILURE_THRESHOLD:
            self._disabled_until = time.monotonic() + self.COOLDOWN_SECONDS
            print(
                f"DuckDuckGo: {self._consecutive_failures} consecutive failures, "
                f"disabling for {self.COOLDOWN_SECONDS}s."
            )

    def _register_success(self):
        self._consecutive_failures = 0

    def _resolve_url(self, href: str) -> str:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "uddg" in qs:
                return qs["uddg"][0]
        return href

    def search(self, query: str, max_results: int = 10, date_range=None) -> List[SearchResult]:
        if time.monotonic() < self._disabled_until:
            return []
        SEARCH_RATE_LIMITER.wait()
        try:
            response = http.http_post(
                self.url,
                data={"q": query},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if response.status_code != 200:
                print(f"DuckDuckGo returned HTTP {response.status_code} (likely rate-limited).")
                self._register_failure()
                return []
            self._register_success()
            soup = BeautifulSoup(response.text, "html.parser")

            results = []
            links = soup.select("a.result__a")
            snippets = soup.select(".result__snippet")
            for i, link in enumerate(links[:max_results]):
                url = self._resolve_url(link.get("href", ""))
                if not url.startswith("http"):
                    continue
                snippet = snippets[i].get_text(" ", strip=True) if i < len(snippets) else ""
                results.append(SearchResult(
                    url=url,
                    title=link.get_text(" ", strip=True),
                    snippet=snippet,
                ))
            return results
        except Exception as e:
            print(f"Search error for query '{query}': {e}")
            self._register_failure()
            return []


class BingSearchProvider:
    """Keyless fallback provider scraping Bing. Decodes bing.com/ck redirect URLs."""

    def __init__(self):
        self.url = "https://www.bing.com/search"

    @staticmethod
    def decode_url(href: str) -> Optional[str]:
        if not href or not href.startswith("http"):
            if href and href.startswith("/"):
                return None
            return href or None
        parsed = urlparse(href)
        if "bing.com" in parsed.netloc and "/ck/" in parsed.path:
            qs = parse_qs(parsed.query)
            u = qs.get("u", [""])[0]
            if u.startswith("a1") and len(u) > 2:
                try:
                    decoded = base64.b64decode(u[2:] + "==").decode("utf-8", "ignore").strip()
                    return decoded if decoded.startswith("http") else None
                except Exception:
                    return None
            return None
        return href

    def search(self, query: str, max_results: int = 10, date_range=None) -> List[SearchResult]:
        SEARCH_RATE_LIMITER.wait()
        try:
            response = http.http_get(
                self.url,
                params={"q": query, "count": max_results},
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            if response.status_code != 200:
                print(f"Bing returned HTTP {response.status_code}.")
                return []
            soup = BeautifulSoup(response.text, "html.parser")

            results = []
            items = soup.select("li.b_algo")
            for item in items[:max_results]:
                link = item.select_one("h2 a")
                if not link:
                    continue
                url = self.decode_url(link.get("href", ""))
                if not url or not url.startswith("http") or "bing.com" in urlparse(url).netloc:
                    continue
                snippet_el = item.select_one(".b_caption p")
                results.append(SearchResult(
                    url=url,
                    title=link.get_text(" ", strip=True),
                    snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
                ))
            return results
        except Exception as e:
            print(f"Search error for query '{query}': {e}")
            return []


GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_GARTURLREQ_CTX = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
    "X",
    "X",
    1,
    [1, 1, 1],
    1,
    1,
    None,
    0,
    0,
    None,
    0,
]
_SIGNATURE_RE = re.compile(r'data-n-a-sg="([^"]+)"')
_TIMESTAMP_RE = re.compile(r'data-n-a-ts="([^"]+)"')


class GoogleNewsRSSSearchProvider:
    """Keyless provider backed by Google News RSS.

    Unlike the scraped engines it supports date-bounded queries via the
    after:/before: operators, so games older than the publication window
    stay searchable within their own 48h window. RSS item links are
    Google News redirect URLs; they are decoded to the original
    publisher URL with Google's two-step batchexecute protocol (fetch
    signature page, then one batched POST).

    google.com serves a consent redirect to browser User-Agents, so this
    provider must use a plain requests session (default UA), not
    USER_AGENT.
    """

    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 900

    def __init__(self):
        self.session = requests.Session()
        self._decoded: Dict[str, Optional[str]] = {}
        self._consecutive_failures = 0
        self._disabled_until = 0.0
        self._decode_delay = 0.25

    def _register_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.FAILURE_THRESHOLD:
            self._disabled_until = time.monotonic() + self.COOLDOWN_SECONDS
            print(
                f"Google News RSS: {self._consecutive_failures} consecutive failures, "
                f"disabling for {self.COOLDOWN_SECONDS}s."
            )

    def _register_success(self):
        self._consecutive_failures = 0

    @staticmethod
    def _article_id(link: str) -> Optional[str]:
        parsed = urlparse(link)
        if parsed.hostname == "news.google.com":
            parts = parsed.path.split("/")
            if len(parts) > 1 and parts[-2] in ("articles", "read"):
                return parts[-1] or None
        return None

    def search(
        self,
        query: str,
        max_results: int = 10,
        date_range: Optional[Tuple[date_type, date_type]] = None,
    ) -> List[SearchResult]:
        if time.monotonic() < self._disabled_until:
            return []
        q = query
        if date_range:
            start, end = date_range
            q = f"{query} after:{start.isoformat()} before:{end.isoformat()}"
        params = {"q": q, "hl": "es", "gl": "ES", "ceid": "ES:es"}
        # On-disk cache (A4): a date-bounded query is stable, so its
        # feed is fetched at most once per 24h even across runs.
        cached = cache.cache_get(GOOGLE_NEWS_RSS_URL, params=params)
        if cached is not None and cached.status_code == 200:
            return self._parse_feed(cached.content, max_results)
        SEARCH_RATE_LIMITER.wait()
        try:
            http.request_budget().acquire()
            response = self.session.get(GOOGLE_NEWS_RSS_URL, params=params, timeout=15)
            if response.status_code != 200:
                print(f"Google News RSS returned HTTP {response.status_code}.")
                self._register_failure()
                return []
            cache.cache_put(
                GOOGLE_NEWS_RSS_URL, 200, response.content, ttl=cache.TTL_SITEMAP_SECONDS
            )
        except Exception as e:
            print(f"Search error for query '{query}': {e}")
            self._register_failure()
            return []
        self._register_success()
        return self._parse_feed(response.content, max_results)

    def _parse_feed(self, content: bytes, max_results: int) -> List[SearchResult]:
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError:
            return []
        items = []
        for item in root.findall(".//item")[:max_results]:
            link = item.findtext("link") or ""
            if not link:
                continue
            items.append({
                "title": item.findtext("title") or "",
                "link": link,
                "published": self._parse_pubdate(item.findtext("pubDate")),
            })
        if not items:
            return []
        decoded = self._decode_links([i["link"] for i in items])
        results = []
        for item in items:
            url = decoded.get(item["link"])
            if not url:
                continue
            results.append(SearchResult(
                url=url,
                title=item["title"],
                snippet="",
                published=item["published"],
            ))
        return results

    @staticmethod
    def _parse_pubdate(text: Optional[str]) -> Optional[object]:
        if not text:
            return None
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _decode_links(self, links: List[str]) -> Dict[str, str]:
        """Map Google News redirect links to publisher URLs.

        The decoding protocol (Google's undocumented batchexecute
        endpoint) can be disabled with GOOGLE_NEWS_DECODE=0 (C3): the
        provider then yields no results instead of relying on the
        gray-area endpoint.

        Signature pages are fetched one per uncached article id, then a
        single batchexecute POST decodes all of them. Failures are
        cached as None so they are not retried within the same run.
        """
        if os.environ.get("GOOGLE_NEWS_DECODE", "1") in ("0", "false", "no"):
            if not getattr(self, "_decode_disabled_logged", False):
                print("Google News decode disabled via GOOGLE_NEWS_DECODE, skipping RSS results.")
                self._decode_disabled_logged = True
            return {}
        mapping: Dict[str, str] = {}
        uncached = []
        for link in links:
            aid = self._article_id(link)
            if aid is None:
                continue
            if aid in self._decoded:
                if self._decoded[aid]:
                    mapping[link] = self._decoded[aid]
            else:
                uncached.append(aid)
        batch = []
        for aid in uncached:
            params = self._fetch_decoding_params(aid)
            self._decoded[aid] = None
            if params is not None:
                batch.append((aid, params[0], params[1]))
            if self._decode_delay:
                time.sleep(self._decode_delay)
        if batch:
            for aid, url in self._batchexecute_decode(batch):
                self._decoded[aid] = url
        for link in links:
            aid = self._article_id(link)
            if aid is not None and self._decoded.get(aid):
                mapping[link] = self._decoded[aid]
        return mapping

    def _fetch_decoding_params(self, art_id: str) -> Optional[Tuple[int, str]]:
        url = f"https://news.google.com/rss/articles/{art_id}?hl=es&gl=ES&ceid=ES:es"
        try:
            http.request_budget().acquire()
            response = self.session.get(url, timeout=15, allow_redirects=False)
            if response.status_code != 200:
                return None
            sig = _SIGNATURE_RE.search(response.text)
            ts = _TIMESTAMP_RE.search(response.text)
            if not (sig and ts):
                return None
            return int(ts.group(1)), sig.group(1)
        except Exception:
            return None

    def _batchexecute_decode(self, batch: List[Tuple[str, int, str]]) -> List[Tuple[str, str]]:
        envelopes = []
        for i, (aid, ts, sig) in enumerate(batch):
            inner = json.dumps(
                ["garturlreq", _GARTURLREQ_CTX, aid, ts, sig],
                separators=(",", ":"),
            )
            envelopes.append(["Fbv4je", inner, None, str(i)])
        body = "f.req=" + quote(json.dumps([envelopes], separators=(",", ":")))
        try:
            http.request_budget().acquire()
            response = self.session.post(
                GOOGLE_NEWS_BATCH_URL,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                timeout=15,
            )
            if response.status_code != 200:
                return []
        except Exception as e:
            print(f"Google News decode error: {e}")
            return []
        return self._parse_batchexecute(response.text, batch)

    @staticmethod
    def _parse_batchexecute(text: str, batch) -> List[Tuple[str, str]]:
        body = text
        if body.startswith(")]}'"):
            body = body.split("\n", 1)[1] if "\n" in body else body[4:]
        try:
            rows = json.loads(body.lstrip())
        except json.JSONDecodeError:
            return []
        pairs = []
        for row in rows:
            if not (isinstance(row, list) and len(row) >= 3 and row[1] == "Fbv4je"):
                continue
            payload = row[2]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            if not (isinstance(payload, list) and payload and payload[0] == "garturlres"):
                continue
            req_id = None
            for cell in reversed(row[3:]):
                if cell is not None:
                    req_id = str(cell)
                    break
            if req_id is not None and req_id.isdigit() and int(req_id) < len(batch):
                pairs.append((batch[int(req_id)][0], payload[1]))
        return pairs


class CompositeSearchProvider:
    """Tries multiple providers in order and returns the first non-empty results."""

    def __init__(self, providers: List[SearchProvider]):
        self.providers = providers

    def search(
        self,
        query: str,
        max_results: int = 10,
        date_range: Optional[Tuple[date_type, date_type]] = None,
    ) -> List[SearchResult]:
        for provider in self.providers:
            try:
                results = provider.search(query, max_results, date_range=date_range)
            except TypeError:
                # Providers with the older two-argument signature.
                results = provider.search(query, max_results)
            except Exception as e:
                print(f"Provider {type(provider).__name__} failed: {e}")
                continue
            if results:
                return results
        return []


def html_scrapers_enabled() -> bool:
    """U3: the DuckDuckGo/Bing HTML scrapers are legally gray (scraping
    consumer pages against their ToS). They only run when explicitly
    opted in with ENABLE_HTML_SCRAPERS=1."""
    return os.environ.get("ENABLE_HTML_SCRAPERS", "") in ("1", "true", "yes")


def get_search_provider(api_key: str = None) -> SearchProvider:
    providers: List[SearchProvider] = []
    if api_key:
        providers.append(WebSearchProvider(api_key=api_key))
    # Google News RSS comes right after any paid provider: it is the
    # only keyless engine that honours date-bounded queries, so it must
    # not be shadowed by undated results from the scraped engines.
    providers.append(GoogleNewsRSSSearchProvider())
    if html_scrapers_enabled():
        providers.append(DuckDuckGoSearchProvider())
        providers.append(BingSearchProvider())
        if not api_key:
            print("Keyless search: Google News RSS + opt-in DuckDuckGo/Bing scrapers.")
    elif not api_key:
        print("No SERPAPI_KEY provided, falling back to keyless search "
              "(Google News RSS). Set ENABLE_HTML_SCRAPERS=1 to also use "
              "the DuckDuckGo/Bing HTML scrapers.")
    return CompositeSearchProvider(providers)
