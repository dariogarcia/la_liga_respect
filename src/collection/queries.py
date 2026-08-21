from datetime import date
from typing import List

def build_queries(coach: str, opponent: str, match_date: date) -> List[str]:
    date_str = match_date.isoformat()
    return [
        f'"{coach}" "{opponent}" referee interview La Liga {date_str}',
        f'"{coach}" "{opponent}" árbitro rueda de prensa {date_str}',
        f'"{coach}" "{opponent}" árbitro declaraciones {date_str}',
        f'"{coach}" "{opponent}" referee post match {date_str}',
    ]
