import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.manager import get_comments, get_teams
from src.grading.grader import calculate_rankings


def show_leaderboard(mode="separate"):
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

    no_ref = [c for c in comments if c.get("no_ref_comment")]
    if no_ref:
        confirmed = sum(1 for c in no_ref if c.get("kind") == "confirmed")
        print(f"NOTE: {len(no_ref)} game(s) resolved without a referee comment "
              f"({confirmed} confirmed coach coverage, {len(no_ref) - confirmed} presumed). "
              f"These count as respectful (3 points).")
        print("-" * 58)

    # U4: one source of truth. The team table is aggregated from
    # calculate_rankings (coach rows with home/away points), so the
    # terminal view can never drift from the published leaderboard.
    rankings, incomplete = calculate_rankings(comments, mode=mode)
    if incomplete:
        print(f"NOTE: {len(incomplete)} game(s) have incomplete grading:")
        for note in incomplete[:5]:
            print(f"  - {note}")
        if len(incomplete) > 5:
            print(f"  ... and {len(incomplete) - 5} more")
        print("-" * 58)

    team_stats = {t["team"]: {"games": 0, "home": 0, "away": 0, "total": 0}
                  for t in teams_data}
    for row in rankings:
        stats = team_stats.setdefault(
            row["team"], {"games": 0, "home": 0, "away": 0, "total": 0}
        )
        stats["games"] += row["games_played"]
        stats["home"] += row["home_points"]
        stats["away"] += row["away_points"]
        stats["total"] += row["points"]

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
