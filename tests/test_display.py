"""U4: the terminal leaderboard derives from calculate_rankings."""

import io
import unittest
from unittest import mock

from src.display import show_leaderboard


TEAMS = [
    {"team": "Alavés", "coach": "A"},
    {"team": "Getafe", "coach": "B"},
]
GAMES = [
    {"game_id": "1", "date": "2026-08-15", "home_team": "Alavés",
     "away_team": "Getafe", "home_coach": "A", "away_coach": "B"},
]


class TestShowLeaderboard(unittest.TestCase):
    def _show(self, comments, mode="separate"):
        out = io.StringIO()
        with mock.patch("src.display.get_comments", return_value=comments), \
             mock.patch("src.display.get_teams", return_value=TEAMS), \
             mock.patch("src.grading.grader.get_teams", return_value=TEAMS), \
             mock.patch("src.grading.grader.get_games", return_value=GAMES), \
             mock.patch("sys.stdout", new=out):
            show_leaderboard(mode)
        return out.getvalue()

    def test_separate_mode_table(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 3},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 0},
        ]
        table = self._show(comments)
        self.assertIn("Alavés", table)
        self.assertIn("Getafe", table)
        # Alavés row: home points from the home coach's score.
        self.assertRegex(table, r"Alavés\s*\|\s*3\s*\|\s*1\s*\|\s*3\s*\|\s*0")

    def test_competitive_mode_winner_gets_three(self):
        comments = [
            {"game_id": "1", "coach": "A", "quote": "q", "score": 0},
            {"game_id": "1", "coach": "B", "quote": "q", "score": 3},
        ]
        table = self._show(comments, mode="competitive")
        # Getafe (away) wins the matchup: 3 away points.
        self.assertRegex(table, r"Getafe\s*\|\s*3\s*\|\s*1\s*\|\s*0\s*\|\s*3")

    def test_missing_scores_warning(self):
        comments = [{"game_id": "1", "coach": "A", "quote": "q"}]
        table = self._show(comments)
        self.assertIn("WARNING", table)


if __name__ == "__main__":
    unittest.main()
