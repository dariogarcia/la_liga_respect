"""Generates stylized SVG badges for every team in data/teams.json.

The badges are simple two-color circles with the team abbreviation, so the
web UI has logos without shipping trademarked club crests. Rerun this
script after changing teams.json:

    python3 scripts/generate_badges.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "teams"

# id -> (abbreviation, primary color, secondary color, text color)
TEAM_STYLES = {
    "alaves": ("ALA", "#0761AF", "#FFFFFF", "#FFFFFF"),
    "athletic-bilbao": ("ATH", "#EE2523", "#FFFFFF", "#FFFFFF"),
    "atletico-madrid": ("ATM", "#CB3524", "#FFFFFF", "#FFFFFF"),
    "barcelona": ("BAR", "#A50044", "#004D98", "#FFFFFF"),
    "celta-vigo": ("CEL", "#8AC3EE", "#FFFFFF", "#083D66"),
    "deportivo-a-coruna": ("DEP", "#0072CE", "#FFFFFF", "#FFFFFF"),
    "elche": ("ELC", "#00963F", "#FFFFFF", "#FFFFFF"),
    "espanyol": ("ESP", "#0055A5", "#FFFFFF", "#FFFFFF"),
    "getafe": ("GET", "#005999", "#B4053F", "#FFFFFF"),
    "levante": ("LEV", "#005AAB", "#B4053F", "#FFFFFF"),
    "malaga": ("MAL", "#0E4E9C", "#FFFFFF", "#FFFFFF"),
    "osasuna": ("OSA", "#D91A21", "#0A346F", "#FFFFFF"),
    "racing-santander": ("RAC", "#00953B", "#FFFFFF", "#FFFFFF"),
    "rayo-vallecano": ("RAY", "#E53027", "#FFFFFF", "#FFFFFF"),
    "real-betis": ("BET", "#00954C", "#FFFFFF", "#FFFFFF"),
    "real-sociedad": ("RSO", "#0067B1", "#FFFFFF", "#FFFFFF"),
    "real-madrid": ("RMA", "#FFFFFF", "#00529F", "#00529F"),
    "sevilla": ("SEV", "#D00027", "#FFFFFF", "#FFFFFF"),
    "valencia": ("VAL", "#F18E00", "#000000", "#FFFFFF"),
    "villarreal": ("VIL", "#FFE667", "#005187", "#003B66"),
}

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <circle cx="32" cy="32" r="30" fill="{primary}"/>
  <path d="M 32 2 A 30 30 0 0 1 32 62 Z" fill="{secondary}"/>
  <circle cx="32" cy="32" r="30" fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="2"/>
  <text x="32" y="40" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="{font_size}" fill="{text_color}">{abbr}</text>
</svg>
"""

DEFAULT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <circle cx="32" cy="32" r="30" fill="#8A9BA8"/>
  <path d="M 32 2 A 30 30 0 0 1 32 62 Z" fill="#6B7B87"/>
  <circle cx="32" cy="32" r="30" fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="2"/>
  <text x="32" y="41" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="30" fill="#FFFFFF">?</text>
</svg>
"""


def generate_all():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))

    generated = 0
    for team in teams:
        style = TEAM_STYLES.get(team["id"])
        if style is None:
            print(f"No style for team '{team['id']}', skipping.")
            continue
        abbr, primary, secondary, text_color = style
        font_size = 26 if len(abbr) <= 2 else 21
        svg = SVG_TEMPLATE.format(
            primary=primary, secondary=secondary,
            text_color=text_color, abbr=abbr, font_size=font_size,
        )
        (ASSETS_DIR / f"{team['id']}.svg").write_text(svg, encoding="utf-8")
        generated += 1

    (ASSETS_DIR / "default.svg").write_text(DEFAULT_SVG, encoding="utf-8")
    print(f"Generated {generated} team badges + default.svg in {ASSETS_DIR}")


if __name__ == "__main__":
    generate_all()
