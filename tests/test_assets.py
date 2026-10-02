import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestTeamAssets(unittest.TestCase):
    def setUp(self):
        self.teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
        self.assets_dir = ROOT / "assets" / "teams"

    def test_every_team_has_logo_file(self):
        for team in self.teams:
            logo_path = ROOT / team["logo"]
            self.assertTrue(
                logo_path.exists(),
                f"Missing logo file for {team['id']}: {team['logo']}",
            )

    def test_logo_paths_follow_convention(self):
        for team in self.teams:
            self.assertEqual(
                team["logo"],
                f"assets/teams/{team['id']}.svg",
                f"Unexpected logo path for {team['id']}",
            )

    def test_default_badge_exists(self):
        self.assertTrue((self.assets_dir / "default.svg").exists())

    def test_logos_are_valid_svg(self):
        for team in self.teams:
            content = (ROOT / team["logo"]).read_text(encoding="utf-8")
            self.assertIn("<svg", content, f"{team['id']} logo is not an SVG")
            self.assertIn("</svg>", content, f"{team['id']} logo is truncated")

    def test_index_references_default_badge(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("assets/teams/default.svg", html)

    def test_logos_are_local_no_external_crests(self):
        # C7 regression: badges must stay locally generated files, never
        # hot-linked club crests (copyright + tracking + availability).
        for team in self.teams:
            logo = team["logo"]
            self.assertFalse(
                logo.startswith(("http://", "https://", "//")),
                f"{team['id']} points to an external logo: {logo}",
            )
            self.assertTrue(
                logo.startswith("assets/teams/"),
                f"{team['id']} logo is not under assets/teams/: {logo}",
            )

    def test_badges_are_initials_style_not_club_crests(self):
        # C7: generated badges are text/initials based SVGs; a real club
        # crest smuggled in would typically be a heavy embedded raster.
        for team in self.teams:
            content = (ROOT / team["logo"]).read_text(encoding="utf-8")
            self.assertNotIn(
                "data:image",
                content,
                f"{team['id']} logo embeds raster data (club crest?)",
            )
            self.assertLess(
                len(content),
                20000,
                f"{team['id']} logo is suspiciously large for an initials badge",
            )


if __name__ == "__main__":
    unittest.main()
