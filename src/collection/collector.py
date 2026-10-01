from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional

from src.data.manager import (
    get_games,
    get_comments,
    save_comments,
    get_pending_requests,
    save_pending_requests,
)
from .models import SourceDocument
from .queries import build_queries
from .search import get_search_provider
from .sitemap import fetch_sitemap_entries, find_coach_articles
from .filtering import is_allowed_source
from .fetcher import ArticleFetcher
from .extractor import get_extractor
from .validation import validate_extractions
from .deduplication import deduplicate_quotes

MAX_DOCS_PER_COACH = 6
MAX_ATTEMPTS = 5
PUBLICATION_WINDOW = timedelta(days=2)

REASON_NO_RESULTS = "no_search_results"
REASON_NO_TRUSTED = "no_trusted_sources"
REASON_FETCH_FAILED = "fetch_failed"
REASON_WINDOW_FILTERED = "publication_window_filtered"
REASON_NO_QUOTES = "no_quotes_extracted"


def _dedupe_results(search_results):
    seen_urls = set()
    unique = []
    for r in search_results:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique.append(r)
    return unique


def _within_publication_window(
    published_at: Optional[datetime],
    match_date: datetime,
    now: Optional[datetime] = None,
) -> bool:
    if now is None:
        now = datetime.now()
    if published_at is None:
        # Undated articles cannot be checked against the match window.
        # Only accept them for games recent enough that a freshly
        # discovered article could plausibly be about them; otherwise a
        # current article would be misattributed to an old match.
        return now - PUBLICATION_WINDOW <= match_date
    diff = published_at - match_date
    return timedelta(0) <= diff <= PUBLICATION_WINDOW


def collect_comments_for_coach(
    game: Dict[str, Any],
    coach: str,
    search_provider: Any,
    fetcher: Any,
    extractor: Any,
    sitemap_entries: List = None,
) -> tuple:
    """
    Collects referee-related quotes for one coach in one game.
    Returns (quotes, failure_reason). Exactly one of them is None.
    """
    is_home = game["home_coach"] == coach
    opponent_team = game["away_team"] if is_home else game["home_team"]
    match_date = datetime.strptime(game["date"], "%Y-%m-%d")
    now = datetime.now()

    # Primary discovery: fresh articles from trusted-outlet news sitemaps
    # (keyless, reliable for games played in the last ~48h). Sitemap
    # articles are at most a couple of days old, so for games older than
    # twice the publication window they can never pass the window filter
    # and fetching them would be futile.
    candidates = []
    if sitemap_entries and match_date >= now - 2 * PUBLICATION_WINDOW:
        candidates.extend(find_coach_articles(sitemap_entries, coach))

    # Fallback discovery: search engines. The query is date-bounded to
    # this game's publication window (after:/before: on Google News), so
    # games older than the window stay searchable within their own 48h.
    date_range = (
        match_date.date(),
        (match_date + PUBLICATION_WINDOW + timedelta(days=1)).date(),
    )
    queries = build_queries(coach, opponent_team, match_date.date())
    search_results = []
    for q in queries:
        search_results.extend(search_provider.search(q, date_range=date_range))
    candidates.extend(search_results)

    unique_results = _dedupe_results(candidates)
    if not unique_results:
        return None, REASON_NO_RESULTS

    trusted = [r for r in unique_results if is_allowed_source(r.url)]
    if not trusted:
        return None, REASON_NO_TRUSTED

    documents: List[SourceDocument] = []
    fetch_failures = 0
    window_filtered = 0
    for result in trusted:
        if len(documents) >= MAX_DOCS_PER_COACH:
            break
        try:
            doc = fetcher.fetch(result.url)
        except Exception as e:
            print(f"Fetch failed for {result.url}: {e}")
            fetch_failures += 1
            continue
        if doc.published_at is None and result.published is not None:
            doc.published_at = result.published
        if not _within_publication_window(doc.published_at, match_date):
            window_filtered += 1
            continue
        documents.append(doc)

    if not documents:
        if window_filtered and fetch_failures < len(trusted):
            return None, REASON_WINDOW_FILTERED
        return None, REASON_FETCH_FAILED

    quotes = []
    for doc in documents:
        extracted = extractor.extract(coach, game["game_id"], doc)
        validated = validate_extractions(extracted, doc)
        quotes.extend(validated)

    quotes = deduplicate_quotes(quotes)
    if not quotes:
        return None, REASON_NO_QUOTES

    merged = {
        "text": " ".join(q["text"] for q in quotes),
        "sources": [doc.url for doc in documents],
        "source": documents[0].source_name,
        "published_at": min(
            (doc.published_at for doc in documents if doc.published_at),
            default=None,
        ),
    }
    return merged, None


