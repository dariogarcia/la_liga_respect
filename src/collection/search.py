from typing import Protocol, List
import requests
from .models import SearchResult

class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[SearchResult]:
        ...

class WebSearchProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.serpapi.com/search"

    def search(self, query: str, max_results: int = 10) -> List[SearchResult]:
        params = {
            "q": query,
            "api_key": self.api_key,
            "num": max_results
        }
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for org_result in data.get("organic_results", []):
                results.append(SearchResult(
                    url=org_result.get("link", ""),
                    title=org_result.get("title", ""),
                    snippet=org_result.get("snippet", "")
                ))
            return results
        except Exception as e:
            print(f"Search error for query '{query}': {e}")
            return []
