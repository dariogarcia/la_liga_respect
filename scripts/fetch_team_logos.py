"""Backfills team crest URLs in data/teams.json from ESPN's public scoreboard.

The UI shows each team's official shield; ESPN's keyless scoreboard API
serves a CDN URL for every club. The weekly pipeline refreshes these
URLs automatically during calendar sync, but this script repairs or
bootstraps them for an existing teams.json without a full sync:

    python3 scripts/fetch_team_logos.py

One request is made per distinct game date in games.json (La Liga plays
roughly weekly, so this stays in the low tens of requests), with a
polite delay between calls. Only https URLs are accepted.
"""
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collection.calendar import find_team  # noqa: E402
from src.data.manager import get_games, get_teams, save_teams  # noqa: E402
from src.utils.api import ESPNLaLigaAPI  # noqa: E402

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"
DELAY_SECONDS = 0.5


def crest_map_for_date(day: str):
    """displayName -> crest URL for every team playing on `day` (YYYY-MM-DD)."""
    response = requests.get(
        SCOREBOARD_URL,
        params={"dates": day.replace("-", "")},
        headers={"User-Agent": "RespectRank/1.0 (logo backfill)"},
        timeout=20,
    )
    response.raise_for_status()
    crests = {}
    for event in response.json().get("events", []):
        for competitor in event.get("competitions", [{}])[0].get("competitors", []):
            team = competitor.get("team", {})
            name = team.get("displayName")
            logo = team.get("logo")
            if not (isinstance(name, str) and isinstance(logo, str)):
                continue
            name = ESPNLaLigaAPI.TEAM_ALIASES.get(name, name)
            if logo.startswith("https://"):
                crests[name] = logo
    return crests


def main():
    games = get_games()
    teams = get_teams()
    dates = sorted({g["date"] for g in games if g.get("date")})
    if not dates:
        print("No game dates found in games.json; nothing to fetch.")
        return

    print(f"Fetching crests across {len(dates)} game dates "
          f"({dates[0]} to {dates[-1]})...")
    crests = {}
    for i, day in enumerate(dates):
        try:
            crests.update(crest_map_for_date(day))
        except requests.RequestException as e:
            print(f"  {day}: request failed ({e})")
        if i < len(dates) - 1:
            time.sleep(DELAY_SECONDS)
    print(f"Found crests for {len(crests)} team names.")

    updated = 0
    for api_name, logo in sorted(crests.items()):
        entry = find_team(api_name, teams)
        if entry is None:
            print(f"  Unmapped: {api_name}")
            continue
        if entry.get("logo") != logo:
            entry["logo"] = logo
            updated += 1

    if updated:
        save_teams(teams)
        print(f"Updated {updated} team logos in data/teams.json.")
    else:
        print("All team logos already up to date.")


if __name__ == "__main__":
    main()
