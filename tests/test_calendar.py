import unittest
from datetime import datetime
from unittest import mock

from src.collection import calendar
from src.collection.calendar import (
    normalize_name,
    distinctive_tokens,
    match_score,
    find_team,
    utcdate_to_date,
    resolve_coach,
    sync_finished_games,
)


class TestTeamMatching(unittest.TestCase):
    def test_normalize_strips_accents(self):
        self.assertEqual(normalize_name("Alavés"), "alaves")
        self.assertEqual(normalize_name("Atlético  Madrid"), "atletico madrid")

    def test_match_score_deportivo_alaves(self):
        self.assertGreaterEqual(match_score("Deportivo Alavés", "Alavés"), 0.5)

    def test_match_score_disambiguates_real_teams(self):
        self.assertEqual(match_score("Real Madrid", "Real Betis"), 0.0)
        self.assertEqual(match_score("Real Madrid", "Real Madrid"), 1.0)

    def test_find_team(self):
        teams = [
            {"team": "Alavés", "coach": "QSFF"},
            {"team": "Real Betis", "coach": "Pellegrini"},
            {"team": "Real Madrid", "coach": "X"},
        ]
        self.assertEqual(find_team("Deportivo Alavés", teams)["coach"], "QSFF")
        self.assertIsNone(find_team("Barcelona", teams))

    def test_find_team_disambiguates_madrid_clubs(self):
        # Regression: token matching alone maps "Real Madrid" to
        # "Atlético Madrid" (both reduce to {madrid}); the exact
        # normalized match must win.
        teams = [
            {"team": "Atlético Madrid", "coach": "Simeone"},
            {"team": "Real Madrid", "coach": "Mourinho"},
        ]
        self.assertEqual(find_team("Real Madrid", teams)["coach"], "Mourinho")
        self.assertEqual(find_team("Atlético Madrid", teams)["coach"], "Simeone")
        self.assertEqual(find_team("Atletico Madrid", teams)["coach"], "Simeone")

    def test_utcdate_to_date(self):
        self.assertEqual(utcdate_to_date("2026-08-15T19:00:00Z"), "2026-08-15")


class TestResolveCoach(unittest.TestCase):
    TEAM = {
        "team": "Alavés",
        "coach": "New Coach",
        "coach_history": [
            {"coach": "Old Coach", "until": "2026-09-20"},
        ],
    }
    MULTI = {
        "team": "Getafe",
        "coach": "Current",
        "coach_history": [
            {"coach": "First", "until": "2025-06-30"},
            {"coach": "Second", "until": "2026-09-10"},
        ],
    }

    def test_before_recorded_history_returns_earliest(self):
        self.assertEqual(resolve_coach(self.MULTI, "2024-10-01"), "First")

    def test_within_last_tenure(self):
        self.assertEqual(resolve_coach(self.MULTI, "2026-09-01"), "Second")

    def test_after_all_tenures_returns_current(self):
        self.assertEqual(resolve_coach(self.MULTI, "2026-10-01"), "Current")
        self.assertEqual(resolve_coach(self.TEAM, "2026-09-21"), "New Coach")

    def test_tenure_end_date_is_inclusive(self):
        self.assertEqual(resolve_coach(self.TEAM, "2026-09-20"), "Old Coach")

    def test_no_history_returns_current(self):
        team = {"team": "X", "coach": "Only Coach"}
        self.assertEqual(resolve_coach(team, "2026-01-01"), "Only Coach")


