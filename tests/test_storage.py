import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import journal, storage
from tests.support import TempDataTestCase


def _make_entry(day="2024-03-01", text="Sample entry", tags=()):
    return {
        "entry_date": day,
        "created_at": f"{day}T12:00:00+00:00",
        "text": text,
        "sentiment": "positive",
        "polarity": 0.5,
        "emotions": ["happy", "calm"],
        "tags": list(tags),
    }


class TestStorage(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("alice")
        self.bob = self.make_user("bob")

    def test_new_data_dir_is_private(self):
        fresh = os.path.join(self.data_dir, "fresh")
        with patch.dict(os.environ, {"CALMCONNECT_DATA_DIR": fresh}):
            storage.data_dir()
        self.assertEqual(os.stat(fresh).st_mode & 0o777, 0o700)

    def test_db_path_override(self):
        other = os.path.join(self.data_dir, "nested", "other.db")
        with patch.dict(os.environ, {"DB_PATH": other}):
            self.assertEqual(str(storage.db_path()), other)
            self.assertTrue(os.path.isdir(os.path.dirname(other)))

    def test_save_and_retrieve_round_trip(self):
        entry_id = storage.insert_entry(self.alice, _make_entry(tags=["b", "a"]))
        entry = storage.get_entry(self.alice, entry_id)
        self.assertEqual(entry["text"], "Sample entry")
        self.assertEqual(entry["emotions"], ["happy", "calm"])
        self.assertEqual(entry["tags"], ["a", "b"])
        self.assertAlmostEqual(entry["polarity"], 0.5)

    def test_entries_persist_across_connections(self):
        storage.insert_entry(self.alice, _make_entry())
        conn = sqlite3.connect(storage.db_path())
        count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_user_isolation(self):
        storage.insert_entry(self.alice, _make_entry(text="alice's"))
        storage.insert_entry(self.bob, _make_entry(text="bob's"))
        self.assertEqual([e["text"] for e in storage.list_entries(self.alice)], ["alice's"])
        self.assertEqual([e["text"] for e in storage.list_entries(self.bob)], ["bob's"])

    def test_tags_loaded_for_every_entry_in_a_list(self):
        for i in range(3):
            storage.insert_entry(self.alice, _make_entry(text=f"e{i}", tags=[f"t{i}"]))
        storage.insert_entry(self.alice, _make_entry(text="untagged"))
        tags = {e["text"]: e["tags"] for e in storage.list_entries(self.alice)}
        self.assertEqual(tags, {"e0": ["t0"], "e1": ["t1"], "e2": ["t2"], "untagged": []})

    def test_deleting_an_entry_removes_its_tags(self):
        entry_id = storage.insert_entry(self.alice, _make_entry(tags=["trip"]))
        storage.delete_entry(self.alice, entry_id)
        self.assertEqual(storage.list_tags(self.alice), [])

    def test_update_is_scoped_to_the_owner(self):
        entry_id = storage.insert_entry(self.alice, _make_entry(tags=["mine"]))
        edited = {**storage.get_entry(self.alice, entry_id), "text": "changed",
                  "tags": [], "updated_at": "2024-03-02T00:00:00+00:00"}
        self.assertFalse(storage.update_entry(self.bob, edited))
        self.assertEqual(storage.get_entry(self.alice, entry_id)["tags"], ["mine"])
        self.assertTrue(storage.update_entry(self.alice, edited))
        self.assertEqual(storage.get_entry(self.alice, entry_id)["tags"], [])

    def test_failed_write_is_rolled_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            # The second tag is a duplicate of the first, which breaks the
            # primary key after the entry row was already inserted.
            storage.insert_entry(self.alice, _make_entry(tags=["same", "same"]))
        self.assertEqual(storage.list_entries(self.alice), [])


class TestLegacyMigration(unittest.TestCase):
    """Databases from the first version had a free-text user_id and no accounts.
    The schema and rows below match what the original code wrote, including an
    empty entry, which its CLI allowed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        env = patch.dict(os.environ, {"CALMCONNECT_DATA_DIR": self.tmp})
        env.start()
        os.environ.pop("DB_PATH", None)
        self.addCleanup(env.stop)

        conn = sqlite3.connect(os.path.join(self.tmp, "journal.db"))
        conn.execute("""
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                date TEXT NOT NULL, text TEXT NOT NULL, mood TEXT NOT NULL,
                polarity REAL NOT NULL, emotions TEXT DEFAULT ''
            )""")
        conn.executemany(
            "INSERT INTO entries (user_id, date, text, mood, polarity, emotions) VALUES (?, ?, ?, ?, ?, ?)",
            [("alice", "2025-07-01", "I am not happy", "negative", -0.4, "happy"),
             ("alice", "2025-07-02", "Good day", "positive", 0.7, ""),
             ("alice", "2025-07-03", "", "neutral", 0.0, ""),
             ("bob", "2025-07-01", "bob's entry", "neutral", 0.0, "")],
        )
        conn.commit()
        conn.close()

    def test_old_rows_are_kept_and_can_be_imported(self):
        from app import auth
        user = auth.register("alice_new", "long enough password")
        self.assertEqual(journal.import_legacy(user, "alice"), 3)

        entries = journal.find_entries(user, oldest_first=True)
        self.assertEqual([(e["entry_date"], e["text"]) for e in entries],
                         [("2025-07-01", "I am not happy"), ("2025-07-02", "Good day"), ("2025-07-03", "")])
        # Re-analysed with the current rules, so the old false "happy" is gone.
        self.assertEqual(entries[0]["emotions"], [])

        # Importing twice doesn't duplicate, and other names are untouched.
        self.assertEqual(journal.import_legacy(user, "alice"), 0)
        self.assertEqual(len(storage.get_legacy_entries("bob")), 1)

    def test_no_legacy_table(self):
        os.remove(os.path.join(self.tmp, "journal.db"))
        self.assertEqual(storage.get_legacy_entries("alice"), [])


if __name__ == "__main__":
    unittest.main()
