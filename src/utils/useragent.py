"""Outbound User-Agent policy.

- BOT_USER_AGENT is the honest, identifiable bot string used for every
  request where Respect Rank acts as a crawler against publisher
  infrastructure: article fetches, news sitemaps and robots.txt. Never
  spoof a browser for these.
- BROWSER_USER_AGENT is used ONLY by the keyless scraped search
  endpoints (DuckDuckGo HTML, Bing), which reject non-browser agents.
  These endpoints are the least compliant part of the pipeline and are
  slated for replacement by official APIs/RSS feeds.
- Google News RSS must be fetched with a plain requests session
  (default User-Agent): google.com serves a consent redirect to browser
  UAs. See src/collection/search.py.
"""

BOT_UA_TOKEN = "RespectRankBot"
BOT_USER_AGENT = "RespectRankBot/1.0 (+https://github.com/dariogarcia/la_liga_respect)"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