def _pending_key(game_id: str, coach: str) -> tuple:
    return (game_id, coach)


def _update_pending(pending: List[Dict], game: Dict, coach: str, reason: str) -> None:
    key = _pending_key(game["game_id"], coach)
    entry = next((p for p in pending if _pending_key(p["game_id"], p["coach"]) == key), None)
    if entry is None:
        pending.append({
            "game_id": game["game_id"],
            "coach": coach,
            "date": game["date"],
            "attempts": 1,
            "last_attempt": datetime.utcnow().isoformat(),
            "reason": reason,
        })
    else:
        entry["attempts"] += 1
        entry["last_attempt"] = datetime.utcnow().isoformat()
        entry["reason"] = reason


def _drop_pending(pending: List[Dict], game_id: str, coach: str) -> None:
    pending[:] = [p for p in pending if _pending_key(p["game_id"], p["coach"]) != _pending_key(game_id, coach)]


def collect_matchday_comments(api_key: str = None, search_provider: Any = None, retry_pending: bool = False):
    games = get_games()
    comments = get_comments()
    pending = get_pending_requests()

    if retry_pending:
        exhausted = [p for p in pending if p.get("attempts", 0) >= MAX_ATTEMPTS]
        for p in exhausted:
            p["attempts"] = 0
        print(f"Retry requested: reset {len(exhausted)} exhausted pending request(s).")

    if search_provider is None:
        search_provider = get_search_provider(api_key)
    fetcher = ArticleFetcher()
    extractor = get_extractor()
    sitemap_entries = fetch_sitemap_entries()

    today = date.today()
    sought_count = 0
    found_count = 0
    skipped_future = 0
    skipped_max_attempts = 0
    already_in_db = 0

    for game in games:
        match_date = datetime.strptime(game["date"], "%Y-%m-%d").date()
        if match_date > today:
            skipped_future += 1
            continue

        for coach_key in ["home_coach", "away_coach"]:
            coach = game[coach_key]
            game_id = game["game_id"]

            if any(c["game_id"] == game_id and c["coach"] == coach for c in comments):
                already_in_db += 1
                continue

            pending_entry = next(
                (p for p in pending if _pending_key(p["game_id"], p["coach"]) == _pending_key(game_id, coach)),
                None,
            )
            if pending_entry and pending_entry.get("attempts", 0) >= MAX_ATTEMPTS:
                skipped_max_attempts += 1
                continue

            sought_count += 1
            print(f"Collecting comments from {coach} for game {game_id} ({game['date']})...")
            try:
                result, reason = collect_comments_for_coach(
                    game, coach, search_provider, fetcher, extractor, sitemap_entries
                )
            except Exception as e:
                print(f"Failed to collect for {coach} in game {game_id}: {e}")
                result, reason = None, REASON_FETCH_FAILED

            if result is not None:
                found_count += 1
                comments.append({
                    "game_id": game_id,
                    "coach": coach,
                    "quote": result["text"],
                    "source_url": result["sources"][0],
                    "sources": result["sources"],
                    "source_name": result["source"],
                    "published_at": result["published_at"].isoformat() if result["published_at"] else None,
                    "retrieved_at": datetime.utcnow().isoformat(),
                })
                _drop_pending(pending, game_id, coach)
            else:
                _update_pending(pending, game, coach, reason)

    save_comments(comments)
    save_pending_requests(pending)

    pending_active = [p for p in pending if p.get("attempts", 0) < MAX_ATTEMPTS]
    print(f"--- Collection Report ---")
    print(f"Matches in calendar: {len(games)} (future, skipped: {skipped_future})")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments already in DB: {already_in_db}")
    print(f"Comments found: {found_count}")
    print(f"Pending (will retry): {len(pending_active)}")
    print(f"Gave up after {MAX_ATTEMPTS} attempts: {skipped_max_attempts}")
    for p in pending_active:
        print(f"  - {p['game_id']} | {p['coach']} | {p['reason']} (attempt {p['attempts']})")
    print(f"----------------------------")
