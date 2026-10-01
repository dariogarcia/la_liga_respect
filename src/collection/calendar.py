import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from src.data.manager import get_games, save_games, get_teams
from src.utils.api import ESPNLaLigaAPI, LaLigaAPI

MATCH_TOKENS = {"de", "la", "el", "los", "las", "a", "y", "club", "cf", "fc", "cd",
                "ud", "sd", "rcd", "real", "deportivo", "atletico", "athletic"}


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    return " ".join(name.lower().split())


def distinctive_tokens(name: str) -> set:
    return {t for t in normalize_name(name).split() if t not in MATCH_TOKENS}


def match_score(api_name: str, known_name: str) -> float:
    api_tokens = distinctive_tokens(api_name)
    known_tokens = distinctive_tokens(known_name)
    if not api_tokens or not known_tokens:
        return 0.0
    overlap = api_tokens & known_tokens
    if not overlap:
        return 0.0
    return len(overlap) / min(len(api_tokens), len(known_tokens))


def find_team(api_name: str, teams: List[Dict]) -> Optional[Dict]:
    # Exact (accent/case-insensitive) match wins immediately. Token
    # matching alone cannot disambiguate subsets like "Real Madrid" vs
    # "Atlético Madrid" (both reduce to {madrid}).
    target = normalize_name(api_name)
    for team in teams:
        if normalize_name(team["team"]) == target:
            return team
    best_team = None
    best_score = 0.0
    for team in teams:
        score = match_score(api_name, team["team"])
        if score > best_score:
            best_score = score
            best_team = team
    if best_team and best_score >= 0.5:
        return best_team
    return None


def utcdate_to_date(utc_date: str) -> str:
    dt = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def game_id_for_match(match: Dict, prefix: str = "fd") -> str:
    return f"{prefix}-{match['match_id']}"


def resolve_coach(team_entry: Dict, game_date: str) -> str:
    """
    Resolves a team's coach on a given date (YYYY-MM-DD).

    Uses the team's optional "coach_history" entries
    ({"coach": name, "until": "YYYY-MM-DD"}, tenure end inclusive).
    Falls back to the current coach for dates after all recorded tenures
    (or when no history is recorded). Mid-season procedure: set "coach" to
    the new hire and append {"coach": old, "until": change_date}.
    """
    history = team_entry.get("coach_history") or []
    candidates = [h for h in history if game_date <= h.get("until", "")]
    if candidates:
        return min(candidates, key=lambda h: h["until"])["coach"]
    return team_entry["coach"]


def sync_finished_games(api_key: Optional[str] = None) -> Dict:
    """
    Syncs finished La Liga matches into games.json.

    Uses football-data.org when an API key is available, otherwise falls
    back to ESPN's public scoreboard API (keyless). Only matches not
    already known (by game_id or home/away/date) are added. Coaches are
    resolved from teams.json.
    """
    stats = {"added": 0, "already_known": 0, "unmapped": [], "error": None, "source": None}

    games = get_games()
    teams = get_teams()

    if api_key:
        api = LaLigaAPI(api_key)
        id_prefix = "fd"
        stats["source"] = "football-data.org"
    else:
        # Keyless fallback: ESPN public scoreboard. Scan from a week before
        # the earliest known game (or 60 days back on an empty calendar).
        today = datetime.now(timezone.utc).date()
        if games:
            earliest = min(g["date"] for g in games)
            start = datetime.strptime(earliest, "%Y-%m-%d").date() - timedelta(days=7)
        else:
            start = today - timedelta(days=60)
        api = ESPNLaLigaAPI(start_date=start.isoformat(), end_date=today.isoformat())
        id_prefix = "espn"
        stats["source"] = "ESPN public scoreboard (keyless fallback)"

    finished = api.get_finished_matches()
    if not finished:
        stats["error"] = f"No finished matches retrieved from {stats['source']}."
        print(stats["error"])
        return stats
    known_ids = {g["game_id"] for g in games}
    known_pairs = {(g["home_team"], g["away_team"], g["date"]) for g in games}

    for match in finished:
        gid = game_id_for_match(match, id_prefix)
        date = utcdate_to_date(match["utcDate"])
        home = find_team(match["homeTeam"], teams)
        away = find_team(match["awayTeam"], teams)

        if home is None:
            stats["unmapped"].append(match["homeTeam"])
            continue
        if away is None:
            stats["unmapped"].append(match["awayTeam"])
            continue

        pair = (home["team"], away["team"], date)
        if gid in known_ids or pair in known_pairs:
            stats["already_known"] += 1
            continue

        games.append({
            "game_id": gid,
            "date": date,
            "home_team": home["team"],
            "away_team": away["team"],
            "home_coach": resolve_coach(home, date),
            "away_coach": resolve_coach(away, date),
        })
        known_ids.add(gid)
        known_pairs.add(pair)
        stats["added"] += 1

    if stats["added"]:
        games.sort(key=lambda g: (g["date"], g["game_id"]))
        save_games(games)

    print(
        f"--- Calendar Sync Report ---\n"
        f"Source: {stats['source']}\n"
        f"Finished matches: {len(finished)}\n"
        f"New games added: {stats['added']}\n"
        f"Already known: {stats['already_known']}\n"
        f"Unmapped teams: {sorted(set(stats['unmapped'])) or 'none'}\n"
        f"----------------------------"
    )
    return stats
