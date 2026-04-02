from datetime import datetime, timedelta
from app.storage import get_user_entries


def get_streak(user_id):
    entries = get_user_entries(user_id)
    if not entries:
        return 0

    dates = sorted(set(e["date"] for e in entries), reverse=True)
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()

    # Streak must start from today or yesterday to still be active
    if dates[0] < yesterday:
        return 0

    streak = 1
    for i in range(1, len(dates)):
        d1 = datetime.fromisoformat(dates[i - 1]).date()
        d2 = datetime.fromisoformat(dates[i]).date()
        if (d1 - d2).days == 1:
            streak += 1
        else:
            break
    return streak


def get_weekly_summary(user_id):
    cutoff = (datetime.now() - timedelta(days=7)).date().isoformat()
    entries = [e for e in get_user_entries(user_id) if e["date"] >= cutoff]

    if not entries:
        return {"entries": 0, "avg_polarity": None, "mood_counts": {}}

    avg_polarity = sum(e["polarity"] for e in entries) / len(entries)
    mood_counts: dict = {}
    for e in entries:
        mood_counts[e["mood"]] = mood_counts.get(e["mood"], 0) + 1

    return {
        "entries": len(entries),
        "avg_polarity": round(avg_polarity, 4),
        "mood_counts": mood_counts,
    }
