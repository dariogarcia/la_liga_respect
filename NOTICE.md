# NOTICE

This file provides important information about the **Respect Rank** project
(`dariogarcia/la_liga_respect`), an automated system that ranks La Liga
coaches by the respect shown toward referees in post-match statements.

## Automated system

All data in this repository is collected and graded automatically:

- Quotes are discovered via news sitemaps, RSS feeds and web search, then
  fetched from publisher websites by a self-identifying crawler
  (`RespectRankBot/1.0`) that respects each site's `robots.txt`.
- Quote extraction and grading are performed by a language model (with a
  keyword-heuristic fallback, clearly flagged in the UI and data).
- No human reviews the quotes before publication on the leaderboard.

## Accuracy and misattribution

Quotes are extracted and attributed automatically and **may be wrong**:
misattributed to the wrong coach, taken out of context, or merged with
other statements from the same press appearance. Grading scores
(3 = respectful, 1 = neutral, 0 = disrespectful) are machine-generated
judgments and are inherently subjective. They do not represent the opinion
of the repository owner and have no official standing.

Each quote in the web UI links to its source articles so readers can verify
the attribution and context themselves.

## Copyright and quotes

Quotes remain the property of their respective publishers and are
reproduced here in short excerpts, linked to their sources, for
commentary and informational purposes. League, club and coach names are
used for identification only.

If you are a rights holder and want a quote removed:

1. Open an issue at
   https://github.com/dariogarcia/la_liga_respect/issues, or
2. Contact the repository owner directly via their GitHub profile.

Include the quote text (or the leaderboard row/coach) and the source URL.
Removal requests are handled by deleting the affected entries from
`data/comments.json` and regenerating the leaderboard.

## Data licensing

The source code is licensed under the MIT license (see `LICENSE`).
The compiled data files under `data/` (games, quotes, scores, rankings)
are provided for informational purposes; they incorporate copyrighted
press excerpts and are not licensed for commercial reuse.

## Crawling

The crawler identifies itself honestly, fetches each site's `robots.txt`
once per run and honors it, rate-limits all requests, and stops fetching
from a domain after repeated block responses. If you operate a site
indexed here and prefer to be excluded, the takedown process above
applies, or block `RespectRankBot` in your `robots.txt`.
