import json
import os
from src.data.manager import get_games, get_comments, save_comments

# Mocking an agentic search for this draft
def search_for_comments(game_id, coach_name):
    print(f"Searching for comments from {coach_name} for game {game_id}...")
    # Updated mock data to include new coaches
    mock_data = {
        "Quique Sánchez Flores": "The referee did his best, we accept the result.",
        "José Bordalás": "This is a scandal! The referee has cost us the game!",
        "Manolo González": "I don't agree with the penalty, but it's part of the game.",
        "Luís Castro": "The officiating was acceptable overall.",
        "José Alberto López": "We are happy with the result, no complaints about the ref.",
        "Iñigo Pérez": "Some decisions were questionable, but we move on."
    }
    return mock_data.get(coach_name, "No comments found.")


def collect_matchday_comments():
    games = get_games()
    comments = get_comments()
    
    sought_count = 0
    found_count = 0
    
    for game in games:
        for coach_key in ["home_coach", "away_coach"]:
            coach_name = game[coach_key]
            game_id = game["game_id"]
            
            if not any(c["game_id"] == game_id and c["coach"] == coach_name for c in comments):
                sought_count += 1
                quote = search_for_comments(game_id, coach_name)
                if quote != "No comments found.":
                    found_count += 1
                    comments.append({
                        "game_id": game_id,
                        "coach": coach_name,
                        "quote": quote
                    })
    
    save_comments(comments)
    
    num_matches = len(games)
    print(f"--- Collection Report ---")
    print(f"Matches processed: {num_matches}")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments found: {found_count}")
    print(f"Comments not found: {sought_count - found_count}")
    print(f"-------------------------")


