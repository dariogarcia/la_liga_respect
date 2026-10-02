import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collection.calendar import sync_finished_games
from src.collection.collector import collect_matchday_comments
from src.data.manager import get_leaderboard, get_run_report, save_run_report
from src.display import show_leaderboard
from src.grading.grader import update_leaderboard
from src.utils import http, llm

# How far before the previous run's date a new run still re-examines:
# covers games played between runs even when the last run was only a
# display/grading pass (A3).
SINCE_OVERLAP_DAYS = 3


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}' (expected YYYY-MM-DD)")


def _resolve_since(cli_value):
    """A3: which games this run should examine.

    Priority: explicit --since, then the SINCE env var, then the last
    run's date (from data/run_report.json) minus a small overlap. None
    means "examine everything".
    """
    if cli_value:
        return cli_value
    env_value = os.getenv("SINCE")
    if env_value:
        try:
            return _parse_date(env_value)
        except argparse.ArgumentTypeError:
            print(f"Warning: ignoring invalid SINCE env value '{env_value}'.")
    last_run = get_run_report().get("last_run")
    if last_run:
        try:
            return _parse_date(last_run) - timedelta(days=SINCE_OVERLAP_DAYS)
        except argparse.ArgumentTypeError:
            return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Respect Rank: La Liga Coach Edition")
    parser.add_argument("--no-sync", action="store_true", help="Skip syncing the calendar (football-data.org, or ESPN keyless fallback)")
    parser.add_argument("--no-collect", action="store_true", help="Skip collecting coach comments")
    parser.add_argument("--no-grade", action="store_true", help="Skip grading and leaderboard update")
    parser.add_argument("--retry-pending", action="store_true", help="Reset attempt counters for exhausted pending requests and retry them")
    parser.add_argument("--since", type=_parse_date, metavar="YYYY-MM-DD", default=None,
                        help="Only examine games dated on or after this date (default: last run minus %d days)" % SINCE_OVERLAP_DAYS)
    parser.add_argument("--full-history", action="store_true", help="Ignore the last-run marker and examine every past game")
    parser.add_argument("--display", action="store_true", help="Print the full standings table at the end")
    args = parser.parse_args()

    print("Starting Respect Rank Update...")

    previous_report = get_run_report()
    since = None if args.full_history else _resolve_since(args.since)
    if since is not None:
        print(f"Collection window: games since {since.isoformat()} (use --full-history to override).")

    http.reset_request_budget()
    llm.reset_llm_usage()

    sync_stats = None
    if not args.no_sync:
        fd_key = os.getenv("FOOTBALL_DATA_API_KEY") or os.getenv("FOOTBALL_API_KEY")
        sync_stats = sync_finished_games(api_key=fd_key)

    collection_stats = None
    if not args.no_collect:
        serpapi_key = os.getenv("SERPAPI_KEY")
        collection_stats = collect_matchday_comments(
            api_key=serpapi_key, retry_pending=args.retry_pending, since=since
        )

    grading_stats = None
    if not args.no_grade:
        grading_stats = update_leaderboard()

    rankings = get_leaderboard()
    print("\n--- Current Respect Rankings (Separate) ---")
    for i, entry in enumerate(rankings[:5], 1):
        print(f"{i}. {entry['coach']} ({entry.get('team', '?')}) - {entry['points']} pts")

    # A5/E5: run report — audit trail for every run and the GUI's
    # "last updated" source. `last_run` only advances when collection
    # actually happened, so display-only passes do not shrink the next
    # run's window.
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "last_run": today_iso() if not args.no_collect else previous_report.get("last_run"),
        "since_used": since.isoformat() if since is not None else None,
        "sync": sync_stats,
        "collection": collection_stats,
        "grading": grading_stats,
        "llm_usage": llm.llm_usage(),
        "http_requests": http.request_budget().count,
    }
    save_run_report(report)
    print(f"Run report written to data/run_report.json "
          f"(LLM calls: {report['llm_usage']['calls']}, HTTP requests: {report['http_requests']}).")

    if args.display:
        show_leaderboard("separate")
        show_leaderboard("competitive")


def today_iso():
    return date.today().isoformat()


if __name__ == "__main__":
    main()
