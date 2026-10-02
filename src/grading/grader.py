from typing import Dict, List, Tuple

from src.data.manager import (
    get_comments,
    get_games,
    get_teams,
    save_comments,
    get_leaderboard,
    save_leaderboard,
)
from ..utils import llm

DISRESPECTFUL_PATTERNS = [
    "saqueo", "robo", "robado", "robando", "hurto",
    "vergüenza", "vergonzoso", "escándalo", "escandaloso",
    "favoritismo", "favoritos", "siempre nos pasa", "siempre pasa lo mismo",
    "no nos tratan", "nos tratan distinto", "nos tratan diferente",
    "miedo a", "nos han costado el partido", "condicionado",
    "no tiene ni idea", "no sabe", "a verme si", "que revise",
    "desastre", "penoso", "indecente",
]

RESPECTFUL_PATTERNS = [
    "bien arbitrado", "gran trabajo", "trabajo difícil", "trabajo complicado",
    "acertó", "acierto", "aciertos", "impecable",
    "no quiero culpar", "sin culpar", "no es culpa del árbitro",
    "no fue culpa del árbitro", "le felicito", "felicitar al árbitro",
    "todos nos equivocamos", "los errores son parte", "parte del fútbol",
    "le deseo", "no quiero quitarle mérito", "hizo lo que pudo",
    "difícil ser árbitro", "trabajo del árbitro es difícil",
]


def heuristic_grade(text: str) -> int:
    """
    Keyword-based fallback grading. Approximate by design; used only when
    no LLM is configured.
    """
    lowered = text.casefold()
    dis = sum(1 for p in DISRESPECTFUL_PATTERNS if p in lowered)
    res = sum(1 for p in RESPECTFUL_PATTERNS if p in lowered)
    if dis > res:
        return 0
    if res > dis:
        return 3
    return 1


def grade_quote(text: str) -> Tuple[int, str, str]:
    """
    Grades a quote as 3 (respectful), 1 (neutral) or 0 (disrespectful).
    Uses an LLM if available, otherwise the heuristic fallback.
    Returns (score, graded_by, justification).
    """
    if llm.llm_available():
        system = (
            "You grade football coaches' post-match quotes about referees. "
            "Respond only with JSON."
        )
        user = (
            "Grade the following quote according to these criteria:\n"
            "- 3 points (Respectful): acknowledges the referee's difficulty, avoids "
            "blaming them for the result, or praises the officiating.\n"
            "- 1 point (Neutral): mentions the referee neutrally or expresses "
            "disagreement without aggression or accusations of bias.\n"
            "- 0 points (Disrespectful): openly criticizes the referee, implies bias, "
            "uses aggressive language, or calls for sanctions.\n\n"
            f"Respond as JSON: {{\"score\": 0, \"justification\": \"...\"}}\n\n"
            f"QUOTE (in Spanish):\n{text}"
        )
        try:
            data = llm.llm_chat(
                system, user, json_mode=True, temperature=0.0, purpose="grading"
            )
            score = int(data.get("score"))
            if score in (0, 1, 3):
                return score, "llm", str(data.get("justification", "")).strip()
        except llm.LLMBudgetExceeded:
            print("LLM budget exhausted: remaining quotes graded by keyword heuristic.")
        except Exception as e:
            print(f"LLM grading failed, falling back to heuristic: {e}")
    return heuristic_grade(text), "heuristic", "keyword heuristic"


