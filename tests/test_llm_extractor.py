"""Unit tests for LLMQuoteExtractor with a mocked LLM backend."""
import unittest
from datetime import datetime
from unittest.mock import patch

from src.collection.extractor import LLMQuoteExtractor, get_extractor
from src.collection.models import SourceDocument


def make_doc(text, url="https://www.marca.com/futbol/x.html"):
    return SourceDocument(
        url=url,
        title="Test article",
        text=text,
        published_at=datetime(2026, 9, 20, 22, 0),
        source_name="marca.com",
    )


class TestLLMQuoteExtractor(unittest.TestCase):
    def _extract(self, llm_response, coach="Diego Simeone", doc=None):
        doc = doc or make_doc("El árbitro lo hizo bien, fue un trabajo muy difícil.")
        with patch("src.utils.llm.llm_chat", return_value=llm_response) as mock_chat:
            quotes = LLMQuoteExtractor().extract(coach, "1", doc)
        return quotes, mock_chat

    def test_parses_llm_quotes(self):
        response = {"quotes": [
            {"text": "El árbitro lo hizo bien.", "referee_related": True},
        ]}
        quotes, _ = self._extract(response)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["text"], "El árbitro lo hizo bien.")
        self.assertEqual(quotes[0]["confidence"], "llm")

    def test_filters_out_non_referee_quotes(self):
        response = {"quotes": [
            {"text": "El árbitro lo hizo bien, fue un trabajo difícil.", "referee_related": True},
            {"text": "Estamos contentos con la victoria del equipo.", "referee_related": False},
        ]}
        quotes, _ = self._extract(response)
        self.assertEqual(len(quotes), 1)
        self.assertIn("árbitro", quotes[0]["text"])

    def test_filters_out_empty_texts(self):
        response = {"quotes": [
            {"text": "", "referee_related": True},
            {"text": None, "referee_related": True},
            {"text": "  ", "referee_related": True},
            {"text": "El árbitro acertó en todo.", "referee_related": True},
        ]}
        quotes, _ = self._extract(response)
        self.assertEqual(len(quotes), 1)

    def test_strips_whitespace(self):
        response = {"quotes": [
            {"text": "  El árbitro acertó en todo.  ", "referee_related": True},
        ]}
        quotes, _ = self._extract(response)
        self.assertEqual(quotes[0]["text"], "El árbitro acertó en todo.")

    def test_empty_quotes_list(self):
        quotes, _ = self._extract({"quotes": []})
        self.assertEqual(quotes, [])

    def test_missing_quotes_key(self):
        quotes, _ = self._extract({})
        self.assertEqual(quotes, [])

    def test_prompt_contains_coach_and_article(self):
        doc = make_doc("Simeone habló del árbitro en la rueda de prensa.")
        _, mock_chat = self._extract({"quotes": []}, coach="Diego Simeone", doc=doc)
        mock_chat.assert_called_once()
        args, kwargs = mock_chat.call_args
        system, user = args
        self.assertIn("Diego Simeone", user)
        self.assertIn("rueda de prensa", user)
        self.assertIn("verbatim", system)
        self.assertTrue(kwargs.get("json_mode"))
        self.assertEqual(kwargs.get("temperature"), 0.0)

    def test_long_document_truncated(self):
        filler = "x" * 20000
        doc = make_doc(filler + "TRUNCATED_MARKER")
        _, mock_chat = self._extract({"quotes": []}, doc=doc)
        user = mock_chat.call_args[0][1]
        self.assertIn("x" * 12000, user)
        self.assertNotIn("TRUNCATED_MARKER", user)

    def test_get_extractor_prefers_llm_when_configured(self):
        with patch("src.utils.llm.llm_available", return_value=True):
            self.assertIsInstance(get_extractor(), LLMQuoteExtractor)

    def test_get_extractor_falls_back_without_key(self):
        with patch("src.utils.llm.llm_available", return_value=False):
            from src.collection.extractor import HeuristicQuoteExtractor
            self.assertIsInstance(get_extractor(), HeuristicQuoteExtractor)


if __name__ == "__main__":
    unittest.main()


class TestLLMAssessCoverage(unittest.TestCase):
    def test_coach_quoted_true(self):
        doc = make_doc("Simeone habló en la rueda de prensa: «El equipo estuvo muy bien».")
        with patch("src.utils.llm.llm_chat", return_value={"coach_quoted": True}) as mock_chat:
            result = LLMQuoteExtractor().assess_coverage("Diego Simeone", [doc])
        self.assertTrue(result)
        self.assertIn("Diego Simeone", mock_chat.call_args[0][1])
        self.assertEqual(mock_chat.call_args.kwargs.get("purpose"), "coverage")

    def test_coach_quoted_false(self):
        doc = make_doc("El rival entrenó en la mañana.")
        with patch("src.utils.llm.llm_chat", return_value={"coach_quoted": False}):
            result = LLMQuoteExtractor().assess_coverage("Diego Simeone", [doc])
        self.assertFalse(result)

    def test_protocol_error_falls_back_to_heuristic(self):
        doc = make_doc("Diego Simeone habló: «El equipo estuvo muy bien».")
        with patch("src.utils.llm.llm_chat", side_effect=ValueError("bad json")):
            result = LLMQuoteExtractor().assess_coverage("Diego Simeone", [doc])
        self.assertTrue(result)  # heuristic detects the quote

    def test_budget_exhaustion_falls_back_to_heuristic(self):
        from src.utils import llm as llm_mod
        doc = make_doc("El rival entrenó en la mañana.")
        with patch("src.utils.llm.llm_chat", side_effect=llm_mod.LLMBudgetExceeded("over")):
            result = LLMQuoteExtractor().assess_coverage("Diego Simeone", [doc])
        self.assertFalse(result)

    def test_truncates_documents(self):
        doc = make_doc("Simeone dijo: «Bien». " + "x" * 20000)
        with patch("src.utils.llm.llm_chat", return_value={"coach_quoted": False}) as mock_chat:
            LLMQuoteExtractor().assess_coverage("Diego Simeone", [doc])
        self.assertLess(len(mock_chat.call_args[0][1]), 20000)
