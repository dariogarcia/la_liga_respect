import json
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
