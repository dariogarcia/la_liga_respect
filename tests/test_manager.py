import json
import os
import tempfile
import unittest
from unittest import mock

from src.data import manager
from src.data.manager import save_json


class TestSaveJson(unittest.TestCase):
    def test_atomic_write_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "data.json")
            save_json(path, {"a": 1})
            save_json(path, {"b": 2})
            with open(path) as f:
                self.assertEqual(json.load(f), {"b": 2})
            # no leftover .tmp file from the atomic replace
            self.assertEqual(os.listdir(os.path.dirname(path)), ["data.json"])


class TestRunHistory(unittest.TestCase):
    """U2: run reports are appended, never lost."""

    def _patched(self, tmp):
        history_dir = os.path.join(tmp, "data", "history")
        return (
            mock.patch.object(manager, "HISTORY_DIR", history_dir),
            mock.patch.object(manager, "RUN_HISTORY_FILE",
                              os.path.join(history_dir, "runs.jsonl")),
        )

    def test_save_run_report_appends_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_patch, file_patch = self._patched(tmp)
            with dir_patch, file_patch:
                manager.save_run_report({"last_run": "2026-10-01", "n": 1})
                manager.save_run_report({"last_run": "2026-10-02", "n": 2})
                history = manager.get_run_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["last_run"], "2026-10-01")
            self.assertEqual(history[1]["last_run"], "2026-10-02")

    def test_get_run_history_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_patch, file_patch = self._patched(tmp)
            with dir_patch, file_patch:
                self.assertEqual(manager.get_run_history(), [])

    def test_corrupt_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            dir_patch, file_patch = self._patched(tmp)
            with dir_patch, file_patch:
                os.makedirs(manager.HISTORY_DIR)
                with open(manager.RUN_HISTORY_FILE, "w") as f:
                    f.write('{"last_run": "2026-10-01"}\n')
                    f.write("not json\n")
                    f.write('{"last_run": "2026-10-02"}\n')
                history = manager.get_run_history()
            self.assertEqual([r["last_run"] for r in history],
                             ["2026-10-01", "2026-10-02"])


if __name__ == "__main__":
    unittest.main()
