"""Journal operations shared by the CLI, the JSON API and the web pages.

This is where input gets validated and analysed before it reaches storage.

About dates: every entry has a UTC `created_at` timestamp and an `entry_date`,
the calendar day it belongs to in the writer's local time. Streaks and weekly
stats use `entry_date`, so something written at 11:55pm counts for that
evening rather than for "tomorrow in UTC". "Local" means the timezone of the
machine running CalmConnect (set TZ to change it).
"""

import random
import re
from datetime import date, datetime, timedelta, timezone

from app import ValidationError, storage
from app.analysis import analyze_text

MAX_ENTRY_LENGTH = 10_000
MAX_SHORT_TEXT = 120  # titles and places
MAX_PROMPT_LENGTH = 300
MAX_TAGS = 10
# Letters (including accented ones), numbers, '-' and '_'. Spaces become '-'.
TAG_PATTERN = re.compile(r"^[\w-]{1,30}$")
EDITABLE_FIELDS = {"text", "title", "place", "tags", "date"}

PROMPTS = [
    "What took most of your energy today?",
    "What's one thing that went better than you expected?",
    "Was there a moment today you'd like to remember?",
    "What's still on your mind as the day winds down?",
    "Who did you talk to today, and how did it feel?",
    "What would you tell yourself from this morning?",
    "What's one small thing you're looking forward to?",
    "What did you need today that you didn't get?",
    "Describe today in three words, then pick one and explain it.",
    "What can you set down before tomorrow?",
    "What made you smile today, even briefly?",
    "What's something you handled well today?",
]


def local_now() -> datetime:
    return datetime.now().astimezone()


def local_today() -> date:
    return local_now().date()


def random_prompt(rng=random) -> str:
    return rng.choice(PROMPTS)


def clean_text(text) -> str:
    if not isinstance(text, str):
        raise ValidationError("Entry text must be a string.")
    text = text.replace("\x00", "").strip()
    if not text:
        raise ValidationError("Entry text can't be empty.")
    if len(text) > MAX_ENTRY_LENGTH:
        raise ValidationError(
            f"Entries are limited to {MAX_ENTRY_LENGTH:,} characters."
        )
    return text


def parse_date(value, field: str = "date") -> date | None:
    """Parse an optional YYYY-MM-DD value from user input."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a YYYY-MM-DD string.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError(f"{field} must be a valid date like 2026-01-31.") from None


def _clean_optional(value, field: str, max_length: int) -> str | None:
    """Validate an optional single-line field such as a title or place."""
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = " ".join(value.split())  # also folds newlines into spaces
    if len(value) > max_length:
        raise ValidationError(f"{field} can be at most {max_length} characters.")
    return value or None


def normalize_tag(raw: str) -> str:
    """'  Study Abroad ' -> 'study-abroad', '#Morocco' -> 'morocco'"""
    return "-".join(raw.strip().lstrip("#").lower().split())


def clean_tags(value) -> list[str]:
    """Accept a list of tags or a comma-separated string ("travel, morocco")."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise ValidationError("tags must be a list of words.")

    tags: list[str] = []
    for raw in value:
        tag = normalize_tag(raw)
        if not tag or tag in tags:
            continue
        if not TAG_PATTERN.match(tag):
            raise ValidationError(
                f"'{raw.strip()}' isn't a valid tag. Use up to 30 letters, numbers or hyphens."
            )
        tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValidationError(f"An entry can have at most {MAX_TAGS} tags.")
    return tags


def _check_not_future(day: date, today: date):
    if day > today:
        raise ValidationError("Entries can't be dated in the future.")


def create_entry(user_id: int, text, *, title=None, place=None, tags=None,
                 entry_date=None, prompt=None, now: datetime | None = None) -> dict:
    """Validate, analyse and save a new entry.

    `entry_date` lets someone write about a day they missed. `now` should be
    timezone-aware; it's a parameter so tests can pin the clock.
    """
    now = now or local_now()
    text = clean_text(text)
    day = parse_date(entry_date) if isinstance(entry_date, str) else entry_date
    day = day or now.date()
    _check_not_future(day, now.date())

    entry = {
        "entry_date": day.isoformat(),
        "created_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "title": _clean_optional(title, "title", MAX_SHORT_TEXT),
        "place": _clean_optional(place, "place", MAX_SHORT_TEXT),
        "tags": clean_tags(tags),
        "text": text,
        "prompt": _clean_optional(prompt, "prompt", MAX_PROMPT_LENGTH),
        **analyze_text(text),
    }
    entry_id = storage.insert_entry(user_id, entry)
    return storage.get_entry(user_id, entry_id)


