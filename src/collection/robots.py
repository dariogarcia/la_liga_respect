"""robots.txt compliance for outbound article fetches (RFC 9309).

Every article URL is checked against its origin's robots.txt before it
is fetched. Rules are downloaded once per origin per process and cached,
so a collection run costs each publisher at most one robots.txt request
in addition to the article fetches themselves.

Status handling follows RFC 9309:
- 2xx: the rules are parsed and applied to our bot token.
- 3xx: followed by requests, then treated as above.
- 4xx (including 404): no rules exist, everything is allowed.
- 5xx or network error: conservatively disallowed for this run.
"""

from typing import Dict, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from ..utils import http
from ..utils.ratelimit import FETCH_RATE_LIMITER
from ..utils.useragent import BOT_UA_TOKEN, BOT_USER_AGENT


class RobotsPolicy:
    """Per-origin robots.txt cache with an injectable HTTP session."""

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or http.shared_session()
        self._parsers: Dict[str, RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._parsers.get(origin)
        if parser is None:
            parser = self._load(origin)
            self._parsers[origin] = parser
        return parser.can_fetch(BOT_UA_TOKEN, url)

    def _load(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            FETCH_RATE_LIMITER.wait()
            response = self.session.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": BOT_USER_AGENT},
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                parser.parse(response.text.splitlines())
            elif 400 <= response.status_code < 500:
                # 4xx: no rules exist for this origin, allow all.
                parser.allow_all = True
            else:
                # 5xx: the origin is unreachable in a rules sense; be
                # conservative and disallow for this run.
                parser.disallow_all = True
                print(f"robots.txt for {origin} returned HTTP {response.status_code}, disallowing fetches this run.")
        except requests.RequestException as e:
            parser.disallow_all = True
            print(f"robots.txt fetch failed for {origin} ({e}), disallowing fetches this run.")
        return parser


class AllowAllRobots:
    """Test/stub policy that permits every URL."""

    def allowed(self, url: str) -> bool:
        return True


_SHARED_POLICY: Optional[RobotsPolicy] = None


def shared_robots_policy() -> RobotsPolicy:
    """Process-wide cache so repeated ArticleFetcher instances share rules."""
    global _SHARED_POLICY
    if _SHARED_POLICY is None:
        _SHARED_POLICY = RobotsPolicy()
    return _SHARED_POLICY
