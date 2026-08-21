import json
from src.data.manager import get_comments, get_leaderboard, save_leaderboard, get_teams

def calculate_rankings(comments, mode="separate"):
    teams_data = get_teams()
    all_coaches = [t["coach"] for t in teams_data]
    
    # Initialize only for coaches who have at least one GRADED quote
    # If we initialize everyone to 0, we can't distinguish "0 points" from "no data"
    leaderboard = {} 
    incomplete_games = []
    
    if mode == "separate":
        for c in comments:
            coach = c["coach"]
            # CRITICAL FIX: Only add points if 'score' is explicitly present
            if "score" in c:
                score = c["score"]
                leaderboard[coach] = leaderboard.get(coach, 0) + score
            else:
                # Log as missing data, but do NOT assign a default score of 1
                pass
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
                # Both must be graded to count as a competitive match
                if "score" in q1 and "score" in q2:
                    s1 = q1["score"]
                    s2 = q2["score"]
                    
                    if s1 > s2:
                        leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 3
                        leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 0
                    elif s2 > s1:
                        leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 3
                        leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 0
                    else:
                        leaderboard[q1["coach"]] = leaderboard.get(q1["coach"], 0) + 1
                        leaderboard[q2["coach"]] = leaderboard.get(q2["coach"], 0) + 1
                else:
                    incomplete_games.append(f"Game {gid} (one or both quotes missing score)")
            elif len(quotes) == 1:
                q = quotes[0]
                if "score" in q:
                    score = q["score"]
                    leaderboard[q["coach"]] = leaderboard.get(q["coach"], 0) + score
                incomplete_games.append(f"Game {gid} (only {q['coach']} has a quote)")
            else:
                incomplete_games.append(f"Game {gid} (no quotes found)")
    
    # Now we can fill in the gaps for all teams so the leaderboard is complete,
    # but they will have 0 points if they had no graded quotes.
    final_rankings = []
    for t in teams_data:
        coach = t["coach"]
        points = leaderboard.get(coach, 0)
        final_rankings.append({"coach": coach, "points": points})
    
    sorted_leaderboard = sorted(final_rankings, key=lambda x: x["points"], reverse=True)
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



