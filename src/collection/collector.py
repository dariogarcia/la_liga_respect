import json
import os
from src.data.manager import get_games, get_comments, save_comments

def search_for_comments(game_id, coach_name, date):
    """
    Interface for the Agentic Bridge.
    Instead of searching directly, it logs the requirement for the LLM Agent.
    """
    print(f"Searching for comments from {coach_name} for game {game_id} (Date: {date})...")
    return f"AGENT_REQUIRED: {coach_name} | {game_id} | {date}"

def collect_matchday_comments():
    games = get_games()
    comments = get_comments()
    
    sought_count = 0
    found_count = 0
    pending = []
    
    for game in games:
        for coach_key in ["home_coach", "away_coach"]:
            coach_name = game[coach_key]
            game_id = game["game_id"]
            game_date = game["date"]
            
            if not any(c["game_id"] == game_id and c["coach"] == coach_name for c in comments):
                sought_count += 1
                quote = search_for_comments(game_id, coach_name, game_date)
                
                if quote and not quote.startswith("AGENT_REQUIRED"):
                    found_count += 1
                    comments.append({
                        "game_id": game_id,
                        "coach": coach_name,
                        "quote": quote
                    })
                else:
                    pending.append({
                        "game_id": game_id,
                        "coach": coach_name,
                        "date": game_date,
                        "query": f"{coach_name} la liga interview {game_date} referee"
                    })
    
    save_comments(comments)
    
    with open("data/pending_requests.json", "w") as f:
        json.dump(pending, f, indent=2)
    
    num_matches = len(games)
    print(f"--- Collection Report ---")
    print(f"Matches processed: {num_matches}")
    print(f"Comments already in DB: {len(comments)}")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments found: {found_count}")
    print(f"Comments pending for Agent: {len(pending)}")
    print(f"---------------------------")






