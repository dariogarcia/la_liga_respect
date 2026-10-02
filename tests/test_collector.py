import unittest
from datetime import date, datetime, timedelta
from unittest import mock

from src.collection.collector import (
    collect_comments_for_coach,
    collect_matchday_comments,
    MAX_ATTEMPTS,
    REASON_NO_QUOTES,
    REASON_NO_RESULTS,
    REASON_NO_TRUSTED,
    REASON_WINDOW_FILTERED,
)
from src.collection.models import SearchResult, SourceDocument

GAME = {
    "game_id": "1",
    "date": "2026-08-15",
    "home_team": "Alavés",
    "away_team": "Getafe",
    "home_coach": "Coach A",
    "away_coach": "Coach B",
}


class FakeSearchProvider:
    def __init__(self, results):
        self.results = results

    def search(self, query, max_results=10, date_range=None):
        return self.results


class FakeFetcher:
    def __init__(self, published_at=None, text=None):
        self.published_at = published_at
        self.text = text

    def fetch(self, url):
        return SourceDocument(
            url=url,
            title="t",
            text=self.text or (
                "Coach A compareció tras el partido. "
                "«El árbitro lo hizo bien, fue un trabajo complicado»"
            ),
            published_at=self.published_at,
            source_name="as.com",
        )


class FakeExtractor:
    def extract(self, coach, game_id, document):
        return [{"text": "El árbitro lo hizo bien, fue un trabajo complicado",
                 "referee_related": True}]


class TestCollectCommentsForCoach(unittest.TestCase):
    def _run(self, provider, fetcher, extractor=None, game=None):
        return collect_comments_for_coach(
            game or GAME, "Coach A", provider, fetcher, extractor or FakeExtractor()
        )

    def test_happy_path(self):
        provider = FakeSearchProvider([SearchResult("https://www.as.com/a", "t", "s")])
        fetcher = FakeFetcher(published_at=datetime(2026, 8, 16, 8, 0))
        merged, reason = self._run(provider, fetcher)
        self.assertIsNotNone(merged)
        self.assertIn("árbitro", merged["text"])
        self.assertEqual(merged["sources"], ["https://www.as.com/a"])
        self.assertIsNone(reason)

    def test_no_search_results(self):
        merged, reason = self._run(FakeSearchProvider([]), FakeFetcher())
        self.assertIsNone(merged)
        self.assertEqual(reason, REASON_NO_RESULTS)

    def test_no_trusted_sources(self):
        provider = FakeSearchProvider([SearchResult("https://blog.example.com/a", "t", "s")])
        merged, reason = self._run(provider, FakeFetcher())
        self.assertIsNone(merged)
        self.assertEqual(reason, REASON_NO_TRUSTED)

    def test_publication_window_filters_old_articles(self):
        provider = FakeSearchProvider([SearchResult("https://www.as.com/a", "t", "s")])
        fetcher = FakeFetcher(published_at=datetime(2026, 8, 20, 8, 0))
        merged, reason = self._run(provider, fetcher)
        self.assertIsNone(merged)
        self.assertEqual(reason, REASON_WINDOW_FILTERED)

    def test_missing_date_is_kept_for_recent_game(self):
        recent_game = dict(GAME, date=(date.today() - timedelta(days=1)).isoformat())
        provider = FakeSearchProvider([SearchResult("https://www.as.com/a", "t", "s")])
        fetcher = FakeFetcher(published_at=None)
        merged, reason = self._run(provider, fetcher, game=recent_game)
        self.assertIsNotNone(merged)

    def test_missing_date_is_rejected_for_old_game(self):
        # An undated article discovered now cannot be from a match played
        # weeks ago; accepting it would misattribute the quote.
        provider = FakeSearchProvider([SearchResult("https://www.as.com/a", "t", "s")])
        fetcher = FakeFetcher(published_at=None)
        merged, reason = self._run(provider, fetcher)
        self.assertIsNone(merged)
        self.assertEqual(reason, REASON_WINDOW_FILTERED)

    def test_dedupes_urls_across_queries(self):
        provider = FakeSearchProvider([SearchResult("https://www.as.com/a", "t", "s")] * 4)
        fetcher = FakeFetcher(published_at=datetime(2026, 8, 16, 8, 0))
        merged, _ = self._run(provider, fetcher)
        self.assertEqual(merged["sources"], ["https://www.as.com/a"])

    def test_rss_pubdate_fills_in_for_undated_article(self):
        # An article without a published date is still accepted for an
        # old game when the discovery source (Google News RSS pubDate)
        # places it inside the game's publication window.
        provider = FakeSearchProvider([
            SearchResult("https://www.as.com/a", "t", "s", published=datetime(2026, 8, 16, 7, 0))
        ])
        fetcher = FakeFetcher(published_at=None)
        merged, reason = self._run(provider, fetcher)
        self.assertIsNotNone(merged)
        self.assertEqual(merged["published_at"], datetime(2026, 8, 16, 7, 0))

    def test_prefilter_skips_document_without_coach_mention(self):
        # B1: a document that never mentions the coach cannot yield his
        # quotes, so the (potentially LLM-backed) extractor is never
        # called for it.
        calls = []

        class RecordingExtractor:
            def extract(self, coach, game_id, document):
                calls.append(document.url)
                return []

        provider = FakeSearchProvider([
            SearchResult("https://www.as.com/no-coach", "t", "s"),
            SearchResult("https://www.as.com/with-coach", "t", "s"),
        ])

        class SelectiveFetcher:
            def fetch(self, url):
                text = (
                    "El técnico del rival analizó el papeleo del árbitro."
                    if "no-coach" in url else
                    "Coach A habló del árbitro tras el partido."
                )
                return SourceDocument(
                    url=url, title="t", text=text,
                    published_at=datetime(2026, 8, 16, 8, 0), source_name="as.com",
                )

        merged, reason = self._run(provider, SelectiveFetcher(), RecordingExtractor())
        self.assertEqual(calls, ["https://www.as.com/with-coach"])
        self.assertIsNone(merged)
        self.assertEqual(reason, REASON_NO_QUOTES)