class TestSyncFinishedGames(unittest.TestCase):
    TEAMS = [
        {"team": "Alavés", "coach": "Coach A"},
        {"team": "Getafe", "coach": "Coach B"},
        {"team": "Real Madrid", "coach": "Coach C"},
        {"team": "Barcelona", "coach": "Coach D"},
    ]

    def _fake_api(self):
        class FakeAPI:
            def __init__(self, api_key):
                pass

            def get_finished_matches(self):
                return [
                    {"match_id": "100", "utcDate": "2026-08-15T19:00:00Z", "status": "FINISHED",
                     "homeTeam": "Deportivo Alavés", "awayTeam": "Getafe"},
                    {"match_id": "101", "utcDate": "2026-08-16T19:00:00Z", "status": "FINISHED",
                     "homeTeam": "Real Madrid", "awayTeam": "Barcelona"},
                ]
        return FakeAPI

    def test_sync_adds_finished_matches_with_coaches(self):
        saved = {}
        with mock.patch("src.collection.calendar.LaLigaAPI", self._fake_api()), \
             mock.patch("src.collection.calendar.get_games", return_value=[]), \
             mock.patch("src.collection.calendar.get_teams", return_value=self.TEAMS), \
             mock.patch("src.collection.calendar.save_games", side_effect=lambda g: saved.update({"games": g})):
            stats = sync_finished_games(api_key="key")

        self.assertEqual(stats["added"], 2)
        games = saved["games"]
        by_id = {g["game_id"]: g for g in games}
        self.assertEqual(by_id["fd-100"]["home_coach"], "Coach A")
        self.assertEqual(by_id["fd-100"]["away_coach"], "Coach B")
        self.assertEqual(by_id["fd-101"]["home_coach"], "Coach C")
        self.assertEqual(by_id["fd-100"]["date"], "2026-08-15")

    def test_sync_skips_known_game_ids_and_pairs(self):
        existing = [{
            "game_id": "fd-100", "date": "2026-08-15",
            "home_team": "Alavés", "away_team": "Getafe",
            "home_coach": "Coach A", "away_coach": "Coach B",
        }]
        with mock.patch("src.collection.calendar.LaLigaAPI", self._fake_api()), \
             mock.patch("src.collection.calendar.get_games", return_value=existing), \
             mock.patch("src.collection.calendar.get_teams", return_value=self.TEAMS), \
             mock.patch("src.collection.calendar.save_games") as save_mock:
            stats = sync_finished_games(api_key="key")

        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["already_known"], 1)
        save_mock.assert_called_once()

    def test_sync_without_key_falls_back_to_espn(self):
        class FakeESPNAPI:
            def __init__(self, start_date, end_date):
                self.start_date = start_date
                self.end_date = end_date

            def get_finished_matches(self):
                return [
                    {"match_id": "200", "utcDate": "2026-08-15T19:00:00Z", "status": "STATUS_FULL_TIME",
                     "homeTeam": "Deportivo Alavés", "awayTeam": "Getafe"},
                ]

        saved = {}
        with mock.patch("src.collection.calendar.ESPNLaLigaAPI", FakeESPNAPI), \
             mock.patch("src.collection.calendar.get_games", return_value=[]), \
             mock.patch("src.collection.calendar.get_teams", return_value=self.TEAMS), \
             mock.patch("src.collection.calendar.save_games", side_effect=lambda g: saved.update({"games": g})):
            stats = sync_finished_games(api_key=None)

        self.assertIsNone(stats["error"])
        self.assertIn("ESPN", stats["source"])
        self.assertEqual(stats["added"], 1)
        game = saved["games"][0]
        self.assertEqual(game["game_id"], "espn-200")
        self.assertEqual(game["home_coach"], "Coach A")
        self.assertEqual(game["away_coach"], "Coach B")

    def test_sync_reports_error_when_no_matches_retrieved(self):
        class EmptyAPI:
            def __init__(self, api_key):
                pass

            def get_finished_matches(self):
                return []

        with mock.patch("src.collection.calendar.LaLigaAPI", EmptyAPI), \
             mock.patch("src.collection.calendar.get_games", return_value=[]), \
             mock.patch("src.collection.calendar.get_teams", return_value=self.TEAMS):
            stats = sync_finished_games(api_key="key")

        self.assertEqual(stats["added"], 0)
        self.assertIsNotNone(stats["error"])


if __name__ == "__main__":
    unittest.main()
