import json
import os

DATA_DIR = "data"
GAMES_FILE = os.path.join(DATA_DIR, "games.json")
COMMENTS_FILE = os.path.join(DATA_DIR, "comments.json")
TEAMS_FILE = os.path.join(DATA_DIR, "teams.json")
LEADERBOARD_FILE = os.path.join(DATA_DIR, "leaderboard.json")
LEADERBOARD_COMPETITIVE_FILE = os.path.join(DATA_DIR, "leaderboard_competitive.json")

def load_json(filepath):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File {filepath} not found.")
        return [] if "leaderboard" in filepath or "comments" in filepath or "games" in filepath or "teams" in filepath else {}
    except json.JSONDecodeError:
        print(f"Error: File {filepath} contains malformed JSON.")
        return [] if "leaderboard" in filepath or "comments" in filepath or "games" in filepath or "teams" in filepath else {}

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_games():
    games = load_json(GAMES_FILE)
    # Validate essential fields
    valid_games = [g for g in games if all(k in g for k in ["game_id", "home_coach", "away_coach"])]
    if len(valid_games) < len(games):
        print(f"Warning: Dropped {len(games) - len(valid_games)} malformed games from {GAMES_FILE}")
    return valid_games

def get_comments():
    comments = load_json(COMMENTS_FILE)
    # Validate essential fields
    valid_comments = [c for c in comments if all(k in c for k in ["game_id", "coach", "quote"])]
    if len(valid_comments) < len(comments):
        print(f"Warning: Dropped {len(comments) - len(valid_comments)} malformed comments from {COMMENTS_FILE}")
    return valid_comments

def save_comments(comments):
    save_json(COMMENTS_FILE, comments)

def get_teams():
    return load_json(TEAMS_FILE)

def get_leaderboard(mode="separate"):
    filepath = LEADERBOARD_FILE if mode == "separate" else LEADERBOARD_COMPETITIVE_FILE
    return load_json(filepath)

def save_leaderboard(leaderboard, mode="separate"):
    filepath = LEADERBOARD_FILE if mode == "separate" else LEADERBOARD_COMPETITIVE_FILE
    save_json(filepath, leaderboard)

