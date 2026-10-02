import unittest
from unittest import mock

import requests

from src.collection.robots import RobotsPolicy


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class TestRobotsPolicy(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("src.collection.robots.FETCH_RATE_LIMITER")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _policy(self, status_code=200, text="", side_effect=None):
        session = mock.Mock()
        if side_effect is not None:
            session.get.side_effect = side_effect
        else:
            session.get.return_value = FakeResponse(status_code, text)
        return RobotsPolicy(session=session)

    def test_disallow_rule_blocks_matching_paths_only(self):
        body = "User-agent: *\nDisallow: /articulos/"
        policy = self._policy(200, body)
        self.assertFalse(policy.allowed("https://www.sport.es/articulos/foo"))
        self.assertTrue(policy.allowed("https://www.sport.es/noticias/foo"))

    def test_wildcard_disallow_all_blocks(self):
        policy = self._policy(200, "User-agent: *\nDisallow: /")
        self.assertFalse(policy.allowed("https://www.sport.es/anything"))

    def test_bot_token_rule_applies_to_us(self):
        policy = self._policy(200, "User-agent: RespectRankBot\nDisallow: /")
        self.assertFalse(policy.allowed("https://www.sport.es/anything"))

    def test_404_allows_all(self):
        policy = self._policy(404)
        self.assertTrue(policy.allowed("https://www.sport.es/anything"))

    def test_5xx_disallows_all(self):
        policy = self._policy(503)
        self.assertFalse(policy.allowed("https://www.sport.es/anything"))

    def test_network_error_disallows_all(self):
        policy = self._policy(side_effect=requests.ConnectionError("boom"))
        self.assertFalse(policy.allowed("https://www.sport.es/anything"))

    def test_rules_are_cached_per_origin(self):
        session = mock.Mock()
        session.get.return_value = FakeResponse(200, "User-agent: *\nDisallow: /")
        policy = RobotsPolicy(session=session)
        policy.allowed("https://www.sport.es/a")
        policy.allowed("https://www.sport.es/b")
        self.assertEqual(session.get.call_count, 1)

    def test_distinct_origins_fetched_separately(self):
        session = mock.Mock()
        session.get.return_value = FakeResponse(200, "User-agent: *\nDisallow: /")
        policy = RobotsPolicy(session=session)
        policy.allowed("https://www.sport.es/a")
        policy.allowed("https://www.relevo.com/b")
        self.assertEqual(session.get.call_count, 2)

    def test_non_http_url_is_rejected(self):
        policy = self._policy(200, "User-agent: *\nDisallow: /")
        self.assertFalse(policy.allowed("ftp://example.com/x"))
        self.assertFalse(policy.allowed("not a url"))


if __name__ == "__main__":
    unittest.main()
