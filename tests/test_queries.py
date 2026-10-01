import unittest
from datetime import date

from src.collection.queries import build_queries


class TestQueries(unittest.TestCase):
    def test_queries_mention_coach_and_opponent(self):
        queries = build_queries("Quique Sánchez Flores", "Getafe", date(2026, 8, 15))
        for q in queries:
            self.assertIn("Quique Sánchez Flores", q)
            self.assertIn("Getafe", q)

    def test_queries_do_not_embed_iso_date(self):
        queries = build_queries("X", "Y", date(2026, 8, 15))
        for q in queries:
            self.assertNotIn("2026-08-15", q)

    def test_queries_mix_spanish_and_english(self):
        queries = " ".join(build_queries("X", "Y", date(2026, 1, 1)))
        self.assertIn("árbitro", queries)
        self.assertIn("referee", queries)

    def test_full_set_includes_site_restricted_variants(self):
        queries = build_queries("X", "Y", date(2026, 1, 1))
        site_queries = [q for q in queries if "site:" in q]
        self.assertEqual(len(site_queries), 4)
        self.assertTrue(any("referee" in q for q in queries))


if __name__ == "__main__":
    unittest.main()
