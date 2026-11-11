import unittest
from datetime import date, timedelta

from app import journal
from app.stats import (calculate_streaks, collection_summary, describe_tone_shift,
                       summarize_week, weekly_summary, write_reflection)
from tests.support import TempDataTestCase

TODAY = date(2026, 11, 11)  # a Wednesday


def days_ago(*offsets):
    return [TODAY - timedelta(days=n) for n in offsets]


def fake_entry(day, polarity=0.0, sentiment="neutral", emotions=()):
    return {"entry_date": day, "polarity": polarity, "sentiment": sentiment,
            "emotions": list(emotions)}


class TestStreaks(unittest.TestCase):
    def test_no_entries(self):
        self.assertEqual(calculate_streaks([], TODAY), (0, 0))

    def test_streak_including_today(self):
        self.assertEqual(calculate_streaks(days_ago(0, 1, 2), TODAY), (3, 3))

    def test_streak_still_counts_before_writing_today(self):
        self.assertEqual(calculate_streaks(days_ago(1, 2), TODAY), (2, 2))

    def test_streak_broken_by_a_missed_day(self):
        self.assertEqual(calculate_streaks(days_ago(2, 3, 4), TODAY), (0, 3))

    def test_multiple_entries_on_one_day_count_once(self):
        self.assertEqual(calculate_streaks(days_ago(0, 0, 0, 1), TODAY), (2, 2))

    def test_longest_streak_in_the_past(self):
        days = days_ago(0, 1) + days_ago(10, 11, 12, 13, 14)
        self.assertEqual(calculate_streaks(days, TODAY), (2, 5))

    def test_streak_across_month_and_year_boundaries(self):
        days = [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1)]
        self.assertEqual(calculate_streaks(days, date(2026, 1, 1)), (3, 3))
        leap = [date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)]
        self.assertEqual(calculate_streaks(leap, date(2028, 3, 1)), (3, 3))


class TestWeeklySummary(unittest.TestCase):
    def test_empty_week(self):
        summary = summarize_week([], TODAY)
        self.assertEqual(summary["total_entries"], 0)
        self.assertEqual(summary["days_journaled"], 0)
        self.assertIsNone(summary["average_polarity"])
        self.assertEqual(summary["sentiment_counts"], {"positive": 0, "neutral": 0, "negative": 0})
        self.assertEqual(len(summary["daily"]), 7)
        self.assertTrue(all(d["entries"] == 0 and d["sentiment"] is None for d in summary["daily"]))

    def test_window_is_exactly_seven_days(self):
        entries = [fake_entry(d.isoformat()) for d in days_ago(0, 6, 7)]
        summary = summarize_week(entries, TODAY)
        self.assertEqual(summary["start"], "2026-11-05")
        self.assertEqual(summary["end"], "2026-11-11")
        self.assertEqual(summary["total_entries"], 2)  # 7 days ago is outside the window

    def test_daily_trend_includes_missing_days(self):
        entries = [fake_entry("2026-11-09", 0.5, "positive")]
        daily = summarize_week(entries, TODAY)["daily"]
        self.assertEqual([d["date"] for d in daily][0], "2026-11-05")
        monday = next(d for d in daily if d["date"] == "2026-11-09")
        self.assertEqual((monday["weekday"], monday["entries"], monday["sentiment"]), ("Mon", 1, "positive"))
        self.assertEqual(sum(1 for d in daily if d["entries"] == 0), 6)

    def test_average_weights_each_day_equally(self):
        entries = [
            fake_entry("2026-11-10", -0.5, "negative"),
            fake_entry("2026-11-10", -0.5, "negative"),
            fake_entry("2026-11-10", -0.5, "negative"),
            fake_entry("2026-11-11", 0.5, "positive"),
        ]
        summary = summarize_week(entries, TODAY)
        self.assertEqual(summary["average_polarity"], 0.0)
        self.assertEqual(summary["sentiment_counts"], {"positive": 1, "neutral": 0, "negative": 3})
        tuesday = next(d for d in summary["daily"] if d["date"] == "2026-11-10")
        self.assertEqual((tuesday["entries"], tuesday["average_polarity"]), (3, -0.5))

    def test_top_emotions_count_entries_and_break_ties_alphabetically(self):
        entries = [
            fake_entry("2026-11-11", emotions=["tired", "anxious"]),
            fake_entry("2026-11-10", emotions=["tired"]),
            fake_entry("2026-11-09", emotions=["happy"]),
            fake_entry("2026-11-08", emotions=["calm"]),
        ]
        top = summarize_week(entries, TODAY)["top_emotions"]
        self.assertEqual(top, [
            {"emotion": "tired", "entries": 2},
            {"emotion": "anxious", "entries": 1},
            {"emotion": "calm", "entries": 1},
        ])


