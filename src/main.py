import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collection.calendar import sync_finished_games
from src.collection.collector import collect_matchday_comments
from src.grading.grader import update_leaderboard
from src.data.manager import get_leaderboard
from src.display import show_leaderboard


def main():
    parser = argparse.ArgumentParser(description="Respect Rank: La Liga Coach Edition")
    parser.add_argument("--no-sync", action="store_true", help="Skip syncing the calendar (football-data.org, or ESPN keyless fallback)")
    parser.add_argument("--no-collect", action="store_true", help="Skip collecting coach comments")
    parser.add_argument("--no-grade", action="store_true", help="Skip grading and leaderboard update")
    parser.add_argument("--retry-pending", action="store_true", help="Reset attempt counters for exhausted pending requests and retry them")
    parser.add_argument("--display", action="store_true", help="Print the full standings table at the end")
    args = parser.parse_args()

    print("Starting Respect Rank Update...")

    if not args.no_sync:
        fd_key = os.getenv("FOOTBALL_DATA_API_KEY") or os.getenv("FOOTBALL_API_KEY")
        sync_finished_games(api_key=fd_key)

    if not args.no_collect:
        serpapi_key = os.getenv("SERPAPI_KEY")
        collect_matchday_comments(api_key=serpapi_key, retry_pending=args.retry_pending)

    if not args.no_grade:
        update_leaderboard()

    rankings = get_leaderboard()
    print("\n--- Current Respect Rankings (Separate) ---")
    for i, entry in enumerate(rankings[:5], 1):
        print(f"{i}. {entry['coach']} ({entry.get('team', '?')}) - {entry['points']} pts")

    if args.display:
        show_leaderboard("separate")
        show_leaderboard("competitive")


if __name__ == "__main__":
    main()
