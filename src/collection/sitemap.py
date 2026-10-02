"""Keyless article discovery via publisher news sitemaps.

News sitemaps list each outlet's most recent articles (typically the last
24-48h) with titles and publication dates. Because the collection pipeline
only accepts quotes published within 48h of the match, these sitemaps are a
reliable, search-engine-free way to discover fresh press-conference articles
on trusted domains.
"""
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Optional

from . import cache
from .models import SearchResult
from ..utils import http
from ..utils.ratelimit import SITEMAP_RATE_LIMITER
from ..utils.useragent import BOT_USER_AGENT

USER_AGENT = BOT_USER_AGENT

NEWS_SITEMAPS = {
    # as.com also publishes https://as.com/sitemaps/news.xml but its
    # article pages block datacenter IPs (HTTP 403), so it is not listed.
    # sport.es serves its news sitemap with HTTP 406 to us and its
    # article pages are blocklisted anyway (Wayback-only), so it was
    # removed here; search engines still surface its articles.
    "mundodeportivo.com": "https://www.mundodeportivo.com/sitemap-news-v7.xml",
    "relevo.com": "https://www.relevo.com/sitemap-news.xml",
    # Vocento regional daily: declares its news sitemap in robots.txt
    # and serves articles without bot blocking.
    "estadiodeportivo.com": "https://www.estadiodeportivo.com/sitemaps/news.xml",
}

# Terms that make an article more likely to contain referee-related quotes.
REFEREE_TERMS = (
    "arbitro", "arbitraje", "arbitral", "penalti", "pitido",
    "rueda de prensa", "prensa", "declaraciones", "directo",
)

MAX_ARTICLES_PER_COACH = 6

_entries_cache: Optional[List[SearchResult]] = None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def parse_sitemap(xml_text) -> List[SearchResult]:
    """Parses a news sitemap into SearchResults (url + title, no snippet).

    Accepts bytes (preferred, encoding is read from the XML declaration)
    or str.
    """
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"Sitemap parse error: {e}")
        return results

    for url_el in root.iter():
        if _local_name(url_el.tag) != "url":
            continue
        loc = None
        title = None
        for descendant in url_el.iter():
            name = _local_name(descendant.tag)
            if name == "loc" and descendant.text and loc is None:
                loc = descendant.text.strip()
            elif name == "title" and descendant.text and title is None:
                title = descendant.text.strip()
        if not loc or not loc.startswith("http"):
            continue
        results.append(SearchResult(url=loc, title=title or "", snippet=""))
    return results


def fetch_sitemap_entries(force_refresh: bool = False) -> List[SearchResult]:
    """Fetches all configured news sitemaps. Cached for the process lifetime."""
    global _entries_cache
    if _entries_cache is not None and not force_refresh:
        return _entries_cache

    all_entries = []
    seen = set()
    for domain, sitemap_url in NEWS_SITEMAPS.items():
        try:
            # On-disk cache (A4): sitemaps are refreshed at most once per
            # 24h even across interrupted or repeated runs.
            response = cache.cache_get(sitemap_url)
            if response is None:
                SITEMAP_RATE_LIMITER.wait()
                response = http.http_get(
                    sitemap_url, headers={"User-Agent": USER_AGENT}, timeout=20
                )
                if response.status_code == 200:
                    cache.cache_put(
                        sitemap_url, 200, response.content, ttl=cache.TTL_SITEMAP_SECONDS
                    )
            if response.status_code != 200:
                print(f"Sitemap for {domain} returned HTTP {response.status_code}, skipping.")
                continue
            entries = parse_sitemap(response.content)
        except Exception as e:
            print(f"Sitemap fetch failed for {domain}: {e}")
            continue
        added = 0
        for entry in entries:
            if entry.url not in seen:
                seen.add(entry.url)
                all_entries.append(entry)
                added += 1
        print(f"Sitemap {domain}: {added} articles")
    _entries_cache = all_entries
    return all_entries


def find_coach_articles(
    entries: List[SearchResult],
    coach: str,
    max_results: int = MAX_ARTICLES_PER_COACH,
) -> List[SearchResult]:
    """Finds articles whose title mentions the coach, ranked by relevance.

    Matching uses the coach's most distinctive name token (the surname for
    Spanish-style names). Articles mentioning referee terms or more coach
    name tokens rank higher.
    """
    tokens = [_normalize(t) for t in coach.split() if len(t) > 2]
    if not tokens:
        return []
    surname = tokens[-1]

    scored = []
    for entry in entries:
        title = _normalize(entry.title)
        if not title or surname not in title:
            continue
        token_hits = sum(1 for t in tokens if t in title)
        referee_bonus = 1 if any(term in title for term in REFEREE_TERMS) else 0
        score = token_hits + 2 * referee_bonus
        scored.append((score, entry))

    scored.sort(key=lambda pair: -pair[0])
    return [entry for _, entry in scored[:max_results]]
