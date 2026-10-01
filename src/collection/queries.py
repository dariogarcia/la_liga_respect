from datetime import date
from typing import List

# Site-restricted variants are included because the keyless engines
# answer them more reliably, and they target the trusted outlets.
SITE_RESTRICTED_DOMAINS = ["marca.com", "as.com", "sport.es", "mundodeportivo.com"]


def build_queries(coach: str, opponent: str, match_date: date) -> List[str]:
    queries = [
        # Quoted variants work best on Google News and DuckDuckGo.
        f'"{coach}" "{opponent}" árbitro rueda de prensa',
        f'"{coach}" "{opponent}" arbitraje declaraciones',
        # Unquoted variants are needed for Bing.
        f"{coach} {opponent} árbitro rueda de prensa",
        f"{coach} rueda de prensa tras el partido {opponent}",
        f'"{coach}" "{opponent}" referee post match interview',
    ]
    for domain in SITE_RESTRICTED_DOMAINS:
        queries.append(f"{coach} {opponent} rueda de prensa árbitro site:{domain}")
    return queries
