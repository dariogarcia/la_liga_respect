from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .filtering import get_domain
from .models import SourceDocument
from ..utils.ratelimit import FETCH_RATE_LIMITER

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

DATE_META_PROPERTIES = [
    "article:published_time",
    "og:article:published_time",
    "article:modified_time",
    "og:updated_time",
]
DATE_META_NAMES = [
    "parsely-pub-date",
    "sailthru.date",
    "date",
    "DC.date.issued",
    "DC.date",
    "publish-date",
    "publication_date",
]
DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%Y/%m/%d",
]


def parse_date_string(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    iso = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.split(" ")[0], fmt)
        except ValueError:
            continue
    return None


class ArticleFetcher:
    """Fetches an article URL and extracts clean text, title and publish date."""

    def fetch(self, url: str) -> SourceDocument:
        FETCH_RATE_LIMITER.wait()
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.5",
            },
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        return SourceDocument(
            url=url,
            title=self.extract_title(soup),
            text=self.extract_text(soup),
            published_at=self.extract_published(soup),
            source_name=get_domain(url),
        )

    def extract_title(self, soup: BeautifulSoup) -> str:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            return og["content"].strip()
        twitter = soup.find("meta", attrs={"name": "twitter:title"})
        if twitter and twitter.get("content"):
            return twitter["content"].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return "Unknown Title"

    def extract_published(self, soup: BeautifulSoup) -> Optional[datetime]:
        for prop in DATE_META_PROPERTIES:
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content"):
                dt = parse_date_string(tag["content"])
                if dt:
                    return dt
        for name in DATE_META_NAMES:
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                dt = parse_date_string(tag["content"])
                if dt:
                    return dt
        for el in soup.find_all("time"):
            raw = el.get("datetime") or el.get_text(strip=True)
            dt = parse_date_string(raw)
            if dt:
                return dt
        return None

    def extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "header", "footer", "aside",
                         "figure", "noscript", "form", "iframe", "svg"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
