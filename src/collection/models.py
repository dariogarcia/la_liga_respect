from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    # Publication date from the discovery source (e.g. Google News RSS
    # pubDate); used as a fallback when the article page is undated.
    published: Optional[datetime] = None

@dataclass
class SourceDocument:
    url: str
    title: str
    text: str
    published_at: Optional[datetime]
    source_name: str
