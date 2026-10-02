import os
import unittest
from datetime import date, datetime
from unittest import mock
from unittest.mock import MagicMock

from src.collection.models import SearchResult
from src.collection.search import (
    BingSearchProvider,
    CompositeSearchProvider,
    DuckDuckGoSearchProvider,
    GoogleNewsRSSSearchProvider,
    get_search_provider,
    SearchProviderError,
)


def _bing_redirect(url: str) -> str:
    import base64
    return "https://www.bing.com/ck/a?!&&p=abc&u=a1" + base64.b64encode(url.encode()).decode()


class TestBingUrlDecoding(unittest.TestCase):
    def setUp(self):
        self.provider = BingSearchProvider()

    def test_decodes_redirect(self):
        real = "https://www.marca.com/futbol/atletico.html"
        self.assertEqual(self.provider.decode_url(_bing_redirect(real)), real)

    def test_passthrough_plain_url(self):
        self.assertEqual(
            self.provider.decode_url("https://www.as.com/a.html"),
            "https://www.as.com/a.html",
        )

    def test_undecodable_redirect_returns_none(self):
        self.assertIsNone(self.provider.decode_url("https://www.bing.com/ck/a?!&&u=a1%%%"))

    def test_relative_url_returns_none(self):
        self.assertIsNone(self.provider.decode_url("/search?q=x"))

    def test_malformed_base64_returns_none(self):
        self.assertIsNone(self.provider.decode_url("https://www.bing.com/ck/a?u=a1not-base64!!"))


class TestDuckDuckGoUrlResolution(unittest.TestCase):
    def test_resolves_ddg_redirect(self):
        provider = DuckDuckGoSearchProvider()
        href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.marca.com%2Fa.html&rut=abc"
        self.assertEqual(provider._resolve_url(href), "https://www.marca.com/a.html")

    def test_plain_url_untouched(self):
        provider = DuckDuckGoSearchProvider()
        self.assertEqual(
            provider._resolve_url("https://www.as.com/a.html"),
            "https://www.as.com/a.html",
        )


class TestCompositeSearchProvider(unittest.TestCase):
    def _provider_returning(self, results):
        p = MagicMock()
        p.search.return_value = results
        return p

    def test_first_non_empty_wins(self):
        empty = self._provider_returning([])
        good = self._provider_returning([SearchResult(url="https://www.as.com/a", title="t", snippet="")        ])
        third = self._provider_returning([SearchResult(url="https://www.marca.com/b", title="t2", snippet="")])
        composite = CompositeSearchProvider([empty, good, third])
        results = composite.search("query")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://www.as.com/a")
        empty.search.assert_called_once()
        good.search.assert_called_once()
        third.search.assert_not_called()

    def test_all_empty_returns_empty(self):
        composite = CompositeSearchProvider(
            [self._provider_returning([]), self._provider_returning([])]
        )
        self.assertEqual(composite.search("query"), [])

    def test_provider_exception_falls_through(self):
        failing = MagicMock()
        failing.search.side_effect = RuntimeError("boom")
        good = self._provider_returning([SearchResult(url="https://www.as.com/a", title="t", snippet="")])
        composite = CompositeSearchProvider([failing, good])
        results = composite.search("query")
        self.assertEqual(len(results), 1)

    def test_all_providers_failing_raises(self):
        # G2 regression: an outage across every provider must raise,
        # not return [] — an empty list would read as "no coverage"
        # and could presume a respectful silence that never was
        # verified (e.g. after the HTTP budget is exhausted).
        failing = MagicMock()
        failing.search.side_effect = RuntimeError("budget exhausted")
        composite = CompositeSearchProvider([failing, MagicMock()])
        composite.providers[1].search.side_effect = RuntimeError("down")
        with self.assertRaises(SearchProviderError):
            composite.search("query")

    def test_forwards_date_range_to_providers(self):
        provider = self._provider_returning([])
        composite = CompositeSearchProvider([provider])
        composite.search("query", date_range=(date(2026, 9, 20), date(2026, 9, 23)))
        provider.search.assert_called_once_with(
            "query", 10, date_range=(date(2026, 9, 20), date(2026, 9, 23))
        )

    def test_get_search_provider_with_key_includes_serpapi_first(self):
        composite = get_search_provider(api_key="fake")
        self.assertIsInstance(composite, CompositeSearchProvider)
        self.assertEqual(type(composite.providers[0]).__name__, "WebSearchProvider")
        self.assertEqual(len(composite.providers), 2)

    def test_get_search_provider_without_key_is_keyless(self):
        composite = get_search_provider(api_key=None)
        self.assertIsInstance(composite, CompositeSearchProvider)
        names = [type(p).__name__ for p in composite.providers]
        self.assertEqual(names, ["GoogleNewsRSSSearchProvider"])

    def test_html_scrapers_require_opt_in(self):
        with mock.patch.dict(os.environ, {"ENABLE_HTML_SCRAPERS": "1"}, clear=False):
            composite = get_search_provider(api_key=None)
        names = [type(p).__name__ for p in composite.providers]
        self.assertEqual(
            names,
            ["GoogleNewsRSSSearchProvider", "DuckDuckGoSearchProvider", "BingSearchProvider"],
        )


