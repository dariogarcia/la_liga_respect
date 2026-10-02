# Respect Rank Usage Guide

This guide describes the functionalities of the Respect Rank system and how to use them.

## Quick Start
To run the complete pipeline (Sync → Collect → Grade → Rank), execute the main script from the repo root:

```bash
python3 src/main.py
```

To display the standings:
```bash
python3 src/display.py [separate|competitive]
```

## Configuration

All configuration is done via environment variables:

| Variable | Purpose | Fallback if missing |
|---|---|---|
| `FOOTBALL_DATA_API_KEY` | Sync finished matches from football-data.org | Keyless ESPN scoreboard fallback used instead |
| `SERPAPI_KEY` | SerpApi web search | News-sitemap discovery plus keyless Google News RSS / DuckDuckGo / Bing search (lower quality) |
| `LLM_API_KEY` | LLM quote extraction + grading via an OpenAI-compatible endpoint | Keyword heuristics (flagged `graded_by: heuristic`) |
| `LLM_BASE_URL` | Your OpenAI-compatible LLM endpoint | — |
| `LLM_MODEL` | Model name served by your endpoint | — |
| `RATE_LIMIT_FETCH` | Seconds between article fetches (default `1.0`, `0` disables) | — |
| `RATE_LIMIT_SEARCH` | Seconds between keyless searches (default `2.0`, `0` disables) | — |
| `RATE_LIMIT_SITEMAP` | Seconds between sitemap fetches (default `1.0`, `0` disables) | — |

All three LLM variables (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`) must be set for LLM mode; the endpoint and model are configuration, never hardcoded.

Outbound HTTP (article fetches, keyless searches, sitemap downloads) is rate-limited to be polite to publishers and avoid DuckDuckGo throttling.

## Functional Components

### 1. Calendar Sync (`src.collection.calendar`)
Fetches **finished** La Liga matches (from football-data.org when a key is set, otherwise from ESPN's public scoreboard API) and adds them to `data/games.json`, resolving each team's coach from `data/teams.json`. Existing games (matched by id or home/away/date) are never duplicated. Coaches are resolved as of each match date via the teams' `coach_history`, so mid-season changes are handled correctly.

To record a coach change: set the team's `coach` to the new hire and append the outgoing coach to `coach_history` with `until` set to his last day in charge (e.g. `{"coach": "Old Coach", "until": "2026-09-20"}`). Departed coaches keep their accumulated points and team on the leaderboard; new coaches start from zero.

### 2. Data Collection (`src.collection.collector`)
Gathers post-game coach interviews and stores them in `data/comments.json`.

- **Function:** `collect_matchday_comments(api_key=...)`
- **Mechanism:** For every past game without a stored comment, the collector discovers candidate articles two ways: (1) publisher news sitemaps from trusted outlets (Sport, Mundo Deportivo, Relevo), which list the last ~48h of articles and are matched against coach names; (2) web search (SerpApi, or the keyless chain Google News RSS → DuckDuckGo → Bing, including `site:`-restricted queries). Google News RSS queries are date-bounded to the game's publication window with the `after:`/`before:` operators, so games older than the window remain searchable within their own 48h; its redirect links are resolved to publisher URLs via Google's batchexecute endpoint. It filters to trusted sources, fetches articles, enforces a 48h publication window relative to each match (falling back to the RSS `pubDate` for undated articles), extracts referee-related verbatim quotes (LLM or heuristic), validates them verbatim against the article text, deduplicates and merges them into one quote per coach and game.
- **Output**: A "Collection Report" plus `data/pending_requests.json`, which records every failed coach/game with the reason (`no_search_results`, `no_trusted_sources`, `fetch_failed`, `publication_window_filtered`, `no_quotes_extracted`) and an attempt counter. Pending entries are retried on the next run and abandoned after 5 attempts. Run with `--retry-pending` (`python3 src/main.py --retry-pending`) to reset exhausted attempt counters and retry them. The keyless search chain includes circuit breakers: after repeated failures (throttling, timeouts) DuckDuckGo or Google News RSS is skipped for 15 minutes and queries go to the next engine.

### 3. Grading & Ranking (`src.grading.grader`)
Analyzes quotes and updates two types of leaderboards.

- **Function:** `update_leaderboard()`
- **Grading Modes**:
    - **Separate**: Absolute grading (0, 1, 3) based on quote content.
    - **Competitive**: Relative grading (winner gets 3, draw gets 1).
- **Mechanism**: Quotes are merged per (game, coach); ungraded quotes are scored by the LLM (or the keyword heuristic fallback) and the score is persisted with a `graded_by` marker.
- **Output**: A "Grading Report" showing quotes processed, newly graded, and incomplete games (e.g. only one coach has a quote).

### 4. Visualization (`src.display`)
Displays a formatted table of the standings.

- **Script:** `src/display.py`
- **Columns**: Position, Team, Total Points, Games Played (GP), Home Points, Away Points.

### 5. Data Management (`src.data.manager`)
Utility layer for JSON storage (absolute paths, safe from any working directory).

- **Files**: `games.json`, `teams.json`, `comments.json`, `pending_requests.json`, `leaderboard.json`, `leaderboard_competitive.json`.

## Grading Criteria
- **3 Points**: Respectful/Empathetic towards referees.
- **1 Point**: Neutral/Objective disagreement.
- **0 Points**: Disrespectful/Aggressive/Accusatory.

## Tests
```bash
python3 -m unittest discover -s tests -t . -v
```
