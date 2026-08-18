import json
import os
from src.data.manager import get_games, get_comments, save_comments

def search_for_comments(game_id, coach_name, date):
    """
    Real mechanism: This function is intended to be called by an LLM-powered agent.
    The date is used as a filter to ensure the correct match is identified.
    """
    print(f"Searching for comments from {coach_name} for game {game_id} (Date: {date})...")
    
    # In a production environment, the agent would use the date in the query:
    # "Search for {coach_name} interview after {date} for match {game_id}"
    
    return f"AGENT_REQUIRED: Please fetch the latest interview for {coach_name} from {date}"

def collect_matchday_comments():
    games = get_games()
    comments = get_comments()
    
    sought_count = 0
    found_count = 0
    
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
    
    save_comments(comments)
    
    num_matches = len(games)
    existing_comments_count = len(comments)
    print(f"--- Collection Report ---")
    print(f"Matches processed: {num_matches}")
    print(f"Comments already in DB: {existing_comments_count}")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments found: {found_count}")
    print(f"Comments not found/Agent required: {sought_count - found_count}")
    print(f"----------------------------")





