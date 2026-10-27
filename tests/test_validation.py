import unittest

from src.collection.validation import validate_extractions
from src.collection.models import SourceDocument
from datetime import datetime


def make_doc(text):
    return SourceDocument(
        url="https://www.as.com/a",
        title="t",
        text=text,
        published_at=None,
        source_name="as.com",
    )


class TestValidation(unittest.TestCase):
    def test_verbatim_quote_passes(self):
        doc = make_doc("El entrenador dijo: «El árbitro lo hizo bien, fue un gran trabajo».")
        quotes = [{"text": "El árbitro lo hizo bien, fue un gran trabajo"}]
        self.assertEqual(len(validate_extractions(quotes, doc)), 1)

    def test_whitespace_and_case_insensitive(self):
        doc = make_doc("párrafo con  espaciones   raros y MAYÚSCULAS del árbitro")
        quotes = [{"text": "espaciones raros y mayúsculas"}]
        self.assertEqual(len(validate_extractions(quotes, doc)), 1)

    def test_linebreak_before_punctuation(self):
        # Regression (Clásico 2026-10-25): the article body wrapped lines
        # mid-sentence ("minuto 60\n,"), which made a verbatim quote ending
        # at that break fail the substring check after whitespace
        # collapsing ("60 ," vs "60,"). Punctuation must be reattached.
        doc = make_doc(
            "un VAR que creo que estaba dormido en el minuto 60\n"
            ", es una clara tarjeta roja de Joao Cancelo a Diomande"
        )
        quotes = [{
            "text": "un VAR que creo que estaba dormido en el minuto 60, "
                    "es una clara tarjeta roja de Joao Cancelo a Diomande"
        }]
        self.assertEqual(len(validate_extractions(quotes, doc)), 1)

    def test_invented_quote_rejected(self):
        doc = make_doc("El entrenador habló del árbitro.")
        quotes = [{"text": "cita inventada que no está en el documento"}]
        self.assertEqual(len(validate_extractions(quotes, doc)), 0)

    def test_short_or_missing_text_rejected(self):
        doc = make_doc("El árbitro.")
        quotes = [{"text": "El árbitro."}, {}, {"text": None}]
        self.assertEqual(len(validate_extractions(quotes, doc)), 0)


if __name__ == "__main__":
    unittest.main()
