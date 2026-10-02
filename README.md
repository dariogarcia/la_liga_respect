# 🏆 Respect Rank: La Liga Coach Edition

[![CI](https://github.com/dariogarcia/la_liga_respect/actions/workflows/ci.yml/badge.svg)](https://github.com/dariogarcia/la_liga_respect/actions/workflows/ci.yml)

Respect Rank is an agentic system designed to monitor and rank La Liga football managers based on their level of respect for referees during post-game interviews.

> ⚠️ **Read [NOTICE.md](NOTICE.md) before relying on this data.** The system is fully automated: quotes may be misattributed, scores are subjective machine-generated judgments, and quoted text remains the property of its publishers (takedown requests welcome). Code is MIT-licensed; compiled data is not covered — see `LICENSE` and `NOTICE.md`.

## 🌟 Overview

The system transforms qualitative interview data into a quantitative leaderboard, mimicking the structure of official league standings. It allows users to track which coaches maintain professionalism and which are frequently critical of officiating.

## 🛠️ Core Functionalities

### 1. Calendar Sync
Finished La Liga matches are automatically fetched from [football-data.org](https://www.football-data.org/) and added to the calendar. Requires a (free) API key. Without a key, the sync falls back to ESPN's public scoreboard API (keyless, day-by-day scan of a bounded window: one week before the latest known game, at most 14 days back). Matches can also be added manually.

### 2. Data Collection
The system identifies pending matches from the calendar and searches for post-game comments from both the home and away coaches.
- **Discovery**: Publisher news sitemaps (Mundo Deportivo, Relevo, Estadio Deportivo — keyless, covers the last ~48h of articles) plus web search: SerpApi (with `SERPAPI_KEY`) or keyless Google News RSS (with opt-in DuckDuckGo / Bing HTML scrapers). Google News RSS queries are date-bounded to each game's 48h publication window (`after:`/`before:`), so games older than the window stay collectable.
- **Fetching**: Articles from trusted sources (LaLiga.com, AS, Marca, Sport, Mundo Deportivo, Relevo, COPE) are downloaded and cleaned; only articles published within 48h of the match are accepted. The crawler identifies itself honestly (`RespectRankBot/1.0`), respects each site's robots.txt (fetched once per domain per run), rate-limits requests, honors `Retry-After` on 429/503 with capped exponential backoff, and circuit-breaks a domain after repeated 403/429 responses.
- **Extraction**: Referee-related quotes are extracted verbatim by an LLM (or a keyword heuristic fallback) and validated against the source text.
- **Output**: A `Collection Report` detailing how many quotes were successfully retrieved, plus `data/pending_requests.json` tracking what failed and why (retried on the next run, up to 5 attempts).

### 3. Dual Grading Systems
To provide a comprehensive view, the system implements two distinct scoring methodologies:
- **Separate Mode (Absolute)**: Each coach is graded independently.
    - `3 pts`: Respectful/Empathetic.
    - `1 pt`: Neutral/Objective.
    - `0 pts`: Disrespectful/Aggressive.
- **Competitive Mode (Relative)**: Coaches are compared head-to-head for each match.
    - The more respectful coach wins `3 pts`.
    - If both are equally respectful/disrespectful, both receive `1 pt`.
    - The less respectful coach receives `0 pts`.

Grading is LLM-based when an LLM key is configured, with a keyword heuristic fallback otherwise (flagged as `graded_by: heuristic`).

### 4. Professional Standings
Displays a formatted leaderboard including:
- **Position (Pos)**: Rank based on total points.
- **Team**: The coach's team.
- **Total**: Cumulative points.
- **Games Played (GP)**: Total games processed for that team.
- **Home/Away**: Points earned specifically in home or away matches.

## 🚀 Getting Started

### Prerequisites
- Python 3.x
- External Dependencies: `requests`, `beautifulsoup4` (install via `pip install -r requirements.txt`)

### Setup
Clone the repository and run from the root:
```bash
pip install -r requirements.txt
python3 src/main.py
```
No `PYTHONPATH` configuration is needed.

### Configuration (environment variables)

| Variable | Required | Purpose |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | For calendar sync (optional) | [football-data.org](https://www.football-data.org/) key (free tier covers La Liga); without it, an ESPN keyless fallback is used |
| `LLM_API_KEY` | Recommended | OpenAI-compatible LLM key for quote extraction and grading |
| `LLM_BASE_URL` | With `LLM_API_KEY` | Your OpenAI-compatible endpoint; nothing is hardcoded |
| `LLM_MODEL` | With `LLM_API_KEY` | Model name served by your endpoint |
| `LLM_EXTRACT_MODEL` | No | Different model for quote extraction only (e.g. a cheaper one); falls back to `LLM_MODEL` |
| `SERPAPI_KEY` | No | SerpApi key; without it the system uses news-sitemap discovery plus keyless Google News RSS search |
| `ENABLE_HTML_SCRAPERS` | No | Set `1` to also use the DuckDuckGo/Bing HTML scrapers (off by default: scraping consumer search pages is legally gray) |
| `SINCE` | No | Default collection window for weekly runs: `YYYY-MM-DD`. CLI `--since` wins; without either, the window is the last run's date minus a 3-day overlap (`--full-history` overrides) |
| `MAX_REQUESTS_PER_RUN` | No | Hard cap on HTTP fetches per run across all sources (default `600`, `0` disables) |
| `MAX_LLM_CALLS_PER_RUN` | No | Hard cap on LLM calls per run (default `300`); when exhausted, extraction/grading degrade to the heuristic fallback |
| `LLM_BATCH_EXTRACTION` | No | Set `0` to disable batched quote extraction (one LLM call per document instead of one per coach) |
| `BATCH_DOC_CHARS` | No | Per-document character cap inside a batched extraction call (default `6000`). Lower than `MAX_DOC_CHARS` on purpose: batching multiplies prompt size by document count |
| `RATE_LIMIT_FETCH` | No | Seconds between article fetches (default `1.0`, `0` disables) |
| `RATE_LIMIT_SEARCH` | No | Seconds between keyless searches (default `2.0`, `0` disables) |
| `RATE_LIMIT_SITEMAP` | No | Seconds between sitemap fetches (default `1.0`, `0` disables) |
| `RATE_LIMIT_FETCH_DOMAIN` | No | Minimum seconds between requests to the *same domain* (default `3.0`, `0` disables) |
| `HTTP_CACHE_DIR` | No | On-disk HTTP cache directory (default `.cache/http`, gitignored) |
| `HTTP_CACHE_DISABLE` | No | Set `1` to bypass the on-disk HTTP cache |
| `BLOCKED_DOMAINS` | No | Publishers that persistently hard-block this bot (default `as.com,sport.es`); never contacted directly, read via the Internet Archive instead. Empty string disables |
| `WAYBACK_FALLBACK` | No | Set `0` to disable the Wayback Machine fallback for blocked publishers (fails hard instead) |
| `PRESUME_AFTER_DAYS` | No | Days after a game before a coach with no referee comment is presumed respectful (default 14) |
| `GOOGLE_NEWS_DECODE` | No | Set `0` to skip the Google News base64 URL decoder (the batchexecute endpoint it queries is undocumented) |

Everything degrades gracefully: without keys the system still runs using news-sitemap discovery, keyless search, and heuristic extraction/grading (lower quality, clearly flagged).

## 🔄 Operational Guide: Keeping the Leaderboard Updated

Run the full pipeline (sync → collect → grade → rank):
```bash
python3 src/main.py
```

Useful variants:
```bash
python3 src/main.py --display          # also print both standings tables
python3 src/main.py --no-sync          # skip football-data.org sync
python3 src/main.py --no-collect       # only re-grade and re-rank
python3 src/main.py --no-grade         # only sync and collect
python3 src/main.py --retry-pending    # retry requests that exhausted all attempts
python3 src/main.py --since 2026-09-25 # only process games from this date on
python3 src/main.py --full-history     # ignore the incremental window
```

**Incremental weekly runs**: by default each run only seeks comments for games since the last run (minus a 3-day overlap), so a weekly run costs minutes, not hours.

**Every game resolves.** A coach-game pair ends in one of three outcomes: referee quotes found (graded 0/1/3), the coach was quoted in the match coverage but never mentioned the referee (**confirmed clean**, 3 points — not dragging the referee is the respectful baseline), or nothing was found within `PRESUME_AFTER_DAYS` (default 14) days of the game (**presumed clean**, 3 points). Gathering itself has no deadline: full runs (`--full-history` or no `--since`) keep seeking old games — the Internet Archive fallback can still recover quotes for them — and weekly runs settle already-sought old games as presumed clean without re-seeking. Games never sought before are always left for a full run rather than presumed blindly.

Pending requests that fail 5 times are normally given up on; `--retry-pending` resets their attempt counters so the next collection run tries them again.

Every run writes `data/run_report.json` (run timestamp, window used, collection and grading stats, LLM usage) and appends the same report to `data/history/runs.jsonl`, so past runs are never lost when the current report is overwritten; the web UI shows the report as a "data last updated" banner.

**Blocked publishers, handled ethically**: some outlets (currently as.com and sport.es) answer this bot's honest user agent with 403/406 bot-block responses. The pipeline respects that: those domains are on `BLOCKED_DOMAINS` and are never contacted — not even for robots.txt. Their articles, when discovered via search or sitemaps, are instead read from the Internet Archive's public Wayback Machine playback (documented availability API + snapshot page), at the same rate-limited, budgeted, cached pace as every other fetch, with robots.txt honored on the archive origins and the original publisher URL kept for attribution. Set `WAYBACK_FALLBACK=0` to fail hard instead, or edit `BLOCKED_DOMAINS` to change the list. Discovery breadth comes from machine-friendly sources: news sitemaps (Mundo Deportivo, Relevo, Estadio Deportivo), Google News RSS, and unblocked outlets like Marca, COPE and RTVE via search.

**Weekly cadence**: a [GitHub Actions workflow](.github/workflows/weekly-reminder.yml) opens a `weekly-update` issue every Monday reminding you to run the pipeline locally (the LLM API key never leaves your machine, so the actual run cannot happen in CI). Close the issue once the updated `data/` is pushed.

**LLM cost control**: before extraction, each fetched document passes a cheap local pre-filter — documents whose text never mentions the coach or contains no referee keywords are skipped without an LLM call, typically cutting extraction from up to 6 calls per coach to 1–2.

To view the standings:
```bash
python3 src/display.py separate
python3 src/display.py competitive
```

Or open the web UI (serves the leaderboard with team badges, games played, a coach/team search filter, per-week quote filtering, light/dark mode, data-quality notices, "data last updated" banner and pending-collection status):
```bash
python3 -m http.server 8000   # then open http://localhost:8000
```

The UI is also deployed to **GitHub Pages** on every push to `main` ([workflow](.github/workflows/deploy.yml)). One-time setup: repo *Settings → Pages → Source: GitHub Actions*. Clicking a leaderboard row opens the coach drill-down: every collected quote with its game, score, grader, justification and source links. All data displayed in the UI is escaped; URLs are validated before use.

Team badges in `assets/teams/` are generated stylized initials (no club crests). Regenerate them after changing `data/teams.json`:
```bash
python3 scripts/generate_badges.py
```

To add matches manually, add entries to `data/games.json` with `game_id`, `date` (`YYYY-MM-DD`), `home_team`, `away_team`, `home_coach` and `away_coach`. Matches dated in the future are skipped until played; matches without collected comments are retried on each run (max 5 attempts, tracked in `data/pending_requests.json`).

### Coach changes mid-season

Each team in `data/teams.json` has a `coach` (current) and an optional `coach_history` of past tenures:

```json
{
  "team": "Alavés",
  "coach": "New Coach",
  "coach_history": [{"coach": "Old Coach", "until": "2026-09-20"}]
}
```

When a club changes coaches: set `coach` to the new hire and append the outgoing coach to `coach_history` with `until` set to his last day in charge. Calendar sync then assigns each new match the coach in charge on its date, and the departed coach keeps his accumulated points and team on the leaderboard (a new coach starts from zero).

## 🧪 Tests
```bash
python3 -m unittest discover -s tests -t . -v
```

## 📂 Project Structure
- `src/collection/`: Calendar sync, search, article fetching, quote extraction, validation, deduplication.
- `src/grading/`: LLM/heuristic scoring and ranking logic.
- `src/data/`: JSON database management.
- `src/utils/`: LLM client and football-data.org API handler.
- `src/display.py`: CLI visualization tool.
- `scripts/generate_badges.py`: Regenerates the web UI team badges.
- `scripts/fetch_team_logos.py`: Backfills official team crest URLs (ESPN CDN) into `teams.json`.
- `assets/teams/`: Generated SVG badges for the web UI.
- `data/`: JSON files (`games.json`, `teams.json`, `comments.json`, `pending_requests.json`, leaderboards).
- `tests/`: Unit tests.
- `docs/`: Design specifications and usage guides. See `docs/OPERATIONS.md` for the weekly runbook, env knobs, and recovery playbooks.