class TestQuerySelection(unittest.TestCase):
    def _record(self, game):
        seen = []

        class RecordingProvider:
            def search(self, query, max_results=10, date_range=None):
                seen.append((query, date_range))
                return []

        collect_comments_for_coach(
            game, "Coach A", RecordingProvider(), FakeFetcher(), FakeExtractor()
        )
        return seen

    def test_old_game_uses_full_queries_and_date_bounds(self):
        # GAME date (2026-08-15) is far in the past, but old games are
        # still collectable: the full query set is sent, each one
        # bounded to the game's own publication window.
        seen = self._record(GAME)
        self.assertTrue(seen)
        joined = " ".join(q for q, _ in seen)
        self.assertIn("referee", joined)
        self.assertTrue(any("site:" not in q for q, _ in seen))
        for _, date_range in seen:
            self.assertEqual(date_range[0], date(2026, 8, 15))
            self.assertEqual(date_range[1], date(2026, 8, 18))

    def test_recent_game_gets_window_starting_at_match_date(self):
        recent_game = dict(GAME, date=(date.today() - timedelta(days=1)).isoformat())
        seen = self._record(recent_game)
        expected_start = date.today() - timedelta(days=1)
        for _, date_range in seen:
            self.assertEqual(date_range[0], expected_start)


class TestPendingRetrySemantics(unittest.TestCase):
    def _run(self, game):
        saved = {}
        with mock.patch("src.collection.collector.get_games", return_value=[game]), \
             mock.patch("src.collection.collector.get_comments", return_value=[]), \
             mock.patch("src.collection.collector.get_pending_requests", return_value=[]), \
             mock.patch("src.collection.collector.save_comments", side_effect=lambda c: saved.update({"comments": c})), \
             mock.patch("src.collection.collector.save_pending_requests", side_effect=lambda p: saved.update({"pending": p})), \
             mock.patch("src.collection.collector.fetch_sitemap_entries", return_value=[]), \
             mock.patch("src.collection.collector.ArticleFetcher"), \
             mock.patch("src.collection.collector.get_extractor"):
            collect_matchday_comments(search_provider=FakeSearchProvider([]))
        return saved

    def test_old_game_failure_stays_retryable(self):
        # 2026-08-15 is older than the publication window, but the
        # failure is recorded like any other: attempts=1, retried later.
        saved = self._run(GAME)
        self.assertEqual(saved["comments"], [])
        self.assertEqual(len(saved["pending"]), 2)
        for entry in saved["pending"]:
            self.assertEqual(entry["reason"], REASON_NO_RESULTS)
            self.assertEqual(entry["attempts"], 1)

    def test_recent_failure_stays_retryable(self):
        recent_game = dict(GAME, date=(date.today() - timedelta(days=1)).isoformat())
        saved = self._run(recent_game)
        entry = saved["pending"][0]
        self.assertEqual(entry["reason"], REASON_NO_RESULTS)
        self.assertEqual(entry["attempts"], 1)


