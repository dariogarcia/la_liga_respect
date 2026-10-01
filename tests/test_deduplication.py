import unittest

from src.collection.deduplication import deduplicate_quotes, quote_hash


class TestDeduplication(unittest.TestCase):
    def test_dedupes_same_text_different_case_and_spacing(self):
        quotes = [
            {"text": "El árbitro  lo hizo bien"},
            {"text": "el árbitro lo hizo    bien"},
            {"text": "Otra cita distinta"},
        ]
        result = deduplicate_quotes(quotes)
        self.assertEqual(len(result), 2)

    def test_keeps_order(self):
        quotes = [{"text": "a"}, {"text": "b"}, {"text": "a"}]
        result = deduplicate_quotes(quotes)
        self.assertEqual([q["text"] for q in result], ["a", "b"])

    def test_hash_stable(self):
        self.assertEqual(quote_hash("Hola  Mundo"), quote_hash("hola mundo"))


if __name__ == "__main__":
    unittest.main()
