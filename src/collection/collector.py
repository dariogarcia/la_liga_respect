from datetime import datetime, date, timedelta
import os
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
from .extractor import get_extractor, is_candidate_document, batch_enabled, mentions_coach
from .validation import validate_extractions
from .deduplication import deduplicate_quotes

MAX_DOCS_PER_COACH = 6
MAX_ATTEMPTS = 5
PUBLICATION_WINDOW = timedelta(days=2)
# User semantics: every game must resolve. A coach who made no
# referee-related comment within this many days after his game is
# presumed respectful for it (score 3). Gathering itself has no
# deadline: full runs keep seeking old games (Wayback can still
# recover quotes); only the *presumption* is time-based.
PRESUMPTION_WINDOW = timedelta(days=int(os.getenv("PRESUME_AFTER_DAYS", "14")))

REASON_NO_RESULTS = "no_search_results"
REASON_NO_TRUSTED = "no_trusted_sources"
REASON_FETCH_FAILED = "fetch_failed"
REASON_WINDOW_FILTERED = "publication_window_filtered"
REASON_NO_QUOTES = "no_quotes_extracted"

# Terminal outcomes stored as comments (not pending failures).
KIND_CONFIRMED_CLEAN = "confirmed"
KIND_PRESUMED_CLEAN = "presumed"


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
    # Skipped when trusted sitemap candidates already saturate the
    # document budget (C3: prefer sitemaps over scraped engines).
    trusted_candidates = [r for r in candidates if is_allowed_source(r.url)]
    search_results = []
    if len(trusted_candidates) < MAX_DOCS_PER_COACH:
        date_range = (
            match_date.date(),
            (match_date + PUBLICATION_WINDOW + timedelta(days=1)).date(),
        )
        queries = build_queries(coach, opponent_team, match_date.date())
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

    # Cheap local check before (potentially LLM-backed) extraction:
    # skip documents that cannot yield referee quotes from this coach.
    candidate_docs = [doc for doc in documents if is_candidate_document(coach, doc)]
    skipped_prefilter = len(documents) - len(candidate_docs)

    quotes = []
    batches = None
    if (
        len(candidate_docs) > 1
        and batch_enabled()
        and getattr(extractor, "extract_batch", None) is not None
    ):
        # B3: one LLM call for all of the coach's documents. Any
        # failure falls back to per-document extraction.
        try:
            batches = extractor.extract_batch(coach, game["game_id"], candidate_docs)
            if len(batches) != len(candidate_docs):
                batches = None
        except Exception as e:
            print(f"Batch extraction failed for {coach}, falling back per-document: {e}")
            batches = None

    if batches is not None:
        for doc, extracted in zip(candidate_docs, batches):
            quotes.extend(validate_extractions(extracted, doc))
    else:
        for doc in candidate_docs:
            extracted = extractor.extract(coach, game["game_id"], doc)
            validated = validate_extractions(extracted, doc)
            quotes.extend(validated)

    if skipped_prefilter:
        print(
            f"Pre-filter skipped {skipped_prefilter}/{len(documents)} document(s) "
            f"for {coach} (no coach mention or no referee keywords)."
        )

    quotes = deduplicate_quotes(quotes)
    if not quotes:
        # No referee-related quotes. Was the coach quoted at all? If the
        # coverage exists but never mentions the referee, the game
        # resolves as respectful silence instead of a retryable failure.
        coach_docs = [doc for doc in documents if mentions_coach(coach, doc)]
        assess = getattr(extractor, "assess_coverage", None)
        if coach_docs and assess and assess(coach, coach_docs):
            return {
                "clean": KIND_CONFIRMED_CLEAN,
                "sources": [doc.url for doc in documents],
                "source": documents[0].source_name,
                "published_at": min(
                    (doc.published_at for doc in documents if doc.published_at),
                    default=None,
                ),
            }, None
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


def _clean_comment(game: Dict, coach: str, kind: str, result: Optional[Dict] = None) -> Dict:
    """
    Builds the terminal comment entry for a coach-game pair that
    resolves without a referee quote: score 3, because not commenting
    on the referee is the respectful baseline (user semantics).
    """
    sources = (result or {}).get("sources") or []
    published = (result or {}).get("published_at")
    if kind == KIND_CONFIRMED_CLEAN:
        justification = "The coach was quoted in the match coverage but made no comment about the referee."
    else:
        justification = (
            f"No referee-related comment found within {PRESUMPTION_WINDOW.days} days "
            f"of the game; presumed respectful."
        )
    return {
        "game_id": game["game_id"],
        "coach": coach,
        "quote": "",
        "no_ref_comment": True,
        "kind": kind,
        "score": 3,
        "graded_by": "coverage",
        "justification": justification,
        "sources": sources,
        "source_url": sources[0] if sources else None,
        "source_name": (result or {}).get("source"),
        "published_at": published.isoformat() if published else None,
        "retrieved_at": datetime.utcnow().isoformat(),
    }


