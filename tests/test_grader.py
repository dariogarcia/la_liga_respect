import unittest
from unittest import mock

from src.grading.grader import heuristic_grade, merge_comments, calculate_rankings


class TestHeuristicGrade(unittest.TestCase):
    def test_disrespectful(self):
        self.assertEqual(heuristic_grade("Ha sido un saqueo, el árbitro nos ha robado"), 0)
        self.assertEqual(heuristic_grade("No nos tratan de la misma manera, es un escándalo"), 0)

    def test_respectful(self):
        self.assertEqual(heuristic_grade("El árbitro lo hizo bien, un gran trabajo"), 3)
        self.assertEqual(
            heuristic_grade("No quiero culpar al árbitro, los errores son parte del fútbol"), 3
        )

    def test_neutral(self):
        self.assertEqual(heuristic_grade("Hemos jugado a un buen nivel hoy"), 1)
        self.assertEqual(heuristic_grade("El colegiado pitó un penalti dudoso"), 1)


class TestMergeComments(unittest.TestCase):
    def test_merges_quotes_per_game_and_coach(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "primera parte"},
            {"game_id": "1", "coach": "A", "quote": "segunda parte", "score": 1},
            {"game_id": "1", "coach": "B", "quote": "otro"},
            {"game_id": "2", "coach": "A", "quote": "otro juego"},
        ]
        merged = merge_comments(comments)
        self.assertEqual(len(merged), 3)
        a1 = next(c for c in merged if c["game_id"] == "1" and c["coach"] == "A")
        self.assertEqual(a1["quote"], "primera parte segunda parte")
        self.assertNotIn("score", a1)

    def test_all_scored_sums_scores(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "x", "score": 3},
            {"game_id": "1", "coach": "A", "quote": "y", "score": 0},
        ]
        merged = merge_comments(comments)
        self.assertEqual(merged[0]["score"], 3)

    def test_merges_sources(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "x", "source_url": "https://a/1", "sources": ["https://a/1"]},
            {"game_id": "1", "coach": "A", "quote": "y", "source_url": "https://a/2", "sources": ["https://a/2"]},
        ]
        merged = merge_comments(comments)
        self.assertEqual(merged[0]["sources"], ["https://a/1", "https://a/2"])
        self.assertEqual(merged[0]["source_url"], "https://a/1")