class TestIncrementalPersistence(unittest.TestCase):
    def _run(self, games):
        calls = {"comments": 0, "pending": 0}

        def count(key):
            return lambda _: calls.__setitem__(key, calls[key] + 1)

        with mock.patch("src.collection.collector.get_games", return_value=games), \
             mock.patch("src.collection.collector.get_comments", return_value=[]), \
             mock.patch("src.collection.collector.get_pending_requests", return_value=[]), \
             mock.patch("src.collection.collector.save_comments", side_effect=count("comments")), \
             mock.patch("src.collection.collector.save_pending_requests", side_effect=count("pending")), \
             mock.patch("src.collection.collector.fetch_sitemap_entries", return_value=[]), \
             mock.patch("src.collection.collector.ArticleFetcher"), \
             mock.patch("src.collection.collector.get_extractor"):
            collect_matchday_comments(search_provider=FakeSearchProvider([]))
        return calls

    def test_saves_after_each_sought_target(self):
        # Two coach targets in one game -> one save per target during the
        # loop plus the final save, so an interruption mid-run keeps the
        # results already collected.
        calls = self._run([GAME])
        self.assertGreaterEqual(calls["comments"], 3)
        self.assertGreaterEqual(calls["pending"], 3)

    def test_no_saves_when_nothing_sought(self):
        # Future games are skipped entirely: nothing to persist.
        future_game = dict(GAME, date=(date.today() + timedelta(days=1)).isoformat())
        calls = self._run([future_game])
        self.assertEqual(calls["comments"], 1)  # final save only
        self.assertEqual(calls["pending"], 1)


class TestRetryPending(unittest.TestCase):
    PENDING = [{
        "game_id": "1",
        "coach": "Coach A",
        "date": (date.today() - timedelta(days=3)).isoformat(),
        "attempts": MAX_ATTEMPTS,
        "last_attempt": "2026-08-16T00:00:00",
        "reason": "no_search_results",
    }]

    # A recent game keeps the classic retry semantics (attempts reset,
    # one failed attempt, retried again next run).
    GAME_FRESH = dict(GAME, date=(date.today() - timedelta(days=1)).isoformat())

    def _run(self, retry_pending, pending):
        saved = {}
        with mock.patch("src.collection.collector.get_games", return_value=[self.GAME_FRESH]), \
             mock.patch("src.collection.collector.get_comments", return_value=[]), \
             mock.patch("src.collection.collector.get_pending_requests", return_value=pending), \
             mock.patch("src.collection.collector.save_comments", side_effect=lambda c: saved.update({"comments": c})), \
             mock.patch("src.collection.collector.save_pending_requests", side_effect=lambda p: saved.update({"pending": p})), \
             mock.patch("src.collection.collector.fetch_sitemap_entries", return_value=[]), \
             mock.patch("src.collection.collector.ArticleFetcher"), \
             mock.patch("src.collection.collector.get_extractor"):
            collect_matchday_comments(
                search_provider=FakeSearchProvider([]),
                retry_pending=retry_pending,
            )
        return saved

    def test_retry_pending_resets_exhausted_attempts(self):
        saved = self._run(retry_pending=True, pending=[dict(self.PENDING[0])])
        entry = saved["pending"][0]
        self.assertEqual(entry["attempts"], 1)  # reset to 0, then one failed attempt

    def test_without_retry_exhausted_entries_stay_skipped(self):
        saved = self._run(retry_pending=False, pending=[dict(self.PENDING[0])])
        entry = saved["pending"][0]
        self.assertEqual(entry["attempts"], MAX_ATTEMPTS)
        self.assertEqual(saved["comments"], [])


if __name__ == "__main__":
    unittest.main()
