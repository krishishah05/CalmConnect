import os
import tempfile
import unittest
from unittest.mock import patch


def _make_entry(user_id="alice", mood="positive", date="2024-03-01", text="Sample entry"):
    return {
        "user_id": user_id,
        "date": date,
        "text": text,
        "mood": mood,
        "polarity": 0.5,
        "emotions": "happy",
    }


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self._patch = patch.dict("os.environ", {"DB_PATH": self.db_path})
        self._patch.start()
        from app.storage import save_entry, get_user_entries
        self.save_entry = save_entry
        self.get_user_entries = get_user_entries

    def tearDown(self):
        self._patch.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_retrieve(self):
        self.save_entry(_make_entry())
        entries = self.get_user_entries("alice")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Sample entry")
        self.assertEqual(entries[0]["mood"], "positive")

    def test_user_isolation(self):
        self.save_entry(_make_entry("alice"))
        self.save_entry(_make_entry("bob"))
        self.assertEqual(len(self.get_user_entries("alice")), 1)
        self.assertEqual(len(self.get_user_entries("bob")), 1)

    def test_empty_user(self):
        self.assertEqual(self.get_user_entries("nobody"), [])

    def test_limit(self):
        for i in range(5):
            self.save_entry(_make_entry(text=f"Entry {i}"))
        entries = self.get_user_entries("alice", limit=3)
        self.assertEqual(len(entries), 3)

    def test_multiple_entries_ordered_newest_first(self):
        self.save_entry(_make_entry(date="2024-01-01", text="first"))
        self.save_entry(_make_entry(date="2024-03-01", text="latest"))
        entries = self.get_user_entries("alice")
        self.assertEqual(entries[0]["date"], "2024-03-01")

    def test_polarity_stored_correctly(self):
        entry = _make_entry()
        entry["polarity"] = -0.42
        entry["mood"] = "negative"
        self.save_entry(entry)
        result = self.get_user_entries("alice")[0]
        self.assertAlmostEqual(result["polarity"], -0.42, places=4)


if __name__ == "__main__":
    unittest.main()