class TestReflection(unittest.TestCase):
    def test_no_entries(self):
        lines = write_reflection(summarize_week([], TODAY))
        self.assertEqual(len(lines), 1)
        self.assertIn("No entries", lines[0])

    def test_describes_only_what_the_data_shows(self):
        entries = [
            fake_entry("2026-11-09", 0.6, "positive", ["happy"]),
            fake_entry("2026-11-10", -0.4, "negative", ["tired"]),
            fake_entry("2026-11-11", 0.3, "positive", ["tired"]),
        ]
        summary = summarize_week(entries, TODAY)
        summary.update(current_streak=3, longest_streak=5)
        text = " ".join(write_reflection(summary))
        self.assertIn("You wrote on 3 of the last 7 days (3 entries).", text)
        self.assertIn("Most of your entries had a positive tone.", text)
        self.assertIn("tired (2) and happy (1)", text)
        self.assertIn("most positive on Monday and most negative on Tuesday", text)
        self.assertIn("3-day streak", text)
        self.assertIn("longest streak so far is 5 days", text)

    def test_mixed_tone(self):
        entries = [fake_entry("2026-11-10", 0.5, "positive"), fake_entry("2026-11-11", -0.5, "negative")]
        text = " ".join(write_reflection(summarize_week(entries, TODAY)))
        self.assertIn("mix of tones: 1 positive, 1 negative", text)


class TestToneShift(unittest.TestCase):
    def test_needs_enough_entries(self):
        self.assertIsNone(describe_tone_shift([fake_entry("2026-10-01", 0.5)] * 3))

    def test_directions(self):
        rising = [fake_entry("d", p) for p in (-0.4, -0.2, 0.3, 0.5)]
        falling = list(reversed(rising))
        steady = [fake_entry("d", p) for p in (0.1, 0.2, 0.1, 0.2)]
        self.assertIn("more positive toward the end", describe_tone_shift(rising))
        self.assertIn("more negative toward the end", describe_tone_shift(falling))
        self.assertIn("steady", describe_tone_shift(steady))


class TestStatsFromDatabase(TempDataTestCase):
    """weekly_summary and collection_summary read real stored entries, so
    edits and deletions should show up in them straight away."""

    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def test_empty_database(self):
        summary = weekly_summary(self.user, today=TODAY)
        self.assertEqual((summary["total_entries"], summary["current_streak"], summary["longest_streak"]), (0, 0, 0))
        self.assertIsNone(collection_summary(self.user, "anything"))

    def test_edits_and_deletes_are_reflected(self):
        happy = journal.create_entry(self.user, "So happy and grateful", entry_date="2026-11-10")
        journal.create_entry(self.user, "A quiet day", entry_date="2026-11-11")

        summary = weekly_summary(self.user, today=TODAY)
        self.assertEqual(summary["sentiment_counts"]["positive"], 1)
        self.assertEqual(summary["current_streak"], 2)

        journal.edit_entry(self.user, happy["id"], {"text": "Actually miserable and exhausted"})
        summary = weekly_summary(self.user, today=TODAY)
        self.assertEqual(summary["sentiment_counts"]["positive"], 0)
        self.assertEqual([e["emotion"] for e in summary["top_emotions"]], ["sad", "tired"])

        journal.delete_entry(self.user, happy["id"])
        summary = weekly_summary(self.user, today=TODAY)
        self.assertEqual(summary["total_entries"], 1)
        self.assertEqual(summary["current_streak"], 1)

    def test_stats_only_include_the_users_own_entries(self):
        bob = self.make_user("bob")
        journal.create_entry(bob, "bob's entry", entry_date="2026-11-11", tags="trip")
        self.assertEqual(weekly_summary(self.user, today=TODAY)["total_entries"], 0)
        self.assertIsNone(collection_summary(self.user, "trip"))

    def test_collection_summary_for_a_trip(self):
        for day, text in [("2026-10-01", "Nervous and exhausted after the flight"),
                          ("2026-10-02", "The market was overwhelming"),
                          ("2026-10-04", "Wonderful day, so happy here"),
                          ("2026-10-05", "Grateful for this amazing trip")]:
            journal.create_entry(self.user, text, entry_date=day, tags="morocco")
        journal.create_entry(self.user, "unrelated", entry_date="2026-10-03")

        summary = collection_summary(self.user, "Morocco")
        self.assertEqual(summary["tag"], "morocco")
        self.assertEqual(summary["total_entries"], 4)
        self.assertEqual((summary["first_date"], summary["last_date"]), ("2026-10-01", "2026-10-05"))
        self.assertEqual((summary["days_spanned"], summary["days_written"]), (5, 4))
        self.assertEqual([e["entry_date"] for e in summary["entries"]],
                         ["2026-10-01", "2026-10-02", "2026-10-04", "2026-10-05"])
        self.assertEqual(len(summary["timeline"]), 4)
        self.assertIn("more positive toward the end", summary["tone_shift"])


if __name__ == "__main__":
    unittest.main()
