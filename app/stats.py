"""Streaks and weekly summaries, calculated from stored entries.

The reflection text only restates what the numbers show. It doesn't guess at
causes or say anything about someone's mental health.
"""

from collections import Counter
from datetime import date, timedelta
from statistics import mean

from app import storage
from app.analysis import classify_polarity
from app.journal import local_today, normalize_tag

WEEK_LENGTH = 7


def calculate_streaks(days, today: date) -> tuple[int, int]:
    """Return (current, longest) runs of consecutive days with an entry.

    The current streak stays alive through today if the user wrote yesterday,
    so it doesn't drop to 0 every morning before they've had a chance to write.
    Multiple entries on one day count once.
    """
    unique_days = sorted(set(days))

    longest = run = 0
    previous = None
    for day in unique_days:
        run = run + 1 if previous and (day - previous).days == 1 else 1
        longest = max(longest, run)
        previous = day

    written = set(unique_days)
    day = today if today in written else today - timedelta(days=1)
    current = 0
    while day in written:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def count_sentiments(entries: list[dict]) -> dict:
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for entry in entries:
        counts[entry["sentiment"]] += 1
    return counts


def top_emotions(entries: list[dict], limit: int = 3) -> list[dict]:
    """The most common emotions, counted once per entry that mentions them.
    Ties are broken alphabetically so the output is stable."""
    counts = Counter(emotion for e in entries for emotion in set(e["emotions"]))
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"emotion": emotion, "entries": count} for emotion, count in ranked[:limit]]


def _day_stats(day: date, day_entries: list[dict]) -> dict:
    average = round(mean(e["polarity"] for e in day_entries), 4) if day_entries else None
    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%a"),
        "entries": len(day_entries),
        "average_polarity": average,
        "sentiment": classify_polarity(average) if average is not None else None,
    }


def _average_of_days(daily: list[dict]) -> float | None:
    """Mean of each day's average, so a day with five entries doesn't
    outweigh a day with one."""
    written = [d["average_polarity"] for d in daily if d["entries"]]
    return round(mean(written), 4) if written else None


def summarize_week(entries: list[dict], end: date) -> dict:
    """Summarise the 7 days ending on `end` (inclusive). Days without entries
    are included so gaps show up in the daily trend."""
    start = end - timedelta(days=WEEK_LENGTH - 1)
    by_day: dict[date, list[dict]] = {start + timedelta(days=i): [] for i in range(WEEK_LENGTH)}
    for entry in entries:
        day = date.fromisoformat(entry["entry_date"])
        if day in by_day:
            by_day[day].append(entry)
    in_range = [e for day_entries in by_day.values() for e in day_entries]

    daily = [_day_stats(day, day_entries) for day, day_entries in by_day.items()]
    average = _average_of_days(daily)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_entries": len(in_range),
        "days_journaled": sum(1 for d in daily if d["entries"]),
        "days_in_period": WEEK_LENGTH,
        "sentiment_counts": count_sentiments(in_range),
        "average_polarity": average,
        "average_sentiment": classify_polarity(average) if average is not None else None,
        "daily": daily,
        "top_emotions": top_emotions(in_range),
    }


def write_reflection(summary: dict) -> list[str]:
    """Turn a weekly summary into a few plain sentences."""
    if summary["total_entries"] == 0:
        return ["No entries in the last 7 days. Whenever you're ready, the page is here."]

    days = summary["days_journaled"]
    total = summary["total_entries"]
    lines = [
        f"You wrote on {days} of the last 7 days "
        f"({total} {'entry' if total == 1 else 'entries'})."
    ]

    counts = summary["sentiment_counts"]
    dominant, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    if dominant_count > total / 2:
        lines.append(f"Most of your entries had a {dominant} tone.")
    else:
        mix = ", ".join(f"{n} {label}" for label, n in counts.items() if n)
        lines.append(f"Your entries were a mix of tones: {mix}.")

    if summary["top_emotions"]:
        named = [f"{e['emotion']} ({e['entries']})" for e in summary["top_emotions"]]
        listed = named[0] if len(named) == 1 else ", ".join(named[:-1]) + " and " + named[-1]
        lines.append(f"Feelings that came up most: {listed}.")

    written = [d for d in summary["daily"] if d["entries"]]
    if len(written) >= 2:
        high = max(written, key=lambda d: d["average_polarity"])
        low = min(written, key=lambda d: d["average_polarity"])
        if high["average_polarity"] - low["average_polarity"] >= 0.2:
            lines.append(
                f"Your writing sounded most positive on {_weekday_name(high['date'])} "
                f"and most negative on {_weekday_name(low['date'])}."
            )

    current, longest = summary.get("current_streak", 0), summary.get("longest_streak", 0)
    if current >= 2:
        lines.append(f"You're on a {current}-day streak.")
    if longest > current and longest >= 3:
        lines.append(f"Your longest streak so far is {longest} days.")
    return lines


def _weekday_name(iso_day: str) -> str:
    return date.fromisoformat(iso_day).strftime("%A")


def weekly_summary(user_id: int, today: date | None = None) -> dict:
    """Everything the stats and reflect views need, for one user."""
    today = today or local_today()
    start = today - timedelta(days=WEEK_LENGTH - 1)
    entries = storage.list_entries(
        user_id, date_from=start.isoformat(), date_to=today.isoformat()
    )
    summary = summarize_week(entries, today)

    all_days = [date.fromisoformat(d) for d in storage.get_entry_dates(user_id)]
    summary["current_streak"], summary["longest_streak"] = calculate_streaks(all_days, today)
    summary["reflection"] = write_reflection(summary)
    return summary


def describe_tone_shift(entries: list[dict]) -> str | None:
    """Compare the first and second half of a collection (in date order).
    Needs at least 4 entries to say anything."""
    if len(entries) < 4:
        return None
    half = len(entries) // 2
    early = mean(e["polarity"] for e in entries[:half])
    late = mean(e["polarity"] for e in entries[-half:])
    if late - early >= 0.15:
        return "Your writing sounded more positive toward the end than at the start."
    if early - late >= 0.15:
        return "Your writing sounded more negative toward the end than at the start."
    return "The tone of your writing stayed fairly steady throughout."


def collection_summary(user_id: int, tag: str) -> dict | None:
    """A look back at every entry with one tag, such as a trip, in the order
    they were written. Returns None if the tag isn't used."""
    tag = normalize_tag(tag)
    entries = storage.list_entries(user_id, tag=tag, oldest_first=True)
    if not entries:
        return None

    by_day: dict[date, list[dict]] = {}
    for entry in entries:
        by_day.setdefault(date.fromisoformat(entry["entry_date"]), []).append(entry)
    timeline = [_day_stats(day, day_entries) for day, day_entries in by_day.items()]

    first, last = min(by_day), max(by_day)
    average = _average_of_days(timeline)
    return {
        "tag": tag,
        "first_date": first.isoformat(),
        "last_date": last.isoformat(),
        "days_spanned": (last - first).days + 1,
        "days_written": len(timeline),
        "total_entries": len(entries),
        "sentiment_counts": count_sentiments(entries),
        "average_polarity": average,
        "average_sentiment": classify_polarity(average) if average is not None else None,
        "top_emotions": top_emotions(entries),
        "timeline": timeline,
        "tone_shift": describe_tone_shift(entries),
        "entries": entries,
    }
