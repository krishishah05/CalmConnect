import unittest
from app.journal import create_entry


class TestCreateEntry(unittest.TestCase):
    def test_required_fields(self):
        entry = create_entry("Feeling good today", "alice")
        self.assertEqual(entry["user_id"], "alice")
        self.assertIn("date", entry)
        self.assertIn("text", entry)

    def test_text_stripped(self):
        entry = create_entry("  some text  ", "alice")
        self.assertEqual(entry["text"], "some text")

    def test_date_is_iso_format(self):
        entry = create_entry("hello", "alice")
        parts = entry["date"].split("-")
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[0]), 4)  # year
        self.assertEqual(len(parts[1]), 2)  # month
        self.assertEqual(len(parts[2]), 2)  # day

    def test_different_users(self):
        e1 = create_entry("text", "alice")
        e2 = create_entry("text", "bob")
        self.assertEqual(e1["user_id"], "alice")
        self.assertEqual(e2["user_id"], "bob")

    def test_empty_text_stripped(self):
        entry = create_entry("   ", "alice")
        self.assertEqual(entry["text"], "")


if __name__ == "__main__":
    unittest.main()