def collect_matchday_comments(
    api_key: str = None,
    search_provider: Any = None,
    retry_pending: bool = False,
    since: Optional[date] = None,
) -> Dict[str, Any]:
    """Collects coach comments for unfinished targets.

    Every coach-game pair resolves (user semantics):
    - referee quotes found -> graded comment;
    - coach quoted but no referee mention -> confirmed clean (3);
    - game older than PRESUMPTION_WINDOW with nothing found -> presumed
      clean (3);
    - fresh game unresolved -> pending, retried next run.
    Gathering has no deadline: full runs (since=None) keep seeking old
    games so archive fallback can still recover quotes; weekly runs
    (since set) settle already-sought old games as presumed clean
    without re-seeking.
    Returns a stats dict for the run report (A5).
    """
    games = get_games()
    comments = get_comments()
    pending = get_pending_requests()

    if retry_pending:
        exhausted = [
            p for p in pending
            if p.get("attempts", 0) >= MAX_ATTEMPTS and not p.get("terminal")
        ]
        for p in exhausted:
            p["attempts"] = 0
        print(f"Retry requested: reset {len(exhausted)} exhausted pending request(s).")
        if exhausted:
            save_pending_requests(pending)

    if search_provider is None:
        search_provider = get_search_provider(api_key)
    fetcher = ArticleFetcher()
    extractor = get_extractor()
    sitemap_entries = fetch_sitemap_entries()

    today = date.today()
    sought_count = 0
    found_count = 0
    confirmed_clean = 0
    presumed_clean = 0
    skipped_future = 0
    skipped_since = 0
    skipped_max_attempts = 0
    already_in_db = 0

    for game in games:
        match_date = datetime.strptime(game["date"], "%Y-%m-%d").date()
        if match_date > today:
            skipped_future += 1
            continue

        stale = match_date < today - PRESUMPTION_WINDOW

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

            if stale and since is not None and match_date < since:
                # Weekly window over an old game: settle it as presumed
                # clean (it was already sought while fresh) instead of
                # re-seeking. Games never sought before are left for a
                # full run.
                if pending_entry is not None and pending_entry.get("attempts", 0) >= 1:
                    comments.append(_clean_comment(game, coach, KIND_PRESUMED_CLEAN))
                    _drop_pending(pending, game_id, coach)
                    presumed_clean += 1
                    save_comments(comments)
                    save_pending_requests(pending)
                else:
                    skipped_since += 1
                continue

            if not stale:
                # A3: outside the requested window: retryable, not sought.
                if since is not None and match_date < since:
                    skipped_since += 1
                    continue
                if pending_entry and pending_entry.get("attempts", 0) >= MAX_ATTEMPTS:
                    skipped_max_attempts += 1
                    continue
                if pending_entry and pending_entry.get("terminal"):
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

            if result is not None and result.get("clean") == KIND_CONFIRMED_CLEAN:
                comments.append(_clean_comment(game, coach, KIND_CONFIRMED_CLEAN, result))
                _drop_pending(pending, game_id, coach)
                confirmed_clean += 1
            elif result is not None:
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
            elif stale:
                # Sought and still nothing: the presumption window has
                # passed, resolve as respectful silence.
                comments.append(_clean_comment(game, coach, KIND_PRESUMED_CLEAN))
                _drop_pending(pending, game_id, coach)
                presumed_clean += 1
            else:
                _update_pending(pending, game, coach, reason)

            # Persist after every sought target so an interruption
            # (crash, Ctrl-C, reboot) never loses collected work.
            save_comments(comments)
            save_pending_requests(pending)

    save_comments(comments)
    save_pending_requests(pending)

    pending_active = [p for p in pending if p.get("attempts", 0) < MAX_ATTEMPTS]
    print(f"--- Collection Report ---")
    print(f"Matches in calendar: {len(games)} (future, skipped: {skipped_future})")
    if since is not None:
        print(f"Window: games since {since.isoformat()} (older, unresolved, skipped: {skipped_since})")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments already in DB: {already_in_db}")
    print(f"Comments found: {found_count}")
    print(f"Resolved clean — coach quoted, no referee comment: {confirmed_clean}")
    print(f"Resolved clean — presumed respectful ({PRESUMPTION_WINDOW.days}d+ old): {presumed_clean}")
    print(f"Pending (will retry): {len(pending_active)}")
    print(f"Gave up after {MAX_ATTEMPTS} attempts: {skipped_max_attempts}")
    for p in pending_active:
        print(f"  - {p['game_id']} | {p['coach']} | {p['reason']} (attempt {p['attempts']})")
    print(f"----------------------------")
    return {
        "games_in_calendar": len(games),
        "skipped_future": skipped_future,
        "skipped_since": skipped_since,
        "sought": sought_count,
        "found": found_count,
        "confirmed_clean": confirmed_clean,
        "presumed_clean": presumed_clean,
        "already_in_db": already_in_db,
        "pending_active": len(pending_active),
    }
