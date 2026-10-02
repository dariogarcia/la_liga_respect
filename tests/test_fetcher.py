import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

import requests
from bs4 import BeautifulSoup

from src.collection.fetcher import (
    ArticleFetcher,
    DomainBlockedError,
    DomainCircuitBreaker,
    RobotsDisallowedError,
    parse_date_string,
    parse_retry_after,
)
from src.collection.robots import AllowAllRobots


HTML = """
<html>
<head>
<title>El técnico habla del árbitro</title>
<meta property="article:published_time" content="2026-08-16T08:30:00Z">
</head>
<body>
<nav>menu</nav>
<article>
<p>El técnico compareció en rueda de prensa.</p>
<p>«El árbitro lo hizo bien», afirmó el entrenador.</p>
</article>
<footer>pie</footer>
<script>var x = 1;</script>
</body>
</html>
"""


class TestParseDateString(unittest.TestCase):
    def test_iso_z(self):
        self.assertEqual(parse_date_string("2026-08-16T08:30:00Z"), datetime(2026, 8, 16, 8, 30))

    def test_plain_date(self):
        self.assertEqual(parse_date_string("2026-08-16"), datetime(2026, 8, 16))

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_date_string("not a date"))


class TestArticleFetcher(unittest.TestCase):
    def setUp(self):
        self.fetcher = ArticleFetcher()
        self.soup = BeautifulSoup(HTML, "html.parser")

    def test_extract_title_prefers_og(self):
        html = '<html><head><meta property="og:title" content="Titular OG"><title>x</title></head></html>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(self.fetcher.extract_title(soup), "Titular OG")

    def test_extract_title_falls_back_to_title_tag(self):
        self.assertEqual(self.fetcher.extract_title(self.soup), "El técnico habla del árbitro")

    def test_extract_published(self):
        self.assertEqual(self.fetcher.extract_published(self.soup), datetime(2026, 8, 16, 8, 30))

    def test_extract_published_none_when_missing(self):
        html = "<html><body><p>sin fecha</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        self.assertIsNone(self.fetcher.extract_published(soup))

    def test_extract_published_from_time_tag(self):
        html = '<html><body><time datetime="2026-09-01">1 sept</time></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(self.fetcher.extract_published(soup), datetime(2026, 9, 1))

    def test_extract_text_removes_noise(self):
        text = self.fetcher.extract_text(self.soup)
        self.assertIn("árbitro", text)
        self.assertNotIn("menu", text)
        self.assertNotIn("pie", text)
        self.assertNotIn("var x", text)


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class TestFetchPoliteness(unittest.TestCase):
    URL = "https://www.sport.es/noticias/foo"

    def setUp(self):
        self.sleep = mock.patch("src.collection.fetcher.time.sleep").start()
        mock.patch("src.collection.fetcher.FETCH_RATE_LIMITER").start()
        mock.patch("src.collection.fetcher.FETCH_DOMAIN_RATE_LIMITER").start()
        self.addCleanup(mock.patch.stopall)

    def _fetcher(self):
        return ArticleFetcher(robots=AllowAllRobots())

    def _patch_get(self, *responses):
        return mock.patch("src.utils.http.http_get", side_effect=list(responses))

    def test_fetch_sends_bot_user_agent(self):
        ok = FakeResponse(200, HTML)
        with self._patch_get(ok) as get:
            self._fetcher().fetch(self.URL)
        headers = get.call_args.kwargs["headers"]
        self.assertTrue(headers["User-Agent"].startswith("RespectRankBot/"))

    def test_robots_disallow_skips_http_entirely(self):
        class DisallowAll:
            def allowed(self, url):
                return False

        fetcher = ArticleFetcher(robots=DisallowAll())
        with self._patch_get(FakeResponse(200, HTML)) as get:
            with self.assertRaises(RobotsDisallowedError):
                fetcher.fetch(self.URL)
        get.assert_not_called()

    def test_429_then_success_retries_with_retry_after(self):
        throttled = FakeResponse(429, headers={"Retry-After": "7"})
        ok = FakeResponse(200, HTML)
        with self._patch_get(throttled, ok) as get:
            doc = self._fetcher().fetch(self.URL)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(self.sleep.call_count, 1)
        self.assertAlmostEqual(self.sleep.call_args.args[0], 7.0)
        self.assertIn("árbitro", doc.text)

    def test_persistent_429_raises_after_max_attempts(self):
        throttled = FakeResponse(429, headers={"Retry-After": "1"})
        with self._patch_get(throttled, throttled, throttled) as get:
            with self.assertRaises(requests.HTTPError):
                self._fetcher().fetch(self.URL)
        self.assertEqual(get.call_count, 3)

    def test_retry_after_http_date_is_honored(self):
        resp = FakeResponse(429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        with mock.patch("src.collection.fetcher.datetime") as fake_dt:
            fake_dt.now.return_value = datetime(2026, 10, 21, 7, 27, 50, tzinfo=timezone.utc)
            self.assertAlmostEqual(parse_retry_after(resp), 10.0)

    def test_huge_retry_after_is_capped(self):
        throttled = FakeResponse(429, headers={"Retry-After": "3600"})
        ok = FakeResponse(200, HTML)
        with self._patch_get(throttled, ok):
            self._fetcher().fetch(self.URL)
        self.assertAlmostEqual(self.sleep.call_args.args[0], 120.0)

    def test_503_without_retry_after_uses_exponential_backoff(self):
        unavailable = FakeResponse(503)
        ok = FakeResponse(200, HTML)
        with self._patch_get(unavailable, ok):
            self._fetcher().fetch(self.URL)
        self.assertAlmostEqual(self.sleep.call_args.args[0], 2.0)

    def test_404_does_not_retry(self):
        with self._patch_get(FakeResponse(404)) as get:
            with self.assertRaises(requests.HTTPError):
                self._fetcher().fetch(self.URL)
        self.assertEqual(get.call_count, 1)
        self.sleep.assert_not_called()


WAYBACK_HTML = """
<html>
<head><title>Declaraciones del míster</title>
<meta property="article:published_time" content="2026-09-16T08:30:00Z"></head>
<body>
<div id="wm-ipp">Wayback Machine toolbar http://archive.org/web/</div>
<article>
<p>«El árbitro actuó con criterio», dijo el entrenador en la rueda de prensa.</p>
</article>
</body>
</html>
"""

WAYBACK_API_OK = json.dumps({
    "url": "https://as.com/futbol/primera/foo/",
    "archived_snapshots": {
        "closest": {
            "status": "200",
            "available": True,
            "url": "http://web.archive.org/web/20260915065517/https://as.com/futbol/primera/foo/",
            "timestamp": "20260915065517",
        }
    },
})

WAYBACK_API_MISS = json.dumps({"archived_snapshots": {}})


class TestWaybackFallback(unittest.TestCase):
    """Blocklisted domains are read via the Internet Archive, never directly."""

    BLOCKED_URL = "https://as.com/futbol/primera/foo/"

    def setUp(self):
        mock.patch("src.collection.fetcher.time.sleep").start()
        mock.patch("src.collection.fetcher.FETCH_RATE_LIMITER").start()
        mock.patch("src.collection.fetcher.FETCH_DOMAIN_RATE_LIMITER").start()
        self.addCleanup(mock.patch.stopall)

    def _fetcher(self):
        return ArticleFetcher(robots=AllowAllRobots())

    def _patch_get(self, *responses):
        return mock.patch("src.utils.http.http_get", side_effect=list(responses))

    def _env(self, **extra):
        env = {"BLOCKED_DOMAINS": "as.com", "WAYBACK_FALLBACK": "1"}
        env.update(extra)
        return mock.patch.dict(os.environ, env)

    def test_blocklisted_domain_uses_archive_only(self):
        api = FakeResponse(200, WAYBACK_API_OK)
        snapshot = FakeResponse(200, WAYBACK_HTML)
        with self._env(), self._patch_get(api, snapshot) as get:
            doc = self._fetcher().fetch(self.BLOCKED_URL)
        called_urls = [c.args[0] for c in get.call_args_list]
        # The publisher itself is never contacted: only the public
        # availability API and the archive playback page.
        self.assertTrue(called_urls[0].startswith("https://archive.org/wayback/available"))
        self.assertTrue(called_urls[1].startswith("https://web.archive.org/web/20260915065517/"))
        self.assertFalse(any(u.startswith("https://as.com") for u in called_urls))
        # Provenance: the document keeps the original publisher URL.
        self.assertEqual(doc.url, self.BLOCKED_URL)
        self.assertEqual(doc.source_name, "as.com")
        # Content: article text extracted, Wayback toolbar stripped.
        self.assertIn("árbitro", doc.text)
        self.assertNotIn("Wayback Machine", doc.text)

    def test_no_snapshot_raises(self):
        api = FakeResponse(200, WAYBACK_API_MISS)
        with self._env(), self._patch_get(api) as get:
            with self.assertRaises(requests.HTTPError):
                self._fetcher().fetch(self.BLOCKED_URL)
        self.assertEqual(get.call_count, 1)

    def test_wayback_disabled_raises_without_any_request(self):
        with self._env(WAYBACK_FALLBACK="0"), self._patch_get() as get:
            with self.assertRaises(requests.HTTPError):
                self._fetcher().fetch(self.BLOCKED_URL)
        get.assert_not_called()

    def test_robots_disallow_on_archive_skips_fallback(self):
        class DisallowArchive:
            def allowed(self, url):
                return "archive.org" not in url

        api = FakeResponse(200, WAYBACK_API_OK)
        with self._env(), self._patch_get(api) as get:
            fetcher = ArticleFetcher(robots=DisallowArchive())
            with self.assertRaises(requests.HTTPError):
                fetcher.fetch(self.BLOCKED_URL)
        get.assert_not_called()

    def test_hard_block_on_normal_domain_falls_back_to_archive(self):
        blocked = FakeResponse(403)
        api = FakeResponse(200, WAYBACK_API_OK)
        snapshot = FakeResponse(200, WAYBACK_HTML)
        with self._env(BLOCKED_DOMAINS="", WAYBACK_FALLBACK="1"), \
             self._patch_get(blocked, api, snapshot) as get:
            doc = self._fetcher().fetch(self.BLOCKED_URL)
        self.assertEqual(get.call_count, 3)
        self.assertIn("árbitro", doc.text)
        self.assertEqual(doc.url, self.BLOCKED_URL)

    def test_soft_errors_do_not_use_archive(self):
        not_found = FakeResponse(404)
        with self._env(BLOCKED_DOMAINS=""), self._patch_get(not_found) as get:
            with self.assertRaises(requests.HTTPError):
                self._fetcher().fetch(self.BLOCKED_URL)
        self.assertEqual(get.call_count, 1)


class TestParseRetryAfter(unittest.TestCase):
    def test_missing_header(self):
        self.assertIsNone(parse_retry_after(FakeResponse(429)))

    def test_garbage_header(self):
        self.assertIsNone(parse_retry_after(FakeResponse(429, headers={"Retry-After": "soon"})))

    def test_delta_seconds(self):
        self.assertEqual(parse_retry_after(FakeResponse(429, headers={"Retry-After": "30"})), 30.0)


class TestDomainCircuitBreaker(unittest.TestCase):
    def test_opens_after_threshold_failures(self):
        breaker = DomainCircuitBreaker()
        for _ in range(DomainCircuitBreaker.FAILURE_THRESHOLD):
            breaker.register_failure("sport.es")
        with self.assertRaises(DomainBlockedError):
            breaker.check("sport.es")

    def test_success_resets_counter(self):
        breaker = DomainCircuitBreaker()
        breaker.register_failure("sport.es")
        breaker.register_failure("sport.es")
        breaker.register_success("sport.es")
        breaker.register_failure("sport.es")
        breaker.check("sport.es")  # only 1 consecutive failure, still closed

    def test_domains_are_independent(self):
        breaker = DomainCircuitBreaker()
        for _ in range(DomainCircuitBreaker.FAILURE_THRESHOLD):
            breaker.register_failure("sport.es")
        breaker.check("relevo.com")  # unaffected

    def test_repeated_403_opens_breaker(self):
        forbidden = FakeResponse(403)
        fetcher = ArticleFetcher(robots=AllowAllRobots())
        with mock.patch("src.collection.fetcher.FETCH_RATE_LIMITER"), \
             mock.patch("src.collection.fetcher.time.sleep"), \
             self._patch_get(forbidden, forbidden, forbidden):
            for _ in range(DomainCircuitBreaker.FAILURE_THRESHOLD):
                with self.assertRaises(requests.HTTPError):
                    fetcher.fetch("https://www.sport.es/noticias/foo")
        with self._patch_get(FakeResponse(200, HTML)) as get:
            with self.assertRaises(DomainBlockedError):
                fetcher.fetch("https://www.sport.es/noticias/other")
        get.assert_not_called()

    def _patch_get(self, *responses):
        return mock.patch("src.utils.http.http_get", side_effect=list(responses))


if __name__ == "__main__":
    unittest.main()
