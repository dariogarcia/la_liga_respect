import json
import os
import tempfile
import time
import unittest
from unittest import mock

from src.collection import cache
from src.utils import http


class TestHttpCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rr_cache_")
        self.env = {
            "HTTP_CACHE_DIR": self.tmpdir,
            "HTTP_CACHE_DISABLE": "",
        }
        for key, value in self.env.items():
            os.environ[key] = value
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ["HTTP_CACHE_DISABLE"] = "1"
        os.environ.pop("HTTP_CACHE_DIR", None)

    def test_put_then_get_roundtrip(self):
        cache.cache_put("https://example.com/a", 200, b"hola", ttl=60)
        cached = cache.cache_get("https://example.com/a")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.status_code, 200)
        self.assertEqual(cached.content, b"hola")
        self.assertEqual(cached.text, "hola")

    def test_miss_returns_none(self):
        self.assertIsNone(cache.cache_get("https://example.com/missing"))

    def test_expired_entry_returns_none(self):
        cache.cache_put("https://example.com/a", 200, b"x", ttl=60)
        # Age the stored record past its TTL.
        path = os.path.join(self.tmpdir, os.listdir(self.tmpdir)[0])
        record = json.load(open(path))
        record["fetched_at"] = time.time() - 120
        json.dump(record, open(path, "w"))
        self.assertIsNone(cache.cache_get("https://example.com/a"))

    def test_disabled_flag_skips_cache(self):
        os.environ["HTTP_CACHE_DISABLE"] = "1"
        cache.cache_put("https://example.com/a", 200, b"x", ttl=60)
        self.assertEqual(os.listdir(self.tmpdir), [])
        self.assertIsNone(cache.cache_get("https://example.com/a"))

    def test_params_change_the_key(self):
        cache.cache_put("https://example.com/search", 200, b"a", params={"q": "x"}, ttl=60)
        self.assertIsNone(cache.cache_get("https://example.com/search", params={"q": "y"}))
        self.assertIsNotNone(cache.cache_get("https://example.com/search", params={"q": "x"}))

    def test_ttl_by_status(self):
        self.assertEqual(cache.ttl_for_status(200), cache.TTL_OK_SECONDS)
        self.assertEqual(cache.ttl_for_status(403), cache.TTL_BLOCKED_SECONDS)
        self.assertEqual(cache.ttl_for_status(429), cache.TTL_BLOCKED_SECONDS)
        self.assertEqual(cache.ttl_for_status(404), cache.TTL_CLIENT_ERROR_SECONDS)
        self.assertEqual(cache.ttl_for_status(503), cache.TTL_SERVER_ERROR_SECONDS)

    def test_cached_error_raises_for_status(self):
        cache.cache_put("https://example.com/blocked", 403, b"", ttl=60)
        cached = cache.cache_get("https://example.com/blocked")
        import requests

        with self.assertRaises(requests.HTTPError):
            cached.raise_for_status()


class TestRequestBudget(unittest.TestCase):
    def tearDown(self):
        http.reset_request_budget()
        os.environ.pop("MAX_REQUESTS_PER_RUN", None)

    def test_budget_exhausted_raises(self):
        os.environ["MAX_REQUESTS_PER_RUN"] = "2"
        http.reset_request_budget()
        http.http_get  # helpers are exercised below via acquire
        http.request_budget().acquire()
        http.request_budget().acquire()
        with self.assertRaises(http.RequestBudgetExceeded):
            http.request_budget().acquire()

    def test_zero_disables_budget(self):
        os.environ["MAX_REQUESTS_PER_RUN"] = "0"
        http.reset_request_budget()
        for _ in range(10):
            http.request_budget().acquire()

    def test_budget_counts_requests(self):
        os.environ["MAX_REQUESTS_PER_RUN"] = "100"
        http.reset_request_budget()
        session = mock.Mock()
        session.get.return_value.status_code = 200
        with mock.patch.object(http, "shared_session", return_value=session):
            http.http_get("https://example.com")
            http.http_post("https://example.com", data=b"")
        self.assertEqual(http.request_budget().count, 2)


if __name__ == "__main__":
    unittest.main()
