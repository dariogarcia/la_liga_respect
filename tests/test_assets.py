import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _relative_luminance(hex_color):
    color = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(color[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(color_a, color_b):
    la, lb = sorted(
        (_relative_luminance(color_a), _relative_luminance(color_b)), reverse=True
    )
    return (la + 0.05) / (lb + 0.05)


class TestTeamAssets(unittest.TestCase):
    def setUp(self):
        self.teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))
        self.assets_dir = ROOT / "assets" / "teams"

    def _badge(self, team):
        # The local fallback badge that ships with the site; the UI uses
        # it when the remote crest fails to load.
        return self.assets_dir / f"{team['id']}.svg"

    def test_every_team_has_fallback_badge(self):
        for team in self.teams:
            self.assertTrue(
                self._badge(team).exists(),
                f"Missing fallback badge for {team['id']}: assets/teams/{team['id']}.svg",
            )

    def test_logo_is_espn_cdn_or_local(self):
        # Product decision (2026-10): teams.json carries the official
        # crest served by ESPN's public CDN; local badge paths are also
        # accepted as a legacy/interim value. Anything else (other
        # hosts, http, protocol-relative) is rejected.
        for team in self.teams:
            logo = team.get("logo", "")
            self.assertTrue(
                logo.startswith("https://a.espncdn.com/")
                or logo.startswith("assets/teams/"),
                f"Unexpected logo for {team['id']}: {logo}",
            )

    def test_default_badge_exists(self):
        self.assertTrue((self.assets_dir / "default.svg").exists())

    def test_badges_are_valid_svg(self):
        for team in self.teams:
            content = self._badge(team).read_text(encoding="utf-8")
            self.assertIn("<svg", content, f"{team['id']} badge is not an SVG")
            self.assertIn("</svg>", content, f"{team['id']} badge is truncated")

    def test_index_references_default_badge(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("assets/teams/default.svg", html)

    def test_badges_are_initials_style_not_club_crests(self):
        # The locally generated fallbacks are text/initials based SVGs;
        # a real club crest smuggled in would typically be a heavy
        # embedded raster.
        for team in self.teams:
            content = self._badge(team).read_text(encoding="utf-8")
            self.assertNotIn(
                "data:image",
                content,
                f"{team['id']} badge embeds raster data (club crest?)",
            )
            self.assertLess(
                len(content),
                20000,
                f"{team['id']} badge is suspiciously large for an initials badge",
            )

    def test_badge_text_contrasts_with_both_halves(self):
        # Regression: initials must be legible on the primary circle AND
        # the secondary half. White-on-white (Real Madrid) or
        # white-on-orange (Valencia) letters are invisible; the fill or
        # its halo stroke must clear a 3:1 WCAG ratio on each half.
        for team in self.teams:
            content = self._badge(team).read_text(encoding="utf-8")
            primary = re.search(
                r'<circle[^>]*fill="(#[0-9A-Fa-f]{6})"', content).group(1)
            secondary = re.search(
                r'<path[^>]*fill="(#[0-9A-Fa-f]{6})"', content).group(1)
            text = re.search(
                r'<text[^>]*fill="(#[0-9A-Fa-f]{6})"', content).group(1)
            halo = re.search(r'<text[^>]*stroke="(#[0-9A-Fa-f]{6})"', content)
            halo = halo.group(1) if halo else None
            for bg in (primary, secondary):
                legible = _contrast_ratio(text, bg) >= 3.0 or (
                    halo and _contrast_ratio(halo, bg) >= 3.0
                )
                self.assertTrue(
                    legible,
                    f"{team['id']}: initials ({text}, halo {halo}) invisible "
                    f"on badge half {bg}",
                )


if __name__ == "__main__":
    unittest.main()
