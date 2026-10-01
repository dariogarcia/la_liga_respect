import time
from datetime import datetime, timedelta

import requests
from typing import Dict, List, Optional


class LaLigaAPI:
    """
    A handler for fetching La Liga data from football-data.org.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.football-data.org/v4"

    def get_matches(self) -> List[Dict]:
        """
        Fetches all matches of the current La Liga (PD) season.
        Returns a list of dicts with match_id, utcDate, status, homeTeam, awayTeam.
        """
        if not self.api_key:
            print("Warning: No football-data.org API key provided. Returning empty list.")
            return []

        headers = {"X-Auth-Token": self.api_key}
        try:
            response = requests.get(
                f"{self.base_url}/competitions/PD/matches",
                headers=headers,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            matches = []
            for match in data.get("matches", []):
                matches.append({
                    "match_id": str(match["id"]),
                    "utcDate": match["utcDate"],
                    "status": match.get("status"),
                    "homeTeam": match["homeTeam"]["name"],
                    "awayTeam": match["awayTeam"]["name"],
                })
            return matches
        except requests.RequestException as e:
            print(f"API Error fetching matches: {e}")
            return []

    def get_finished_matches(self) -> List[Dict]:
        """
        Returns only matches whose status is FINISHED.
        """
        return [m for m in self.get_matches() if m.get("status") == "FINISHED"]

    def get_current_matches(self) -> List[Dict]:
        """
        Backwards-compatible alias for get_matches().
        """
        return self.get_matches()

    def get_coach_quotes(self, coach_name: str, match_id: str) -> str:
        """
        Since no public API provides direct coach quotes, this method returns
        a structured search query that a calling LLM agent can use to
        retrieve the quote via web search.
        """
        return f"SEARCH_QUERY: {coach_name} la liga interview match {match_id} referee comments"


class ESPNLaLigaAPI:
    """
    Keyless La Liga fixture source using ESPN's public scoreboard API.

    Used as a fallback when no football-data.org API key is available.
    The scoreboard endpoint only accepts single dates, so a date range is
    scanned one day at a time. Returns matches in the same dict shape as
    LaLigaAPI (match_id, utcDate, status, homeTeam, awayTeam).
    """

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"
    FINISHED_STATUSES = {"STATUS_FULL_TIME", "STATUS_FINAL"}

    # ESPN display names that do not token-match the teams.json names.
    TEAM_ALIASES = {
        "Athletic Club": "Athletic Bilbao",
        "Deportivo": "Deportivo A Coruña",
    }

    def __init__(self, start_date: str, end_date: str, delay: float = 0.3):
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RespectRank/1.0 (fixture sync)",
            "Accept": "*/*",
        })

    def _extract_match(self, event: Dict) -> Optional[Dict]:
        try:
            competitors = event["competitions"][0]["competitors"]
            home = next(c for c in competitors if c.get("homeAway") == "home")
            away = next(c for c in competitors if c.get("homeAway") == "away")

            def name_of(competitor):
                name = competitor["team"]["displayName"]
                return self.TEAM_ALIASES.get(name, name)

            return {
                "match_id": str(event["id"]),
                "utcDate": event["date"],
                "status": event.get("status", {}).get("type", {}).get("name"),
                "homeTeam": name_of(home),
                "awayTeam": name_of(away),
            }
        except (KeyError, IndexError, StopIteration):
            return None

    def get_matches(self) -> List[Dict]:
        matches: List[Dict] = []
        seen_ids = set()
        errors = 0
        day = self.start_date
        while day <= self.end_date:
            try:
                response = self.session.get(
                    self.BASE_URL, params={"dates": day.strftime("%Y%m%d")}, timeout=20
                )
                response.raise_for_status()
                for event in response.json().get("events", []):
                    match = self._extract_match(event)
                    if match and match["match_id"] not in seen_ids:
                        seen_ids.add(match["match_id"])
                        matches.append(match)
            except (requests.RequestException, ValueError) as e:
                errors += 1
                print(f"ESPN API error for {day.isoformat()}: {e}")
            day = day + timedelta(days=1)
            if day <= self.end_date:
                time.sleep(self.delay)
        if errors and not matches:
            print(f"ESPN API: failed on all {errors} requested day(s).")
        return matches

    def get_finished_matches(self) -> List[Dict]:
        return [m for m in self.get_matches() if m.get("status") in self.FINISHED_STATUSES]
