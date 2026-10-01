import unittest

from src.collection.filtering import is_allowed_source, get_domain


class TestFiltering(unittest.TestCase):
    def test_allowed_domains(self):
        for url in [
            "https://www.as.com/futbol/articulo.html",
            "https://marca.com/futbol/laliga.html",
            "https://www.laliga.com/en-ES/match/123",
            "https://sport.es/article/1",
            "https://www.mundodeportivo.com/futbol/1",
            "https://relevo.com/futbol/primera-division/articulo.html",
            "https://www.cope.es/deportes/futbol/noticia.html",
        ]:
            self.assertTrue(is_allowed_source(url), url)

    def test_blocked_domains(self):
        for url in [
            "https://blogspot.com/as.html",
            "https://as.com.evil.io/article",
            "https://twitter.com/coach/status/1",
            "https://notas.com",
            "https://www.bing.com/ck/a",
            "https://relevo.com.evil.io/article",
            "https://www.elconfidencial.com/deportes/futbol/202601-01/",
            "https://cadenaser.com/deporte-futbol/20260101.html",
        ]:
            self.assertFalse(is_allowed_source(url), url)

    def test_get_domain_strips_www(self):
        self.assertEqual(get_domain("https://www.as.com/a"), "as.com")
        self.assertEqual(get_domain("https://AS.COM/a"), "as.com")


if __name__ == "__main__":
    unittest.main()
