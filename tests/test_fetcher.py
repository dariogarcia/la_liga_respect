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
            raise requests.HTTPError(f"HTTP {self.status_code}")


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
