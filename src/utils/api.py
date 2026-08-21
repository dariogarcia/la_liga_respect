import requests
from typing import List, Dict, Optional

class LaLigaAPI:
    """
    A handler for fetching La Liga data. 
    Designed to be called by LLM agents to automate data retrieval.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://api.football-data.org/v4"

    def get_current_matches(self) -> List[Dict]:
        """
        Fetches recent matches from La Liga (PD).
        Returns a list of matches with home/away teams and dates.
        """
        if not self.api_key:
            print("Warning: No API key provided. Returning empty list.")
            return []

        headers = {"X-Auth-Token": self.api_key}
        try:
            # 'PD' is the code for Primera División (La Liga)
            response = requests.get(f"{self.base_url}/competitions/PD/matches", headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            matches = []
            for match in data.get("matches", []):
                matches.append({
                    "match_id": match["id"],
                    "utcDate": match["utcDate"],
                    "homeTeam": match["homeTeam"]["name"],
                    "awayTeam": match["awayTeam"]["name"],
                    "score": match.get("score", {})
                })
            return matches
        except requests.RequestException as e:
            print(f"API Error fetching matches: {e}")
            return []

    def get_coach_quotes(self, coach_name: str, match_id: str) -> str:
        """
        Since no public API provides direct coach quotes, this method returns 
         a structured search query that a calling LLM agent can use to 
         retrieve the quote via web search.
        """
        return f"SEARCH_QUERY: {coach_name} la liga interview match {match_id} referee comments"