def get_entry(user_id: int, entry_id: int) -> dict | None:
    return storage.get_entry(user_id, entry_id)


def edit_entry(user_id: int, entry_id: int, changes: dict) -> dict | None:
    """Update only the fields present in `changes` (text, title, place, tags,
    date). Changing the text re-runs the analysis. Returns None if the entry
    doesn't exist or belongs to someone else."""
    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}.")
    if not changes:
        raise ValidationError("Nothing to update.")

    columns = {}
    if "text" in changes:
        columns["text"] = clean_text(changes["text"])
        columns.update(analyze_text(columns["text"]))
    if "title" in changes:
        columns["title"] = _clean_optional(changes["title"], "title", MAX_SHORT_TEXT)
    if "place" in changes:
        columns["place"] = _clean_optional(changes["place"], "place", MAX_SHORT_TEXT)
    if "date" in changes:
        day = parse_date(changes["date"])
        if day is None:
            raise ValidationError("date can't be empty.")
        _check_not_future(day, local_today())
        columns["entry_date"] = day.isoformat()
    tags = clean_tags(changes["tags"]) if "tags" in changes else None

    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not storage.update_entry(user_id, entry_id, columns, updated_at, tags=tags):
        return None
    return storage.get_entry(user_id, entry_id)


def delete_entry(user_id: int, entry_id: int) -> bool:
    return storage.delete_entry(user_id, entry_id)


def find_entries(user_id: int, search=None, tag=None, date_from=None, date_to=None,
                 oldest_first: bool = False, limit: int | None = 20,
                 offset: int = 0) -> list[dict]:
    """Search and filter entries. Dates are inclusive."""
    start = parse_date(date_from, "from")
    end = parse_date(date_to, "to")
    if start and end and start > end:
        raise ValidationError("The 'from' date must be on or before the 'to' date.")
    if limit is not None and limit < 1:
        raise ValidationError("limit must be at least 1.")
    if offset < 0:
        raise ValidationError("offset can't be negative.")
    search = search.strip() if isinstance(search, str) else None
    tag = normalize_tag(tag) if isinstance(tag, str) else None
    return storage.list_entries(
        user_id,
        search=search or None,
        tag=tag or None,
        date_from=start.isoformat() if start else None,
        date_to=end.isoformat() if end else None,
        oldest_first=oldest_first,
        limit=limit,
        offset=offset,
    )


def list_collections(user_id: int) -> list[dict]:
    """Tags the user has used, most recently active first."""
    return storage.list_tags(user_id)


def revisit_entry(user_id: int, today: date | None = None, rng=random) -> dict | None:
    """Pick an older entry (at least a week old) to look back on.

    Entries written on this calendar day in an earlier year are preferred;
    otherwise any older entry is chosen at random.
    """
    today = today or local_today()
    cutoff = (today - timedelta(days=7)).isoformat()
    older = storage.list_entries(user_id, date_to=cutoff)
    if not older:
        return None
    on_this_day = [e for e in older if e["entry_date"][5:] == today.isoformat()[5:]]
    return rng.choice(on_this_day or older)


def nice_date(iso_day: str) -> str:
    """'2026-11-11' -> 'Wednesday, November 11, 2026'"""
    day = date.fromisoformat(iso_day)
    return f"{day:%A, %B} {day.day}, {day.year}"


def describe_age(entry_date: str, today: date | None = None) -> str:
    """Human-friendly 'how long ago', e.g. '3 weeks ago' or '1 year ago today'."""
    today = today or local_today()
    then = date.fromisoformat(entry_date)
    days = (today - then).days
    if then.month == today.month and then.day == today.day and days >= 365:
        years = today.year - then.year
        return f"{years} year{'s' if years != 1 else ''} ago today"
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    for size, unit in ((365, "year"), (30, "month"), (7, "week"), (1, "day")):
        if days >= size:
            count = days // size
            return f"{count} {unit}{'s' if count != 1 else ''} ago"
    return entry_date  # future-dated legacy data; shouldn't normally happen


def import_legacy(user_id: int, legacy_name: str) -> int:
    """Move entries saved by the first version (under a bare name, with no
    account) into this user's journal. Text is re-analysed with the current
    analysis. The original time of day wasn't recorded, so created_at is set
    to midnight UTC on the original date."""
    rows = storage.get_legacy_entries(legacy_name)
    entries = [
        {
            "entry_date": row["date"],
            "created_at": f"{row['date']}T00:00:00+00:00",
            "text": row["text"],
            **analyze_text(row["text"]),
        }
        for row in rows
    ]
    return storage.move_legacy_entries(user_id, legacy_name, entries) if entries else 0
