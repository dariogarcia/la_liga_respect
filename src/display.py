import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.manager import get_games, get_comments, get_teams, load_json, DATA_DIR


def show_leaderboard(mode="separate"):
    games = get_games()
    comments = get_comments()
    teams_data = get_teams()

    missing_scores = [c["coach"] for c in comments if "score" not in c]
    if missing_scores:
        print(f"WARNING: {len(missing_scores)} quotes are missing scores! This may skew results.")
        print(f"Missing scores for: {', '.join(set(missing_scores))}")
        print("-" * 58)

    heuristic_scores = [c["coach"] for c in comments if c.get("graded_by") == "heuristic"]
    if heuristic_scores:
        print(f"NOTE: {len(heuristic_scores)} quotes graded by keyword heuristic (run the grader with an LLM key for better accuracy).")
        print("-" * 58)

    coach_to_team = {t["coach"]: t["team"] for t in teams_data}
    team_stats = {t["team"]: {"games": 0, "home": 0, "away": 0, "total": 0} for t in teams_data}

    for game in games:
        gid = game["game_id"]
        h_coach = game["home_coach"]
        a_coach = game["away_coach"]
        h_team = game["home_team"]
        a_team = game["away_team"]

        game_comments = [c for c in comments if c["game_id"] == gid]

        def _score_for(coach):
            return sum(c["score"] for c in game_comments if c["coach"] == coach and "score" in c)

        h_has = any(c["coach"] == h_coach for c in game_comments)
        a_has = any(c["coach"] == a_coach for c in game_comments)

        if h_has:
            team_stats[h_team]["games"] += 1
        if a_has:
            team_stats[a_team]["games"] += 1

        if mode == "separate":
            if h_has:
                score = _score_for(h_coach)
                team_stats[h_team]["home"] += score
                team_stats[h_team]["total"] += score
            if a_has:
                score = _score_for(a_coach)
                team_stats[a_team]["away"] += score
                team_stats[a_team]["total"] += score
        else:
            if h_has and a_has:
                s_h = _score_for(h_coach)
                s_a = _score_for(a_coach)

                if s_h > s_a:
                    team_stats[h_team]["home"] += 3
                    team_stats[h_team]["total"] += 3
                elif s_a > s_h:
                    team_stats[a_team]["away"] += 3
                    team_stats[a_team]["total"] += 3
                else:
                    team_stats[h_team]["home"] += 1
                    team_stats[h_team]["total"] += 1
                    team_stats[a_team]["away"] += 1
                    team_stats[a_team]["total"] += 1

    sorted_teams = sorted(team_stats.items(), key=lambda x: x[1]["total"], reverse=True)

    print(f"\n--- Respect Leaderboard ({mode}) ---")
    print(f"{'Pos':<4} | {'Team':<20} | {'Total':<6} | {'GP':<4} | {'Home':<6} | {'Away':<6}")
    print("-" * 58)
    for i, (team, stats) in enumerate(sorted_teams, 1):
        print(f"{i:<4} | {team:<20} | {stats['total']:<6} | {stats['games']:<4} | {stats['home']:<6} | {stats['away']:<6}")
    print("-" * 58)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "separate"
    if mode not in ("separate", "competitive"):
        print(f"Unknown mode '{mode}'. Use 'separate' or 'competitive'.")
        sys.exit(1)
    show_leaderboard(mode)
