from src.collection.collector import collect_matchday_comments
from src.grading.grader import update_leaderboard
from src.data.manager import get_leaderboard
import os

def main():
    # API key could be passed via environment variable
    api_key = os.getenv("SERPAPI_KEY")
    
    print("Starting Respect Rank Update...")
    collect_matchday_comments(api_key=api_key)
    update_leaderboard()
    
    rankings = get_leaderboard()
    print("\n--- Current Respect Rankings ---")
    for i, entry in enumerate(rankings, 1):
        print(f"{i}. {entry['coach']} - {entry['points']} pts")

if __name__ == "__main__":
    main()
