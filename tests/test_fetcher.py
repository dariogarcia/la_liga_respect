import unittest
from datetime import datetime

from bs4 import BeautifulSoup

from src.collection.fetcher import ArticleFetcher, parse_date_string


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


if __name__ == "__main__":
    unittest.main()
