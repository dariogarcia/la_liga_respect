import json
from src.data.manager import get_games, get_comments, load_json, DATA_DIR
import os

def show_leaderboard(mode="separate"):
    games = get_games()
    comments = get_comments()
    
    # Validation: Check for missing scores
    missing_scores = [c["coach"] for c in comments if "score" not in c]
    if missing_scores:
        print(f"WARNING: {len(missing_scores)} quotes are missing Agent scores! This may skew results.")
        print(f"Missing scores for: {', '.join(set(missing_scores))}")
        print("-" * 58)

    # Load teams to map coach -> team
    teams_path = os.path.join(DATA_DIR, "teams.json")
    teams_data = load_json(teams_path)
    
    coach_to_team = {t["coach"]: t["team"] for t in teams_data}
    team_stats = {t["team"]: {"games": 0, "home": 0, "away": 0, "total": 0} for t in teams_data}
    
    # We need to know which coach played where in each game
    for game in games:
        gid = game["game_id"]
        h_coach = game["home_coach"]
        a_coach = game["away_coach"]
        h_team = game["home_team"]
        a_team = game["away_team"]
        
        # Find comments for this game
        game_comments = [c for c in comments if c["game_id"] == gid]
        
        # Track games played (where a comment was processed)
        # For simplicity, we count the game if either coach has a comment, 
        # but typically we track per team.
        h_comment = next((c for c in game_comments if c["coach"] == h_coach), None)
        a_comment = next((c for c in game_comments if c["coach"] == a_coach), None)
        
        if h_comment:
            team_stats[h_team]["games"] += 1
        if a_comment:
            team_stats[a_team]["games"] += 1
        
        # Separate mode calculations
        if mode == "separate":
            for c in game_comments:
                score = c.get("score", 1)
                if c["coach"] == h_coach:
                    team_stats[h_team]["home"] += score
                    team_stats[h_team]["total"] += score
                elif c["coach"] == a_coach:
                    team_stats[a_team]["away"] += score
                    team_stats[a_team]["total"] += score
        
        # Competitive mode calculations
        else:
            if h_comment and a_comment:
                s_h = h_comment.get("score", 1)
                s_a = a_comment.get("score", 1)
                
                if s_h > s_a:
                    team_stats[h_team]["home"] += 3
                    team_stats[h_team]["total"] += 3
                    team_stats[a_team]["away"] += 0
                elif s_a > s_h:
                    team_stats[a_team]["away"] += 3
                    team_stats[a_team]["total"] += 3
                    team_stats[h_team]["home"] += 0
                else:
                    team_stats[h_team]["home"] += 1
                    team_stats[h_team]["total"] += 1
                    team_stats[a_team]["away"] += 1
                    team_stats[a_team]["total"] += 1

    # Sort teams by total points
    sorted_teams = sorted(team_stats.items(), key=lambda x: x[1]["total"], reverse=True)
    
    # Print table
    print(f"\n--- Respect Leaderboard ({mode}) ---")
    print(f"{'Pos':<4} | {'Team':<20} | {'Total':<6} | {'GP':<4} | {'Home':<6} | {'Away':<6}")
    print("-" * 58)
    for i, (team, stats) in enumerate(sorted_teams, 1):
        print(f"{i:<4} | {team:<20} | {stats['total']:<6} | {stats['games']:<4} | {stats['home']:<6} | {stats['away']:<6}")
    print("-" * 58)



if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "separate"
    show_leaderboard(mode)
