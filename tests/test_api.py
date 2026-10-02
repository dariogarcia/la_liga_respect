import unittest

from src.utils.api import ESPNLaLigaAPI


def _event(home_name="Deportivo Alavés", away_name="Getafe",
           home_logo="https://a.espncdn.com/i/teamlogos/soccer/500/95.png",
           away_logo="https://a.espncdn.com/i/teamlogos/soccer/500/93.png"):
    return {
        "id": 12345,
        "date": "2026-08-15T19:00:00Z",
        "status": {"type": {"name": "STATUS_FULL_TIME"}},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": home_name, "logo": home_logo}},
                {"homeAway": "away", "team": {"displayName": away_name, "logo": away_logo}},
            ],
        }],
    }


class TestExtractMatchLogos(unittest.TestCase):
    def setUp(self):
        self.api = ESPNLaLigaAPI.__new__(ESPNLaLigaAPI)  # no network in __init__

    def test_captures_crest_urls(self):
        match = self.api._extract_match(_event())
        self.assertEqual(match["homeLogo"], "https://a.espncdn.com/i/teamlogos/soccer/500/95.png")
        self.assertEqual(match["awayLogo"], "https://a.espncdn.com/i/teamlogos/soccer/500/93.png")

    def test_missing_or_non_https_logos_become_none(self):
        match = self.api._extract_match(_event(home_logo=None, away_logo="assets/teams/getafe.svg"))
        self.assertIsNone(match["homeLogo"])
        self.assertIsNone(match["awayLogo"])

    def test_alias_still_applied_to_names(self):
        match = self.api._extract_match(_event(home_name="Athletic Club"))
        self.assertEqual(match["homeTeam"], "Athletic Bilbao")
        self.assertEqual(match["homeLogo"], "https://a.espncdn.com/i/teamlogos/soccer/500/95.png")


if __name__ == "__main__":
    unittest.main()