class TestCalculateRankings(unittest.TestCase):
    TEAMS = [
        {"team": "Alavés", "coach": "A"},
        {"team": "Getafe", "coach": "B"},
        {"team": "Espanyol", "coach": "C"},
    ]
    GAMES = [
        {"game_id": "1", "date": "2026-08-15", "home_team": "Alavés", "away_team": "Getafe",
         "home_coach": "A", "away_coach": "B"},
        {"game_id": "2", "date": "2026-08-16", "home_team": "Espanyol", "away_team": "Alavés",
         "home_coach": "C", "away_coach": "A"},
    ]

    def _rankings(self, comments, mode):
        with mock.patch("src.grading.grader.get_teams", return_value=self.TEAMS), \
             mock.patch("src.grading.grader.get_games", return_value=self.GAMES):
            return calculate_rankings(comments, mode=mode)

    def test_separate_mode(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 0},
            {"game_id": "2", "coach": "C", "quote": "q", "score": 1},
        ]
        rankings, incomplete = self._rankings(comments, "separate")
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)
        self.assertEqual(points["B"], 0)
        self.assertEqual(points["C"], 1)
        self.assertEqual(incomplete, [])

    def test_competitive_mode(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 0},
            {"game_id": "2", "coach": "C", "quote": "q", "score": 1},
            {"game_id": "2", "coach": "A", "quote": "q", "score": 1},
        ]
        rankings, incomplete = self._rankings(comments, "competitive")
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 4)
        self.assertEqual(points["B"], 0)
        self.assertEqual(points["C"], 1)

    def test_competitive_flags_incomplete_game(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
        ]
        rankings, incomplete = self._rankings(comments, "competitive")
        self.assertEqual(len(incomplete), 1)
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)

    def test_unscored_quotes_flagged_and_skipped(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
            {"game_id": "1", "coach": "B", "quote": "q"},
        ]
        rankings, incomplete = self._rankings(comments, "separate")
        self.assertEqual(len(incomplete), 1)
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)
        self.assertEqual(points["B"], 0)

    def test_three_quotes_per_game_supported(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 1},
            {"game_id": "1", "coach": "A", "quote": "q", "score": 1},
            {"game_id": "1", "coach": "A", "quote": "q", "score": 1},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 0},
        ]
        merged = merge_comments(comments)
        rankings, incomplete = self._rankings(merged, "competitive")
        self.assertEqual(incomplete, [])
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)
        self.assertEqual(points["B"], 0)

    def test_departed_coach_keeps_points_and_team(self):
        teams = [
            {"team": "Alavés", "coach": "New Coach",
             "coach_history": [{"coach": "A", "until": "2026-09-01"}]},
            {"team": "Getafe", "coach": "B"},
        ]
        games = [
            {"game_id": "1", "date": "2026-08-15", "home_team": "Alavés", "away_team": "Getafe",
             "home_coach": "A", "away_coach": "B"},
        ]
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 1},
        ]
        with mock.patch("src.grading.grader.get_teams", return_value=teams), \
             mock.patch("src.grading.grader.get_games", return_value=games):
            rankings, _ = calculate_rankings(comments, mode="separate")
        by_coach = {r["coach"]: r for r in rankings}
        self.assertIn("A", by_coach)
        self.assertEqual(by_coach["A"]["points"], 3)
        self.assertEqual(by_coach["A"]["team"], "Alavés")
        self.assertIn("New Coach", by_coach)
        self.assertEqual(by_coach["New Coach"]["points"], 0)

    def test_departed_coach_without_games_is_omitted(self):
        teams = [
            {"team": "Alavés", "coach": "New Coach",
             "coach_history": [{"coach": "Old", "until": "2026-09-01"}]},
        ]
        with mock.patch("src.grading.grader.get_teams", return_value=teams), \
             mock.patch("src.grading.grader.get_games", return_value=[]):
            rankings, _ = calculate_rankings([], mode="separate")
        coaches = {r["coach"] for r in rankings}
        self.assertNotIn("Old", coaches)
        self.assertIn("New Coach", coaches)


if __name__ == "__main__":
    unittest.main()


class TestCleanEntriesInRankings(unittest.TestCase):
    """no_ref_comment entries (score 3, graded_by=coverage) flow through
    both ranking modes like any scored quote."""

    TEAMS = [
        {"team": "Alavés", "coach": "A"},
        {"team": "Getafe", "coach": "B"},
    ]
    GAMES = [
        {"game_id": "1", "date": "2026-08-15", "home_team": "Alavés", "away_team": "Getafe",
         "home_coach": "A", "away_coach": "B"},
    ]

    def _rankings(self, comments, mode):
        with mock.patch("src.grading.grader.get_teams", return_value=self.TEAMS), \
             mock.patch("src.grading.grader.get_games", return_value=self.GAMES):
            return calculate_rankings(comments, mode=mode)

    def _clean(self, coach, kind="presumed"):
        return {
            "game_id": "1", "coach": coach, "quote": "",
            "no_ref_comment": True, "kind": kind, "score": 3,
            "graded_by": "coverage", "justification": "no referee comment",
        }

    def test_separate_mode_counts_clean_as_three(self):
        comments = [self._clean("A"), {"game_id": "1", "coach": "B", "quote": "q", "score": 0}]
        rankings, _ = self._rankings(comments, "separate")
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)
        self.assertEqual(points["B"], 0)

    def test_competitive_mode_silent_coach_beats_complainer(self):
        comments = [self._clean("A"), {"game_id": "1", "coach": "B", "quote": "q", "score": 0}]
        rankings, incomplete = self._rankings(comments, "competitive")
        self.assertEqual(incomplete, [])
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 3)  # silence wins the duel
        self.assertEqual(points["B"], 0)

    def test_both_clean_is_a_draw(self):
        comments = [self._clean("A"), self._clean("B", kind="confirmed")]
        rankings, _ = self._rankings(comments, "competitive")
        points = {r["coach"]: r["points"] for r in rankings}
        self.assertEqual(points["A"], 1)
        self.assertEqual(points["B"], 1)
