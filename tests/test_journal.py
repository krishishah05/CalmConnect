import random
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app import ValidationError, journal
from tests.support import TempDataTestCase

NEW_YORK = ZoneInfo("America/New_York")


class TestCreateEntry(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def test_saves_text_analysis_and_timestamps(self):
        entry = journal.create_entry(self.user, "  Feeling really happy today  ")
        self.assertIsInstance(entry["id"], int)
        self.assertEqual(entry["text"], "Feeling really happy today")
        self.assertEqual(entry["sentiment"], "positive")
        self.assertEqual(entry["emotions"], ["happy"])
        self.assertEqual(entry["entry_date"], journal.local_today().isoformat())
        self.assertTrue(entry["created_at"].endswith("+00:00"))
        self.assertIsNone(entry["updated_at"])

    def test_ids_are_unique(self):
        first = journal.create_entry(self.user, "one")
        second = journal.create_entry(self.user, "two")
        self.assertNotEqual(first["id"], second["id"])

    def test_title_place_tags_and_prompt(self):
        entry = journal.create_entry(
            self.user, "Walked the medina all afternoon.",
            title="  First day in\nFes ", place="Fes, Morocco",
            tags="Travel, #Morocco, travel", prompt=journal.PROMPTS[0],
        )
        self.assertEqual(entry["title"], "First day in Fes")
        self.assertEqual(entry["place"], "Fes, Morocco")
        self.assertEqual(entry["tags"], ["morocco", "travel"])
        self.assertEqual(entry["prompt"], journal.PROMPTS[0])

    def test_tags_accept_a_list_and_normalize(self):
        entry = journal.create_entry(self.user, "x", tags=["Study Abroad", "Zürich"])
        self.assertEqual(entry["tags"], ["study-abroad", "zürich"])

    def test_invalid_input(self):
        bad = [
            {"text": ""},
            {"text": "   \n "},
            {"text": None},
            {"text": 42},
            {"text": "x" * (journal.MAX_ENTRY_LENGTH + 1)},
            {"text": "ok", "title": "t" * 121},
            {"text": "ok", "tags": ["has/slash"]},
            {"text": "ok", "tags": [f"tag{i}" for i in range(11)]},
            {"text": "ok", "tags": {"not": "a list"}},
            {"text": "ok", "entry_date": "2026-13-01"},
            {"text": "ok", "entry_date": "yesterday"},
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                journal.create_entry(self.user, kwargs.pop("text"), **kwargs)
        self.assertEqual(journal.find_entries(self.user), [])

    def test_can_write_about_an_earlier_day_but_not_the_future(self):
        yesterday = (journal.local_today() - timedelta(days=1)).isoformat()
        entry = journal.create_entry(self.user, "Catching up", entry_date=yesterday)
        self.assertEqual(entry["entry_date"], yesterday)

        tomorrow = (journal.local_today() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValidationError):
            journal.create_entry(self.user, "From the future", entry_date=tomorrow)

    def test_entry_just_before_midnight_belongs_to_that_local_day(self):
        # 11:50pm in New York is already the next day in UTC.
        late = datetime(2026, 3, 1, 23, 50, tzinfo=NEW_YORK)
        entry = journal.create_entry(self.user, "Late one", now=late)
        self.assertEqual(entry["entry_date"], "2026-03-01")
        self.assertEqual(entry["created_at"], "2026-03-02T04:50:00+00:00")

        just_after = datetime(2026, 3, 2, 0, 5, tzinfo=NEW_YORK)
        entry = journal.create_entry(self.user, "Early one", now=just_after)
        self.assertEqual(entry["entry_date"], "2026-03-02")


class TestEditAndDelete(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.entry = journal.create_entry(
            self.user, "I feel happy today", title="Good day", tags="school"
        )

    def test_edit_text_reanalyzes(self):
        updated = journal.edit_entry(self.user, self.entry["id"], {"text": "Actually I am exhausted and sad"})
        self.assertEqual(updated["text"], "Actually I am exhausted and sad")
        self.assertEqual(updated["sentiment"], "negative")
        self.assertEqual(updated["emotions"], ["tired", "sad"])
        self.assertIsNotNone(updated["updated_at"])
        # Fields that weren't sent are left alone.
        self.assertEqual(updated["title"], "Good day")
        self.assertEqual(updated["tags"], ["school"])

    def test_edit_metadata_only(self):
        updated = journal.edit_entry(self.user, self.entry["id"], {
            "title": "", "place": "Copenhagen", "tags": "travel, copenhagen",
            "date": "2026-01-05",
        })
        self.assertIsNone(updated["title"])
        self.assertEqual(updated["place"], "Copenhagen")
        self.assertEqual(updated["tags"], ["copenhagen", "travel"])
        self.assertEqual(updated["entry_date"], "2026-01-05")
        self.assertEqual(updated["text"], "I feel happy today")
        self.assertEqual(updated["sentiment"], self.entry["sentiment"])

    def test_clearing_tags(self):
        updated = journal.edit_entry(self.user, self.entry["id"], {"tags": ""})
        self.assertEqual(updated["tags"], [])

    def test_invalid_edits(self):
        for changes in [{}, {"text": ""}, {"mood": "x"}, {"date": ""}, {"user_id": 2},
                        {"date": (journal.local_today() + timedelta(days=2)).isoformat()}]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                journal.edit_entry(self.user, self.entry["id"], changes)
        self.assertEqual(journal.get_entry(self.user, self.entry["id"])["text"], "I feel happy today")

    def test_edit_missing_entry(self):
        self.assertIsNone(journal.edit_entry(self.user, 9999, {"text": "hi"}))

    def test_delete(self):
        self.assertTrue(journal.delete_entry(self.user, self.entry["id"]))
        self.assertIsNone(journal.get_entry(self.user, self.entry["id"]))
        self.assertFalse(journal.delete_entry(self.user, self.entry["id"]))
        self.assertEqual(journal.list_collections(self.user), [])

    def test_other_users_cannot_read_edit_or_delete(self):
        bob = self.make_user("bob")
        entry_id = self.entry["id"]
        self.assertIsNone(journal.get_entry(bob, entry_id))
        self.assertIsNone(journal.edit_entry(bob, entry_id, {"text": "hacked"}))
        self.assertIsNone(journal.edit_entry(bob, entry_id, {"tags": "hacked"}))
        self.assertFalse(journal.delete_entry(bob, entry_id))
        self.assertEqual(journal.find_entries(bob), [])
        self.assertEqual(journal.list_collections(bob), [])

        untouched = journal.get_entry(self.user, entry_id)
        self.assertEqual(untouched["text"], "I feel happy today")
        self.assertEqual(untouched["tags"], ["school"])


class TestSearchAndFilter(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        add = lambda day, text, **kw: journal.create_entry(self.user, text, entry_date=day, **kw)
        add("2026-10-01", "Landed in Marrakech, the heat was unreal", tags="travel,morocco",
            title="Arrival", place="Marrakech")
        add("2026-10-02", "Desert trip, sleeping under the stars", tags="travel,morocco")
        add("2026-10-02", "Long bus ride back", tags="morocco")
        add("2026-10-20", "Midterms all week", tags="school")
        add("2026-11-03", "Rainy day in Copenhagen, 100% cozy", tags="travel,copenhagen",
            place="Copenhagen")

    def texts(self, entries):
        return [e["text"] for e in entries]

    def test_newest_first_by_default(self):
        dates = [e["entry_date"] for e in journal.find_entries(self.user)]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_same_day_entries_keep_writing_order(self):
        entries = journal.find_entries(self.user, date_from="2026-10-02", date_to="2026-10-02",
                                       oldest_first=True)
        self.assertEqual(self.texts(entries),
                         ["Desert trip, sleeping under the stars", "Long bus ride back"])

    def test_filter_by_tag_reads_a_trip_in_order(self):
        entries = journal.find_entries(self.user, tag="Morocco", oldest_first=True)
        self.assertEqual([e["entry_date"] for e in entries], ["2026-10-01", "2026-10-02", "2026-10-02"])
        self.assertEqual(entries[0]["title"], "Arrival")

    def test_search_text_title_and_place(self):
        self.assertEqual(len(journal.find_entries(self.user, search="desert")), 1)
        self.assertEqual(len(journal.find_entries(self.user, search="ARRIVAL")), 1)
        self.assertEqual(len(journal.find_entries(self.user, search="copenhagen")), 1)
        self.assertEqual(journal.find_entries(self.user, search="lisbon"), [])

    def test_search_treats_wildcards_literally(self):
        self.assertEqual(self.texts(journal.find_entries(self.user, search="100%")),
                         ["Rainy day in Copenhagen, 100% cozy"])
        self.assertEqual(journal.find_entries(self.user, search="_"), [])

    def test_date_range_is_inclusive(self):
        entries = journal.find_entries(self.user, date_from="2026-10-02", date_to="2026-10-20")
        self.assertEqual(len(entries), 3)

    def test_filters_combine(self):
        entries = journal.find_entries(self.user, tag="travel", date_from="2026-10-02", search="stars")
        self.assertEqual(self.texts(entries), ["Desert trip, sleeping under the stars"])

    def test_limit_and_offset(self):
        first = journal.find_entries(self.user, limit=2)
        second = journal.find_entries(self.user, limit=2, offset=2)
        self.assertEqual(len(first), 2)
        self.assertFalse({e["id"] for e in first} & {e["id"] for e in second})

    def test_invalid_filters(self):
        for kwargs in [{"date_from": "2026-11-01", "date_to": "2026-10-01"},
                       {"date_from": "not a date"}, {"limit": 0}, {"offset": -1}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                journal.find_entries(self.user, **kwargs)

    def test_collections(self):
        tags = {t["tag"]: t for t in journal.list_collections(self.user)}
        self.assertEqual(tags["morocco"]["entries"], 3)
        self.assertEqual(tags["morocco"]["first_date"], "2026-10-01")
        self.assertEqual(tags["morocco"]["last_date"], "2026-10-02")
        self.assertEqual(tags["travel"]["entries"], 3)


class TestRevisit(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def test_nothing_to_revisit_without_older_entries(self):
        journal.create_entry(self.user, "today")
        self.assertIsNone(journal.revisit_entry(self.user, today=journal.local_today()))

    def test_prefers_the_same_day_in_an_earlier_year(self):
        today = date(2026, 11, 11)
        journal.create_entry(self.user, "a month ago", entry_date="2026-10-11")
        journal.create_entry(self.user, "a year ago", entry_date="2025-11-11")
        for seed in range(5):
            entry = journal.revisit_entry(self.user, today=today, rng=random.Random(seed))
            self.assertEqual(entry["text"], "a year ago")

    def test_falls_back_to_any_entry_at_least_a_week_old(self):
        today = date(2026, 11, 11)
        journal.create_entry(self.user, "recent", entry_date="2026-11-08")
        journal.create_entry(self.user, "older", entry_date="2026-10-20")
        self.assertEqual(journal.revisit_entry(self.user, today=today)["text"], "older")

    def test_describe_age(self):
        today = date(2026, 11, 11)
        self.assertEqual(journal.describe_age("2026-11-11", today), "today")
        self.assertEqual(journal.describe_age("2026-11-10", today), "yesterday")
        self.assertEqual(journal.describe_age("2026-11-01", today), "1 week ago")
        self.assertEqual(journal.describe_age("2026-09-01", today), "2 months ago")
        self.assertEqual(journal.describe_age("2025-11-11", today), "1 year ago today")


class TestPrompts(unittest.TestCase):
    def test_random_prompt_comes_from_the_list(self):
        self.assertIn(journal.random_prompt(random.Random(1)), journal.PROMPTS)


if __name__ == "__main__":
    unittest.main()