class TestDuckDuckGoCircuitBreaker(unittest.TestCase):
    def _failing_provider(self):
        provider = DuckDuckGoSearchProvider()
        response = MagicMock()
        response.status_code = 202
        return provider, response

    def _patched(self):
        # Mock the rate limiter so the tests do not really sleep.
        return mock.patch("src.collection.search.SEARCH_RATE_LIMITER")

    def test_opens_after_consecutive_failures(self):
        provider, response = self._failing_provider()
        with mock.patch("src.utils.http.http_post") as post_mock, self._patched():
            post_mock.return_value = response
            for _ in range(provider.FAILURE_THRESHOLD):
                with self.assertRaises(SearchProviderError):
                    provider.search("query")
            self.assertEqual(post_mock.call_count, provider.FAILURE_THRESHOLD)
            # Circuit breaker open: further calls fail instantly
            # without touching the network.
            with self.assertRaises(SearchProviderError):
                provider.search("query")
            self.assertEqual(post_mock.call_count, provider.FAILURE_THRESHOLD)

    def test_closes_again_after_cooldown(self):
        provider, response = self._failing_provider()
        with mock.patch("src.utils.http.http_post") as post_mock, self._patched():
            post_mock.return_value = response
            for _ in range(provider.FAILURE_THRESHOLD):
                with self.assertRaises(SearchProviderError):
                    provider.search("query")
            self.assertEqual(post_mock.call_count, provider.FAILURE_THRESHOLD)
            # Simulate cooldown expiry: the provider is probed again.
            provider._disabled_until = 0.0
            with self.assertRaises(SearchProviderError):
                provider.search("query")
            self.assertEqual(post_mock.call_count, provider.FAILURE_THRESHOLD + 1)


