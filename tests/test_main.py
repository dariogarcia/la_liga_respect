"""T1: integration tests for src/main.py.

Patches the layer boundaries (calendar sync, collection, grading,
leaderboard IO) and drives main() through the CLI flag matrix,
the --since resolution order, and the run-report contract.
"""

import io
import os
import sys
import unittest
from datetime import date, timedelta
from unittest import mock

from src import main as main_module
from src.main import SINCE_OVERLAP_DAYS, _parse_date


class MainHarness(unittest.TestCase):
    """Runs main() with all boundaries patched; returns the mocks."""

    def _run(self, argv, last_report=None, env_overrides=None):
        env = dict(os.environ)
        for var in ("SINCE", "SERPAPI_KEY", "FOOTBALL_DATA_API_KEY", "FOOTBALL_API_KEY"):
            env.pop(var, None)
        env.update(env_overrides or {})

        with mock.patch.object(main_module, "sync_finished_games") as sync, \
             mock.patch.object(main_module, "collect_matchday_comments") as collect, \
             mock.patch.object(main_module, "update_leaderboard") as grade, \
             mock.patch.object(main_module, "get_leaderboard",
                               return_value=[{"coach": "X", "team": "T", "points": 3}]), \
             mock.patch.object(main_module, "get_run_report",
                               return_value=last_report or {}), \
             mock.patch.object(main_module, "save_run_report") as save, \
             mock.patch.object(main_module, "show_leaderboard") as show, \
             mock.patch.object(sys, "argv", ["main.py"] + argv), \
             mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("sys.stdout", new=io.StringIO()):
            main_module.main()

        return {
            "sync": sync, "collect": collect, "grade": grade,
            "save": save, "show": show,
        }

    def _report(self, mocks):
        mocks["save"].assert_called_once()
        return mocks["save"].call_args[0][0]


class TestFlagMatrix(MainHarness):
    def test_default_run_calls_everything(self):
        mocks = self._run([], env_overrides={"SERPAPI_KEY": "k"})
        mocks["sync"].assert_called_once()
        mocks["collect"].assert_called_once()
        mocks["grade"].assert_called_once()
        mocks["show"].assert_not_called()

        kwargs = mocks["collect"].call_args.kwargs
        self.assertEqual(kwargs["api_key"], "k")
        self.assertFalse(kwargs["retry_pending"])
        self.assertIsNone(kwargs["since"])

        report = self._report(mocks)
        self.assertEqual(report["last_run"], date.today().isoformat())
        self.assertIsNone(report["since_used"])
        self.assertEqual(report["collection"], mocks["collect"].return_value)
        self.assertEqual(report["grading"], mocks["grade"].return_value)
        self.assertEqual(report["sync"], mocks["sync"].return_value)

    def test_no_flags_skip_their_stages(self):
        mocks = self._run(["--no-sync", "--no-collect", "--no-grade", "--display"],
                          last_report={"last_run": "2026-09-01"})
        mocks["sync"].assert_not_called()
        mocks["collect"].assert_not_called()
        mocks["grade"].assert_not_called()
        mocks["show"].assert_has_calls(
            [mock.call("separate"), mock.call("competitive")], any_order=True
        )
        self.assertEqual(mocks["show"].call_count, 2)

        report = self._report(mocks)
        # Display-only pass must not advance (or shrink) the window.
        self.assertEqual(report["last_run"], "2026-09-01")
        self.assertIsNone(report["sync"])
        self.assertIsNone(report["collection"])
        self.assertIsNone(report["grading"])

    def test_retry_pending_forwarded(self):
        mocks = self._run(["--retry-pending"])
        self.assertTrue(mocks["collect"].call_args.kwargs["retry_pending"])

    def test_report_shape(self):
        mocks = self._run(["--no-sync", "--no-collect", "--no-grade"])
        report = self._report(mocks)
        for key in ("generated_at", "last_run", "since_used", "sync",
                    "collection", "grading", "llm_usage", "http_requests"):
            self.assertIn(key, report)
        self.assertIn("calls", report["llm_usage"])
        self.assertIsInstance(report["http_requests"], int)


class TestSinceResolution(MainHarness):
    def test_since_flag_forwarded(self):
        mocks = self._run(["--since", "2026-09-15"])
        self.assertEqual(mocks["collect"].call_args.kwargs["since"],
                         date(2026, 9, 15))
        self.assertEqual(self._report(mocks)["since_used"], "2026-09-15")

    def test_last_run_minus_overlap(self):
        last_run = date(2026, 9, 20)
        mocks = self._run([], last_report={"last_run": last_run.isoformat()})
        expected = last_run - timedelta(days=SINCE_OVERLAP_DAYS)
        self.assertEqual(mocks["collect"].call_args.kwargs["since"], expected)
        self.assertEqual(self._report(mocks)["since_used"], expected.isoformat())

    def test_full_history_overrides_last_run(self):
        mocks = self._run(["--full-history"],
                          last_report={"last_run": "2026-09-20"})
        self.assertIsNone(mocks["collect"].call_args.kwargs["since"])
        self.assertIsNone(self._report(mocks)["since_used"])

    def test_env_since_used_when_no_cli_flag(self):
        mocks = self._run([], env_overrides={"SINCE": "2026-09-01"})
        self.assertEqual(mocks["collect"].call_args.kwargs["since"],
                         date(2026, 9, 1))

    def test_cli_since_beats_env(self):
        mocks = self._run(["--since", "2026-09-10"],
                          env_overrides={"SINCE": "2026-09-01"})
        self.assertEqual(mocks["collect"].call_args.kwargs["since"],
                         date(2026, 9, 10))

    def test_invalid_env_since_ignored(self):
        mocks = self._run([], env_overrides={"SINCE": "not-a-date"})
        self.assertIsNone(mocks["collect"].call_args.kwargs["since"])

    def test_invalid_last_run_means_full_run(self):
        mocks = self._run([], last_report={"last_run": "garbage"})
        self.assertIsNone(mocks["collect"].call_args.kwargs["since"])


class TestParseDate(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_parse_date("2026-10-02"), date(2026, 10, 2))

    def test_invalid_raises_argument_error(self):
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_date("02/10/2026")


if __name__ == "__main__":
    unittest.main()
