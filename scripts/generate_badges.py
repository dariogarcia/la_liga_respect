"""Generates stylized SVG badges for every team in data/teams.json.

The badges are simple two-color circles with the team abbreviation, so the
web UI has logos without shipping trademarked club crests. Rerun this
script after changing teams.json:

    python3 scripts/generate_badges.py

Text legibility is automatic: the abbreviation color is chosen by WCAG
relative luminance against BOTH background colors (primary circle and
secondary half), and a contrasting halo stroke guarantees the letters
remain readable wherever they cross onto the other half. Teams whose
colors include white (Real Madrid) or light yellow (Villarreal) get dark
letters instead of invisible white-on-white ones.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets" / "teams"

# id -> (abbreviation, primary color, secondary color).
# The text color is computed automatically for contrast.
TEAM_STYLES = {
    "alaves": ("ALA", "#0761AF", "#FFFFFF"),
    "athletic-bilbao": ("ATH", "#EE2523", "#FFFFFF"),
    "atletico-madrid": ("ATM", "#CB3524", "#FFFFFF"),
    "barcelona": ("BAR", "#A50044", "#004D98"),
    "celta-vigo": ("CEL", "#8AC3EE", "#FFFFFF"),
    "deportivo-a-coruna": ("DEP", "#0072CE", "#FFFFFF"),
    "elche": ("ELC", "#00963F", "#FFFFFF"),
    "espanyol": ("ESP", "#0055A5", "#FFFFFF"),
    "getafe": ("GET", "#005999", "#B4053F"),
    "levante": ("LEV", "#005AAB", "#B4053F"),
    "malaga": ("MAL", "#0E4E9C", "#FFFFFF"),
    "osasuna": ("OSA", "#D91A21", "#0A346F"),
    "racing-santander": ("RAC", "#00953B", "#FFFFFF"),
    "rayo-vallecano": ("RAY", "#E53027", "#FFFFFF"),
    "real-betis": ("BET", "#00954C", "#FFFFFF"),
    "real-sociedad": ("RSO", "#0067B1", "#FFFFFF"),
    "real-madrid": ("RMA", "#FFFFFF", "#00529F"),
    "sevilla": ("SEV", "#D00027", "#FFFFFF"),
    "valencia": ("VAL", "#F18E00", "#000000"),
    "villarreal": ("VIL", "#FFE667", "#005187"),
}

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <circle cx="32" cy="32" r="30" fill="{primary}"/>
  <path d="M 32 2 A 30 30 0 0 1 32 62 Z" fill="{secondary}"/>
  <circle cx="32" cy="32" r="30" fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="2"/>
  <text x="32" y="40" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="{font_size}" fill="{text_color}" stroke="{halo_color}" stroke-width="{halo_width}" paint-order="stroke" stroke-linejoin="round">{abbr}</text>
</svg>
"""

DEFAULT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <circle cx="32" cy="32" r="30" fill="#8A9BA8"/>
  <path d="M 32 2 A 30 30 0 0 1 32 62 Z" fill="#6B7B87"/>
  <circle cx="32" cy="32" r="30" fill="none" stroke="rgba(0,0,0,0.25)" stroke-width="2"/>
  <text x="32" y="41" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="700" font-size="30" fill="#FFFFFF" stroke="#000000" stroke-width="1.5" paint-order="stroke" stroke-linejoin="round">?</text>
</svg>
"""


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of an sRGB hex color."""
    color = hex_color.lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(color[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a: str, color_b: str) -> float:
    """WCAG contrast ratio between two hex colors (1..21)."""
    la, lb = sorted(
        (_relative_luminance(color_a), _relative_luminance(color_b)), reverse=True
    )
    return (la + 0.05) / (lb + 0.05)


def text_colors(primary: str, secondary: str):
    """Pick letter + halo colors readable on both background halves.

    The letter color maximizes the worst-case WCAG contrast against the
    primary circle and the secondary half; the halo is its inverse, so
    letters crossing onto the other half keep a visible outline.
    """
    best, best_score = "#FFFFFF", -1.0
    for candidate in ("#FFFFFF", "#000000"):
        score = min(
            contrast_ratio(candidate, primary), contrast_ratio(candidate, secondary)
        )
        if score > best_score:
            best, best_score = candidate, score
    halo = "#000000" if best.upper() == "#FFFFFF" else "#FFFFFF"
    return best, halo


def generate_all():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    teams = json.loads((ROOT / "data" / "teams.json").read_text(encoding="utf-8"))

    generated = 0
    for team in teams:
        style = TEAM_STYLES.get(team["id"])
        if style is None:
            print(f"No style for team '{team['id']}', skipping.")
            continue
        abbr, primary, secondary = style
        text_color, halo_color = text_colors(primary, secondary)
        font_size = 26 if len(abbr) <= 2 else 21
        svg = SVG_TEMPLATE.format(
            primary=primary, secondary=secondary, text_color=text_color,
            halo_color=halo_color, halo_width=2, abbr=abbr, font_size=font_size,
        )
        (ASSETS_DIR / f"{team['id']}.svg").write_text(svg, encoding="utf-8")
        generated += 1

    (ASSETS_DIR / "default.svg").write_text(DEFAULT_SVG, encoding="utf-8")
    print(f"Generated {generated} team badges + default.svg in {ASSETS_DIR}")


if __name__ == "__main__":
    generate_all()
