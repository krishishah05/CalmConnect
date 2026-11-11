import io
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import demo
from app import auth, journal
from app.stats import collection_summary, weekly_summary
from tests.support import TempDataTestCase


class TestDemoEntries(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.password = demo.load_demo()
        self.user = auth.check_login("demo", self.password)["id"]

    def places(self, entries):
        return [e["place"] for e in entries]

    def test_all_samples_saved_with_normal_analysis(self):
        entries = journal.find_entries(self.user, limit=None, oldest_first=True)
        self.assertEqual(len(entries), len(demo.SAMPLE_ENTRIES))
        self.assertEqual([e["entry_date"] for e in entries],
                         [s["date"] for s in demo.SAMPLE_ENTRIES])
        for entry in entries:
            self.assertIn(entry["sentiment"], ("positive", "neutral", "negative"))
            self.assertIsNone(entry["title"])

    def test_tags_become_collections(self):
        tags = {t["tag"]: t["entries"] for t in journal.list_collections(self.user)}
        self.assertEqual(tags["travel"], 6)
        self.assertEqual(tags["italy"], 2)
        self.assertEqual(tags["study-abroad"], 1)
        self.assertEqual(tags["amalfi-coast"], 1)

    def test_find_a_trip_by_tag_search_and_date(self):
        italy = journal.find_entries(self.user, tag="Italy", oldest_first=True)
        self.assertEqual(self.places(italy), ["Rome, Italy", "Amalfi Coast, Italy"])

        # Searching matches places and text, including accented words.
        self.assertEqual(self.places(journal.find_entries(self.user, search="italy")),
                         ["Amalfi Coast, Italy", "Rome, Italy"])
        self.assertEqual(self.places(journal.find_entries(self.user, search="park güell")),
                         ["Barcelona, Spain"])
        self.assertEqual(self.places(journal.find_entries(self.user, tag="travel", search="halloween")),
                         ["Dublin, Ireland"])

        october = journal.find_entries(self.user, date_from="2026-10-01", date_to="2026-10-31")
        self.assertEqual(len(october), 4)

    def test_semester_reads_in_order(self):
        summary = collection_summary(self.user, "travel")
        self.assertEqual((summary["first_date"], summary["last_date"]), ("2026-08-01", "2026-11-06"))
        self.assertEqual(self.places(summary["entries"]),
                         ["Iceland", "Barcelona, Spain", "Rome, Italy", "Amalfi Coast, Italy",
                          "Dublin, Ireland", "Marrakech and the Sahara, Morocco"])

    def test_weekly_stats_and_looking_back(self):
        summary = weekly_summary(self.user, today=date(2026, 11, 11))
        self.assertEqual(summary["total_entries"], 1)  # Morocco, November 6
        older = journal.revisit_entry(self.user, today=date(2026, 11, 11))
        self.assertNotEqual(older["entry_date"], "2026-11-06")


class TestDemoScript(TempDataTestCase):
    """main() must only ever write to its own folder."""

    def setUp(self):
        super().setUp()
        # A "real" journal in the normal data directory.
        self.real_user = self.make_user("krishi")
        self.real_entry = journal.create_entry(self.real_user, "My own entry", tags="prague")
        self.real_db = Path(self.data_dir, "journal.db").read_bytes()

        parent = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        self.demo_dir = Path(parent) / "demo-data"
        dir_patch = patch.object(demo, "DEMO_DIR", self.demo_dir)
        dir_patch.start()
        self.addCleanup(dir_patch.stop)

    def run_demo(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = demo.main(list(argv))
        return code, out.getvalue()

    def demo_entry_count(self):
        with patch.dict(os.environ, {"CALMCONNECT_DATA_DIR": str(self.demo_dir)}):
            user = auth.check_login("demo", self.password)
            return len(journal.find_entries(user["id"], limit=None)), auth.check_login("krishi", "correct horse")

    def test_creates_demo_without_touching_real_journal(self):
        code, out = self.run_demo()
        self.assertEqual(code, 0)
        self.password = out.split("password: ")[1].split()[0]
        count, real_user_in_demo = self.demo_entry_count()
        self.assertEqual(count, len(demo.SAMPLE_ENTRIES))
        self.assertIsNone(real_user_in_demo)

        self.assertEqual(Path(self.data_dir, "journal.db").read_bytes(), self.real_db)
        os.environ["CALMCONNECT_DATA_DIR"] = self.data_dir
        self.assertEqual(journal.get_entry(self.real_user, self.real_entry["id"])["text"], "My own entry")
        self.assertIsNone(auth.check_login("demo", self.password))

    def test_refuses_to_overwrite_and_resets_on_request(self):
        self.run_demo()
        code, out = self.run_demo()
        self.assertEqual(code, 1)
        self.assertIn("--reset", out)

        code, out = self.run_demo("--reset")
        self.assertEqual(code, 0)
        self.password = out.split("password: ")[1].split()[0]
        count, _ = self.demo_entry_count()
        self.assertEqual(count, len(demo.SAMPLE_ENTRIES))  # replaced, not doubled

    def test_db_path_setting_cannot_redirect_demo_into_real_journal(self):
        with patch.dict(os.environ, {"DB_PATH": str(Path(self.data_dir, "journal.db"))}):
            self.run_demo()
        self.assertEqual(Path(self.data_dir, "journal.db").read_bytes(), self.real_db)