class TestGoogleNewsRSSProvider(unittest.TestCase):
    RSS_XML = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<item><title>Simeone habla del árbitro</title>"
        "<link>https://news.google.com/rss/articles/AAA111?oc=5</link>"
        "<pubDate>Sun, 20 Sep 2026 18:36:04 GMT</pubDate></item>"
        "<item><title>Otro titular</title>"
        "<link>https://news.google.com/rss/articles/BBB222?oc=5</link>"
        "<pubDate>Sun, 20 Sep 2026 19:00:00 GMT</pubDate></item>"
        "</channel></rss>"
    )
    SIGNATURE_HTML = '<c-wiz><div data-n-a-sg="SIG123" data-n-a-ts="1790868910"></div></c-wiz>'

    def setUp(self):
        self.provider = GoogleNewsRSSSearchProvider()
        self.provider._decode_delay = 0
        self.provider.session = MagicMock()
        # Mock the rate limiter so the tests do not really sleep.
        limiter = mock.patch("src.collection.search.SEARCH_RATE_LIMITER")
        limiter.start()
        self.addCleanup(limiter.stop)

    @staticmethod
    def _response(status_code=200, **kwargs):
        response = MagicMock()
        response.status_code = status_code
        for key, value in kwargs.items():
            setattr(response, key, value)
        return response

    def _batch_response(self, url):
        payload = '["garturlres","%s"]' % url
        row = '["wrb.fr","Fbv4je",%s,null,null,null,"0"]' % (
            '"' + payload.replace('"', '\\"') + '"'
        )
        return self._response(text=")]}'\n\n" + "[" + row + ']')

    def _full_flow(self):
        self.provider.session.get.side_effect = [
            self._response(content=self.RSS_XML.encode()),
            self._response(text=self.SIGNATURE_HTML),
            self._response(status_code=404),
        ]
        self.provider.session.post.return_value = self._batch_response(
            "https://www.marca.com/futbol/x.html"
        )

    def test_appends_date_operators_to_query(self):
        self.provider.session.get.return_value = self._response(content=b"<rss></rss>")
        self.provider.search(
            "Simeone árbitro", date_range=(date(2026, 9, 20), date(2026, 9, 23))
        )
        params = self.provider.session.get.call_args[1]["params"]
        self.assertIn("after:2026-09-20", params["q"])
        self.assertIn("before:2026-09-23", params["q"])
        self.assertIn("Simeone árbitro", params["q"])

    def test_no_date_range_leaves_query_untouched(self):
        self.provider.session.get.return_value = self._response(content=b"<rss></rss>")
        self.provider.search("Simeone árbitro")
        params = self.provider.session.get.call_args[1]["params"]
        self.assertNotIn("after:", params["q"])

    def test_decodes_links_and_returns_publisher_urls(self):
        self._full_flow()
        results = self.provider.search("Simeone árbitro")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://www.marca.com/futbol/x.html")
        self.assertEqual(results[0].title, "Simeone habla del árbitro")
        self.assertEqual(results[0].published, datetime(2026, 9, 20, 18, 36, 4))
        # One signature page per uncached id, one batched decode POST.
        self.assertEqual(self.provider.session.get.call_count, 3)
        self.assertEqual(self.provider.session.post.call_count, 1)

    def test_undecodable_items_are_skipped(self):
        self.provider.session.get.side_effect = [
            self._response(content=self.RSS_XML.encode()),
            self._response(status_code=404),
            self._response(status_code=404),
        ]
        results = self.provider.search("Simeone árbitro")
        self.assertEqual(results, [])
        self.provider.session.post.assert_not_called()

    def test_cached_ids_are_not_decoded_twice(self):
        self._full_flow()
        self.provider.search("Simeone árbitro")
        self.provider.session.get.reset_mock()
        self.provider.session.get.side_effect = None
        self.provider.session.post.reset_mock()
        self.provider.session.get.return_value = self._response(
            content=self.RSS_XML.encode()
        )
        results = self.provider.search("Simeone árbitro")
        self.assertEqual(len(results), 1)
        # Only the RSS feed is fetched again; decodes come from cache.
        self.assertEqual(self.provider.session.get.call_count, 1)
        self.provider.session.post.assert_not_called()

    def test_non_200_rss_trips_circuit_breaker(self):
        self.provider.session.get.return_value = self._response(status_code=429)
        with mock.patch("src.collection.search.SEARCH_RATE_LIMITER"):
            for _ in range(self.provider.FAILURE_THRESHOLD):
                with self.assertRaises(SearchProviderError):
                    self.provider.search("q")
            calls = self.provider.session.get.call_count
            with self.assertRaises(SearchProviderError):
                self.provider.search("q")
            self.assertEqual(self.provider.session.get.call_count, calls)


if __name__ == "__main__":
    unittest.main()
