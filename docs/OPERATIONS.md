# Operations Runbook

How to keep Respect Rank running week after week: the ritual, the knobs,
and what to do when things break.

## The weekly ritual (Mondays, ~10 minutes)

La Liga plays weekends. Monday morning, after the matchday:

```bash
export PROVIDER_API_KEY=...          # your LLM key
python3 src/main.py                # sync calendar, collect, grade, report
git add data/ && git commit -m "data: matchday N" && git push
```

That is the whole ritual. Everything below is context, knobs, and recovery.

## What a run does

1. **Sync** — finished games from football-data.org (needs `FOOTBALL_DATA_API_KEY`)
   or the keyless ESPN fallback, into `data/games.json`.
2. **Collect** — for each unresolved coach-game pair: sitemap discovery +
   Google News RSS (date-bounded to the 48h after the match), fetch trusted
   sources, extract referee-related quotes (batched LLM calls), and grade them.
3. **Grade + rank** — every quote gets a score (3 respectful / 1 neutral /
   0 disrespectful); coaches with no referee comment resolve as 3
   (confirmed or presumed clean after `PRESUME_AFTER_DAYS`, default 14).
4. **Report** — `data/run_report.json` overwritten, `data/history/runs.jsonl`
   appended (never lost).

## Window semantics

- Weekly runs only examine games since the last run minus 3 days
  (`SINCE_OVERLAP_DAYS`), so nothing played between runs is missed.
- A coach-game already sought but unresolved, older than 14 days, resolves
  as **presumed clean** on the next weekly run — without re-seeking.
- Games never sought (e.g. added later) are picked up by the next
  **full run**: `python3 src/main.py --full-history`.
- Gathering has no deadline: full runs keep seeking old games via search
  engines + the Internet Archive (Wayback) fallback for blocked publishers.

## Budgets and limits (per run)

| Knob | Default | Meaning |
|------|---------|---------|
| `MAX_LLM_CALLS` | 300 | run aborts collection (grading finishes) past this |
| `MAX_REQUESTS_PER_RUN` | 600 | hard HTTP ceiling across all domains |
| `RATE_LIMIT_SEARCH` | 3.0s | between search-engine hits |
| `RATE_LIMIT_SITEMAP` | 1.0s | between sitemap fetches |
| `PRESUME_AFTER_DAYS` | 14 | respectful-silence presumption window |
| `BATCH_DOC_CHARS` | 6000 | per-doc truncation in batched extraction |
| `GOOGLE_NEWS_DECODE` | 1 | set `0` to skip the Google News URL decoder |
| `ENABLE_HTML_SCRAPERS` | off | set `1` for DuckDuckGo/Bing scrapers (gray) |
| `BLOCKED_DOMAINS` | `as.com,sport.es` | never contacted; read via Wayback |
| `WAYBACK_FALLBACK` | 1 | set `0` to fail hard on blocked domains |

Check the spend after every run: `data/run_report.json` → `llm_usage.calls`
(plus `by_purpose` breakdown) and `http_requests`.

## Recovery playbooks

### "Google News RSS returned HTTP 429"
Rate limiting — expected on keyless search. The circuit breaker disables it
for 15 minutes and the run continues with what it has. If a run finishes
with many `no_search_results` pendings, just re-run later:
`python3 src/main.py --retry-pending`.

### "no Wayback snapshot available for blocklisted as.com"
The Internet Archive simply has no copy of that article. Nothing is broken;
the coach-game resolves as presumed clean if nothing else is found. Do not
try to fetch blocked domains directly — that is the whole point of the
blocklist.

### Collection stopped early (LLM budget)
`LLMBudgetExceeded` ends collection but grading still runs; pending entries
keep their attempt counters. Next run with a fresh budget (or a raised
`MAX_LLM_CALLS`) resumes where it stopped.

### A run crashed / log looks stuck
Runs write `data/pending_requests.json` after every sought coach, so a
crash loses at most one coach's work. Restart with `--retry-pending` if the
crash exhausted attempts.

### Data looks wrong (misattributed quote, bad score)
1. Find the entry in `data/comments.json` (search the quote text).
2. Check its `sources` — open them; the quote must be visible there.
3. Fix or remove the entry, then re-rank without collecting:
   `python3 src/main.py --no-sync --no-collect --display`.
4. Commit `data/` with what you changed and why.

### Rankings look merged / a coach has another club's points
Coach-name collisions are guarded: points accumulate per (coach, team). If
a coach switched clubs, he legitimately has one row per club.

## Testing before touching code

```bash
python3 -m unittest discover -s tests -t .   # ~240 hermetic tests
```

Tests are hermetic: no network, no LLM key needed. CI runs the same
command on every push.

## Publishing

GitHub Pages serves `index.html` + `data/` (deploy job in `ci.yml`), and a
weekly issue reminds you to run the ritual (`weekly-reminder.yml`). Both
activate only after the repo is pushed and (once) Settings → Pages →
Source: GitHub Actions.
