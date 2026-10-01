import unittest
from unittest.mock import patch

from src.collection.models import SearchResult
from src.collection.sitemap import parse_sitemap, find_coach_articles

SAMPLE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://www.marca.com/futbol/atletico/2026/09/20/simeone-prensa.html</loc>
    <news:news>
      <news:title>Simeone, sobre el arbitraje: hay que respetar al árbitro</news:title>
      <news:publication_date>2026-09-20T22:00:00Z</news:publication_date>
    </news:news>
  </url>
  <url>
    <loc>https://www.as.com/futbol/2026/09/21/flick-prensa.html</loc>
    <news:news>
      <news:title>Flick: "No quiero hablar del árbitro"</news:title>
    </news:news>
  </url>
  <url>
    <loc>https://www.sport.es/noticias/futbol/resultado.html</loc>
    <news:news>
      <news:title>El Atlético vence al Barça en un partido intenso</news:title>
    </news:news>
  </url>
  <url>
    <loc>not-a-url</loc>
    <news:news>
      <news:title>Simeone también aquí</news:title>
    </news:news>
  </url>
</urlset>
"""


class TestParseSitemap(unittest.TestCase):
    def test_parses_urls_and_titles(self):
        results = parse_sitemap(SAMPLE_SITEMAP)
        urls = [r.url for r in results]
        self.assertEqual(len(results), 3)
        self.assertIn("https://www.marca.com/futbol/atletico/2026/09/20/simeone-prensa.html", urls)
        self.assertIn("https://www.as.com/futbol/2026/09/21/flick-prensa.html", urls)
        self.assertTrue(all(r.snippet == "" for r in results))

    def test_skips_non_http_locs(self):
        results = parse_sitemap(SAMPLE_SITEMAP)
        self.assertFalse(any("not-a-url" in r.url for r in results))

    def test_invalid_xml_returns_empty(self):
        self.assertEqual(parse_sitemap("<broken<"), [])

    def test_plain_sitemap_without_news_tags(self):
        xml = """<?xml version="1.0"?>
        <urlset><url><loc>https://www.as.com/a.html</loc></url></urlset>"""
        results = parse_sitemap(xml)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "")


class TestFindCoachArticles(unittest.TestCase):
    def setUp(self):
        self.entries = parse_sitemap(SAMPLE_SITEMAP)

    def test_finds_articles_mentioning_coach(self):
        results = find_coach_articles(self.entries, "Diego Simeone")
        self.assertEqual(len(results), 1)
        self.assertIn("simeone-prensa", results[0].url)

    def test_no_match_returns_empty(self):
        self.assertEqual(find_coach_articles(self.entries, "Pepe Mel"), [])

    def test_referee_articles_rank_first(self):
        entries = [
            SearchResult(url="https://www.as.com/a1", title="Simeone habla del partido", snippet=""),
            SearchResult(url="https://www.as.com/a2", title="Simeone critique al árbitro", snippet=""),
        ]
        results = find_coach_articles(entries, "Diego Simeone")
        self.assertEqual(results[0].url, "https://www.as.com/a2")

    def test_accents_and_case_normalized(self):
        entries = [
            SearchResult(url="https://www.as.com/a1", title="GARCÍA PIMIENTA recela del árbitro", snippet=""),
        ]
        results = find_coach_articles(entries, "García Pimienta")
        self.assertEqual(len(results), 1)

    def test_caps_results(self):
        entries = [
            SearchResult(url=f"https://www.as.com/a{i}", title=f"Simeone nota {i}", snippet="")
            for i in range(10)
        ]
        results = find_coach_articles(entries, "Diego Simeone", max_results=3)
        self.assertEqual(len(results), 3)


if __name__ == "__main__":
    unittest.main()
