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


def _load_i18n(html):
    # The I18N dictionary in index.html is kept pure JSON between
    # marker comments so it can be parsed and checked here.
    match = re.search(
        r"/\* I18N:START \*/\s*(const I18N = .*?);\s*/\* I18N:END \*/",
        html,
        re.S,
    )
    if not match:
        raise AssertionError("I18N block not found in index.html")
    return json.loads(match.group(1)[len("const I18N = "):])


class TestI18n(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.i18n = _load_i18n(self.html)

    def test_three_languages_with_identical_keys(self):
        self.assertEqual(
            sorted(self.i18n.keys()), ["ca", "en", "es"],
            "I18N must define exactly en/es/ca",
        )
        en, es, ca = (set(self.i18n[l].keys()) for l in ("en", "es", "ca"))
        self.assertEqual(en, es, f"es keys differ: only-es={sorted(es - en)}, only-en={sorted(en - es)}")
        self.assertEqual(en, ca, f"ca keys differ: only-ca={sorted(ca - en)}, only-en={sorted(en - ca)}")

    def test_placeholders_match_across_languages(self):
        def placeholders(value):
            return sorted(re.findall(r"\{(\w+)\}", value))
        for key, en_value in self.i18n["en"].items():
            self.assertEqual(
                placeholders(en_value),
                placeholders(self.i18n["es"][key]),
                f"es '{key}' placeholder mismatch",
            )
            self.assertEqual(
                placeholders(en_value),
                placeholders(self.i18n["ca"][key]),
                f"ca '{key}' placeholder mismatch",
            )

    def test_every_markup_reference_resolves(self):
        # Every data-i18n(-html/-title/-placeholder/-aria) attribute in
        # the static markup must name an existing key.
        referenced = set(re.findall(
            r'data-i18n(?:-html|-title|-placeholder|-aria)?="([a-z0-9_]+)"',
            self.html,
        ))
        self.assertTrue(referenced)
        for key in referenced:
            self.assertIn(key, self.i18n["en"], f"markup references unknown key '{key}'")

    def test_every_t_literal_resolves(self):
        # Every t('key', ...) call in the script must name an existing
        # key. Runtime-composed keys (duel_*, movement_*_one/many,
        # mode_blurb_*, pending_*_one/many) are whitelisted.
        dynamic = {
            "duel_won", "duel_drew", "duel_lost", "duel_solo",
            "duel_won_title", "duel_drew_title", "duel_lost_title", "duel_solo_title",
            "movement_up_one", "movement_up_many",
            "movement_down_one", "movement_down_many",
            "mode_blurb_season", "mode_blurb_h2h",
            "pending_note_coach_one", "pending_note_coach_many",
            "pending_summary_active_one", "pending_summary_active_many",
        }
        for key in dynamic:
            self.assertIn(key, self.i18n["en"], f"missing runtime-composed key '{key}'")
        called = set(re.findall(r"\bt\('([a-z0-9_]+)'", self.html))
        for key in called - dynamic:
            self.assertIn(key, self.i18n["en"], f"t() references unknown key '{key}'")

    def test_language_switcher_present(self):
        self.assertIn("lang-btn", self.html)
        self.assertIn("setLang('es')", self.html)
        self.assertIn("setLang('ca')", self.html)


if __name__ == "__main__":
    unittest.main()
