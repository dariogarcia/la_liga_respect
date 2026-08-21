import requests
from .models import SourceDocument
from datetime import datetime
from typing import Optional

class ArticleFetcher:
    def fetch(self, url: str) -> SourceDocument:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "LaLigaRespectBot/1.0"
            },
        )
        response.raise_for_status()
        
        # This is a simplified extraction. In a real system, we would use
        # a library like trafilatura or newspaper3k.
        text = response.text
        title = "Unknown Title"
        
        return SourceDocument(
            url=url,
            title=title,
            text=text,
            published_at=None, # Date extraction is complex without libraries
            source_name=url
        )