def merge_comments(comments: List[Dict]) -> List[Dict]:
    """
    Merges multiple comments from the same coach in the same game into a
    single entry (design.md: concatenation of remarks per game).
    Scored comments keep the sum of their scores; un-scored groups get one
    merged quote to be graded.
    """
    groups: Dict[Tuple[str, str], List[Dict]] = {}
    order: List[Tuple[str, str]] = []
    for c in comments:
        key = (c["game_id"], c["coach"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    merged = []
    for key in order:
        group = groups[key]
        base = dict(group[0])
        if len(group) == 1:
            merged.append(base)
            continue

        texts = [c["quote"] for c in group]
        base["quote"] = " ".join(texts)
        sources = []
        for c in group:
            for s in c.get("sources", [c.get("source_url")] if c.get("source_url") else []):
                if s and s not in sources:
                    sources.append(s)
        if sources:
            base["sources"] = sources
            base["source_url"] = sources[0]

        scores = [c["score"] for c in group if "score" in c]
        if len(scores) == len(group):
            base["score"] = sum(scores)
        else:
            base.pop("score", None)
        merged.append(base)
    return merged


def _games_by_id() -> Dict[str, Dict]:
    return {g["game_id"]: g for g in get_games()}


def calculate_rankings(comments: List[Dict], mode: str = "separate"):
    teams_data = get_teams()
    games = _games_by_id()

    # T3: accumulate per (coach, team), resolving the coach's team from
    # each game record. Two different coaches sharing a name (Spanish
    # football has had simultaneous "Luis García"s) must never merge
    # points; a coach switching clubs mid-season keeps separate rows
    # per club.
    leaderboard: Dict[Tuple[str, str], Dict] = {}
    incomplete_games = []

    def _entry(coach: str, team: str) -> Dict:
        key = (coach, team)
        if key not in leaderboard:
            leaderboard[key] = {
                "coach": coach, "team": team, "points": 0, "games_played": 0,
                "home_points": 0, "away_points": 0,
                "quoted_games": 0, "quoted_points": 0,
            }
        return leaderboard[key]

    def _side(game: Dict, coach: str) -> str:
        """E2: 'home' or 'away' for the coach in this game, else ''."""
        if game.get("home_coach") == coach:
            return "home"
        if game.get("away_coach") == coach:
            return "away"
        return ""

    def _team_for(game: Dict, coach: str, fallback: str) -> str:
        """The team the coach represented in this game."""
        if game.get("home_coach") == coach:
            return game.get("home_team") or fallback
        if game.get("away_coach") == coach:
            return game.get("away_team") or fallback
        return fallback

    def _add(coach: str, team: str, points: int, side: str) -> None:
        entry = _entry(coach, team)
        entry["points"] += points
        if side == "home":
            entry["home_points"] += points
        elif side == "away":
            entry["away_points"] += points

    # Map every known coach (current and historical) to his team so that
    # coaches replaced mid-season keep their affiliation and points.
    team_by_coach: Dict[str, str] = {}
    for t in teams_data:
        team_by_coach.setdefault(t["coach"], t["team"])
        for h in t.get("coach_history") or []:
            team_by_coach.setdefault(h["coach"], t["team"])

    by_game: Dict[str, List[Dict]] = {}
    for c in comments:
        by_game.setdefault(c["game_id"], []).append(c)

    def _team(game: Dict, coach: str) -> str:
        """T3: the club this coach represented in this game (falls back
        to the affiliation table when the game record is missing)."""
        return _team_for(game, coach, team_by_coach.get(coach, "?"))

    for gid, quotes in by_game.items():
        scored = [c for c in quotes if "score" in c]
        game = games.get(gid, {})
        coaches_here = {c["coach"] for c in scored}

        if mode == "separate":
            for c in scored:
                _add(c["coach"], _team(game, c["coach"]), c["score"], _side(game, c["coach"]))
                entry = _entry(c["coach"], _team(game, c["coach"]))
                entry["games_played"] += 1
                if not c.get("no_ref_comment"):
                    # Normalization base: only games where a quote was
                    # retrieved count towards the per-game average.
                    entry["quoted_games"] += 1
                    entry["quoted_points"] += c["score"]
            missing = [c["coach"] for c in quotes if "score" not in c]
            if missing:
                incomplete_games.append(f"Game {gid} (ungraded quotes: {', '.join(missing)})")
        else:
            if len(coaches_here) < 2:
                incomplete_games.append(f"Game {gid} (only {len(coaches_here)} coach with graded quote)")
                for c in scored:
                    _add(c["coach"], _team(game, c["coach"]), c["score"], _side(game, c["coach"]))
                    entry = _entry(c["coach"], _team(game, c["coach"]))
                    entry["games_played"] += 1
                    if not c.get("no_ref_comment"):
                        entry["quoted_games"] += 1
                        entry["quoted_points"] += c["score"]
                continue

            home_coach = game.get("home_coach")
            away_coach = game.get("away_coach")
            pairs = [(c["coach"], c["score"]) for c in scored]
            awarded = {c["coach"]: 0 for c in scored}
            if home_coach and away_coach and {home_coach, away_coach} == coaches_here:
                s_h = next(s for c, s in pairs if c == home_coach)
                s_a = next(s for c, s in pairs if c == away_coach)
                _entry(home_coach, _team(game, home_coach))["games_played"] += 1
                _entry(away_coach, _team(game, away_coach))["games_played"] += 1
                if s_h > s_a:
                    _add(home_coach, _team(game, home_coach), 3, "home")
                    awarded[home_coach] = 3
                elif s_a > s_h:
                    _add(away_coach, _team(game, away_coach), 3, "away")
                    awarded[away_coach] = 3
                else:
                    _add(home_coach, _team(game, home_coach), 1, "home")
                    _add(away_coach, _team(game, away_coach), 1, "away")
                    awarded[home_coach] = 1
                    awarded[away_coach] = 1
            else:
                sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)
                for c, _ in sorted_pairs:
                    _entry(c, _team(game, c))["games_played"] += 1
                if sorted_pairs[0][1] > sorted_pairs[1][1]:
                    _add(sorted_pairs[0][0], _team(game, sorted_pairs[0][0]), 3, _side(game, sorted_pairs[0][0]))
                    awarded[sorted_pairs[0][0]] = 3
                elif sorted_pairs[1][1] > sorted_pairs[0][1]:
                    _add(sorted_pairs[1][0], _team(game, sorted_pairs[1][0]), 3, _side(game, sorted_pairs[1][0]))
                    awarded[sorted_pairs[1][0]] = 3
                else:
                    _add(sorted_pairs[0][0], _team(game, sorted_pairs[0][0]), 1, _side(game, sorted_pairs[0][0]))
                    _add(sorted_pairs[1][0], _team(game, sorted_pairs[1][0]), 1, _side(game, sorted_pairs[1][0]))
                    awarded[sorted_pairs[0][0]] = 1
                    awarded[sorted_pairs[1][0]] = 1
            for c in scored:
                if not c.get("no_ref_comment"):
                    entry = _entry(c["coach"], _team(game, c["coach"]))
                    entry["quoted_games"] += 1
                    entry["quoted_points"] += awarded.get(c["coach"], 0)

    final_rankings = []
    emitted = set()
    _zero = {"points": 0, "games_played": 0, "home_points": 0, "away_points": 0,
             "quoted_games": 0, "quoted_points": 0}
    for t in teams_data:
        coach = t["coach"]
        entry = leaderboard.get((coach, t["team"]), _zero)
        final_rankings.append({
            "coach": coach,
            "team": t["team"],
            "points": entry["points"],
            "games_played": entry["games_played"],
            "home_points": entry["home_points"],
            "away_points": entry["away_points"],
            "quoted_games": entry["quoted_games"],
            "quoted_points": entry["quoted_points"],
        })
        emitted.add((coach, t["team"]))

    # Coaches no longer at a club stay on the table if they played games.
    for (coach, team), entry in leaderboard.items():
        if (coach, team) in emitted:
            continue
        if entry["points"] or entry["games_played"]:
            final_rankings.append({
                "coach": coach,
                "team": team,
                "points": entry["points"],
                "games_played": entry["games_played"],
                "home_points": entry["home_points"],
                "away_points": entry["away_points"],
                "quoted_games": entry["quoted_games"],
                "quoted_points": entry["quoted_points"],
            })

    sorted_leaderboard = sorted(final_rankings, key=lambda x: (-x["points"], x["coach"]))
    return sorted_leaderboard, incomplete_games


def update_leaderboard():
    comments = get_comments()

    merged = merge_comments(comments)
    graded_count = 0
    for c in merged:
        if "score" not in c:
            score, graded_by, justification = grade_quote(c["quote"])
            c["score"] = score
            c["graded_by"] = graded_by
            if justification:
                c["justification"] = justification
            graded_count += 1
    if merged != comments:
        save_comments(merged)
    comments = merged

    separate_rankings, _ = calculate_rankings(comments, mode="separate")
    save_leaderboard(separate_rankings, mode="separate")

    competitive_rankings, incomplete = calculate_rankings(comments, mode="competitive")
    save_leaderboard(competitive_rankings, mode="competitive")

    heuristic_count = sum(1 for c in comments if c.get("graded_by") == "heuristic")
    coverage_count = sum(1 for c in comments if c.get("graded_by") == "coverage")
    usage = llm.llm_usage()
    print(f"--- Grading Report ---")
    print(f"Quotes processed: {len(comments)}")
    print(f"Newly graded: {graded_count}")
    if coverage_count:
        print(f"Games resolved without a referee comment (score 3): {coverage_count}")
    if heuristic_count:
        print(f"WARNING: {heuristic_count} quotes graded by keyword heuristic (no LLM key).")
    print(f"LLM usage so far: {usage['calls']} call(s), "
          f"~{usage['prompt_tokens'] + usage['completion_tokens']} tokens "
          f"({', '.join(f'{k}={v}' for k, v in usage['by_purpose'].items()) or 'none'}).")
    print(f"Separate leaderboard updated.")
    print(f"Competitive leaderboard updated.")
    if incomplete:
        print(f"Incomplete games flagged: {len(incomplete)}")
        for msg in incomplete:
            print(f"  - {msg}")
    print(f"----------------------")
    return {
        "quotes": len(comments),
        "newly_graded": graded_count,
        "heuristic": heuristic_count,
        "no_ref_comment": coverage_count,
        "llm_calls": usage["calls"],
    }
