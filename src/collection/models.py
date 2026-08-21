from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str

@dataclass
class SourceDocument:
    url: str
    title: str
    text: str
    published_at: Optional[datetime]
    source_name: str
