import json
from src.data.manager import get_comments, get_leaderboard, save_leaderboard, get_teams

def calculate_rankings(comments, mode="separate"):
    teams_data = get_teams()
    all_coaches = [t["coach"] for t in teams_data]
    
    leaderboard = {coach: 0 for coach in all_coaches}
    incomplete_games = []
    
    if mode == "separate":
        for c in comments:
            coach = c["coach"]
            if coach in leaderboard:
                score = c.get("score", 1)
                leaderboard[coach] += score
    else:
        # Competitive mode: For every game, we compare home vs away
        game_quotes = {}
        for c in comments:
            gid = c["game_id"]
            if gid not in game_quotes:
                game_quotes[gid] = []
            game_quotes[gid].append(c)
            
        for gid, quotes in game_quotes.items():
            if len(quotes) == 2:
                q1, q2 = quotes[0], quotes[1]
                s1 = q1.get("score", 1)
                s2 = q2.get("score", 1)
                
                if s1 > s2:
                    leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 3
                    leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 0
                elif s2 > s1:
                    leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 3
                    leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 0
                else:
                    leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 1
                    leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 1
            elif len(quotes) == 1:
                q = quotes[0]
                score = q.get("score", 1)
                leaderboard[q["coach"]] = leaderboard.get(q["coach"], 0) + score
                incomplete_games.append(f"Game {gid} (only {q['coach']} has a score)")
            else:
                incomplete_games.append(f"Game {gid} (no scores found)")
    
    sorted_leaderboard = [
        {"coach": coach, "points": points} 
        for coach, points in sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    ]
    return sorted_leaderboard, incomplete_games

def update_leaderboard():
    comments = get_comments()
    
    # Update separate leaderboard
    separate_rankings, _ = calculate_rankings(comments, mode="separate")
    save_leaderboard(separate_rankings, mode="separate")
    
    # Update competitive leaderboard
    competitive_rankings, incomplete = calculate_rankings(comments, mode="competitive")
    save_leaderboard(competitive_rankings, mode="competitive")
    
    print(f"--- Grading Report ---")
    print(f"Quotes processed: {len(comments)}")
    # Flag quotes that have no score assigned by the agent
    missing_scores = [c for c in comments if "score" not in c]
    if missing_scores:
        print(f"WARNING: {len(missing_scores)} quotes are missing Agent scores!")
    
    print(f"Separate leaderboard updated.")
    print(f"Competitive leaderboard updated.")
    if incomplete:
        print(f"Incomplete games flagged: {len(incomplete)}")
        for msg in incomplete:
            print(f"  - {msg}")
    print(f"----------------------")



