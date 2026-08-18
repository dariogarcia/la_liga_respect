import json
import os

DATA_DIR = "data"
GAMES_FILE = os.path.join(DATA_DIR, "games.json")
COMMENTS_FILE = os.path.join(DATA_DIR, "comments.json")
LEADERBOARD_FILE = os.path.join(DATA_DIR, "leaderboard.json")
LEADERBOARD_COMPETITIVE_FILE = os.path.join(DATA_DIR, "leaderboard_competitive.json")

def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def get_games():
    return load_json(GAMES_FILE)

def get_comments():
    return load_json(COMMENTS_FILE)

def save_comments(comments):
    save_json(COMMENTS_FILE, comments)

def get_leaderboard(mode="separate"):
    filepath = LEADERBOARD_FILE if mode == "separate" else LEADERBOARD_COMPETITIVE_FILE
    return load_json(filepath)

def save_leaderboard(leaderboard, mode="separate"):
    filepath = LEADERBOARD_FILE if mode == "separate" else LEADERBOARD_COMPETITIVE_FILE
    save_json(filepath, leaderboard)

