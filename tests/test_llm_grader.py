"""Unit tests for grade_quote with a mocked LLM backend."""
import unittest
from unittest import mock
from unittest.mock import patch

from src.grading.grader import grade_quote, heuristic_grade


class TestGradeQuoteLLMPath(unittest.TestCase):
    def test_llm_score_three(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={
                 "score": 3, "justification": "Praises the referee's work."
             }) as mock_chat:
            score, graded_by, justification = grade_quote("El árbitro lo hizo bien")
        self.assertEqual(score, 3)
        self.assertEqual(graded_by, "llm")
        self.assertEqual(justification, "Praises the referee's work.")
        mock_chat.assert_called_once()
        args, kwargs = mock_chat.call_args
        self.assertIn("El árbitro lo hizo bien", args[1])
        self.assertTrue(kwargs.get("json_mode"))
        self.assertEqual(kwargs.get("temperature"), 0.0)

    def test_llm_score_one(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={"score": 1, "justification": "Neutral."}):
            self.assertEqual(grade_quote("No comento el arbitraje")[:2], (1, "llm"))

    def test_llm_score_zero(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={"score": 0, "justification": "Accuses bias."}):
            self.assertEqual(grade_quote("Ha sido un robo")[:2], (0, "llm"))

    def test_llm_score_as_string_is_accepted(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={"score": "3", "justification": "ok"}):
            self.assertEqual(grade_quote("Bien arbitrado")[:2], (3, "llm"))

    def test_invalid_score_falls_back_to_heuristic(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={"score": 2, "justification": "?"}):
            score, graded_by, justification = grade_quote("El árbitro lo hizo bien, gran trabajo")
        self.assertEqual(graded_by, "heuristic")
        self.assertEqual(score, heuristic_grade("El árbitro lo hizo bien, gran trabajo"))
        self.assertEqual(justification, "keyword heuristic")

    def test_non_numeric_score_falls_back_to_heuristic(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", return_value={"score": "three", "justification": "?"}):
            score, graded_by, _ = grade_quote("Ha sido un robo, una vergüenza")
        self.assertEqual(graded_by, "heuristic")
        self.assertEqual(score, 0)

    def test_llm_error_falls_back_to_heuristic(self):
        with patch("src.utils.llm.llm_available", return_value=True), \
             patch("src.utils.llm.llm_chat", side_effect=RuntimeError("connection refused")):
            score, graded_by, justification = grade_quote("El árbitro lo hizo bien, gran trabajo")
        self.assertEqual(graded_by, "heuristic")
        self.assertEqual(score, 3)
        self.assertEqual(justification, "keyword heuristic")

    def test_no_llm_key_uses_heuristic_without_calling_llm(self):
        with patch("src.utils.llm.llm_available", return_value=False), \
             patch("src.utils.llm.llm_chat") as mock_chat:
            score, graded_by, justification = grade_quote("El árbitro lo hizo bien, gran trabajo")
        mock_chat.assert_not_called()
        self.assertEqual((score, graded_by), (3, "heuristic"))

    def test_returned_scores_are_always_valid(self):
        for quote in ["Ha sido un robo", "No comento nada", "Gran trabajo del árbitro"]:
            with patch("src.utils.llm.llm_available", return_value=False):
                score, _, _ = grade_quote(quote)
            self.assertIn(score, (0, 1, 3))


if __name__ == "__main__":
    unittest.main()


class TestLLMConfig(unittest.TestCase):
    def test_requires_all_three_variables(self):
        import os
        from src.utils.llm import llm_available
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "k"}, clear=True):
            self.assertFalse(llm_available())
        with mock.patch.dict(os.environ, {
            "LLM_API_KEY": "k", "LLM_BASE_URL": "https://llm.example", "LLM_MODEL": "m",
        }, clear=True):
            self.assertTrue(llm_available())
