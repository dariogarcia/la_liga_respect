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

import json
import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Any
from src.data.manager import get_games, get_comments, save_comments
from .models import SourceDocument
from .queries import build_queries
from .search import WebSearchProvider
from .filtering import is_allowed_source
from .fetcher import ArticleFetcher
from .extractor import QuoteExtractor
from .validation import validate_extractions
from .deduplication import deduplicate_quotes

def collect_comments_for_coach(
    game: Dict[str, Any],
    coach: str,
    search_provider: Any,
    fetcher: Any,
    extractor: Any,
) -> List[Dict[str, Any]]:
    # Determine opponent
    opponent = game["away_coach"] if game["home_coach"] == coach else game["home_coach"]
    
    # Match date as datetime object
    match_date = datetime.strptime(game["date"], "%Y-%m-%d")
    
    queries = build_queries(coach, opponent, match_date.date())
    search_results = []
    for q in queries:
        search_results.extend(search_provider.search(q))
    
    # Deduplicate URLs
    seen_urls = set()
    unique_results = []
    for r in search_results:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_results.append(r)
            
    documents = []
    for result in unique_results:
        if not is_allowed_source(result.url):
            continue
        try:
            doc = fetcher.fetch(result.url)
            
            # ENFORCE 48-HOUR WINDOW
            if doc.published_at:
                diff = doc.published_at - match_date
                if diff.days > 2 or diff.total_seconds() < 0:
                    continue
            elif doc.published_at is None:
                # If date is missing, we keep it but flag for agent validation
                pass
                
            documents.append(doc)
        except Exception as e:
            print(f"Fetch failed for {result.url}: {e}")
            continue
            
    quotes = []
    for doc in documents:
        extracted = extractor.extract(coach, game["game_id"], doc)
        
        # If extraction returned a request for the agent, we can't proceed automatically
        if extracted and isinstance(extracted[0], dict) and extracted[0].get("status") == "AGENT_REQUIRED":
            # For this automated pipeline, we treat these as "Pending for Agent"
            continue
            
        validated = validate_extractions(extracted, doc)
        quotes.extend(validated)
        
    return deduplicate_quotes(quotes)

def collect_matchday_comments(api_key: str = None):
    games = get_games()
    comments = get_comments()
    
    search_provider = WebSearchProvider(api_key=api_key) if api_key else None
    fetcher = ArticleFetcher()
    extractor = QuoteExtractor()
    
    if not search_provider:
        print("Error: API key required for collection. Skipping.")
        return

    sought_count = 0
    found_count = 0
    
    for game in games:
        for coach_key in ["home_coach", "away_coach"]:
            coach = game[coach_key]
            game_id = game["game_id"]
            
            if not any(c["game_id"] == game_id and c["coach"] == coach for c in comments):
                sought_count += 1
                try:
                    new_quotes = collect_comments_for_coach(
                        game, coach, search_provider, fetcher, extractor
                    )
                    if new_quotes:
                        found_count += len(new_quotes)
                        for q in new_quotes:
                            comments.append({
                                "game_id": game_id,
                                "coach": coach,
                                "quote": q["text"],
                                "source_url": q["url"],
                                "source_name": q["source"],
                                "published_at": q.get("published_at"),
                                "retrieved_at": datetime.utcnow().isoformat()
                            })
                except Exception as e:
                    print(f"Failed to collect for {coach} in game {game_id}: {e}")

    save_comments(comments)
    
    print(f"--- Collection Report ---")
    print(f"Matches processed: {len(games)}")
    print(f"Comments already in DB: {len(comments) - found_count}")
    print(f"Coach comments sought: {sought_count}")
    print(f"Comments found: {found_count}")
    print(f"----------------------------")







