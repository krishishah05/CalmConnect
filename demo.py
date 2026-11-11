"""Create a separate demo journal filled with sample entries.

    python demo.py            # create demo-data/ with the sample entries
    python demo.py --reset    # delete demo-data/ and create it again

The entries are short illustrative reflections based on trips from a
semester abroad in Prague. They are sample data, not diary entries written
on those exact days. Only months or date ranges are known, so each entry is
placed on the first day of its period (October trips on October 1, for
example). Tone and feelings come from the normal analysis.

Your real journal in data/ is never opened. Run the app against the demo with:

    CALMCONNECT_DATA_DIR=demo-data flask --app api.main run
    CALMCONNECT_DATA_DIR=demo-data calmconnect login demo
"""

import argparse
import os
import secrets
import shutil
import sys
from pathlib import Path

from app import auth, journal

DEMO_DIR = Path(__file__).resolve().parent / "demo-data"
DEMO_USERNAME = "demo"

SAMPLE_ENTRIES = [
    {
        "date": "2026-08-01",  # August 2026
        "place": "Iceland",
        "tags": ["Iceland", "Travel", "Summer"],
        "text": "Iceland was such a change of scenery. Everything felt so different from my "
                "usual routine, and I loved getting to spend a few days somewhere with such "
                "unique landscapes.",
    },
    {
        "date": "2026-09-01",  # Fall 2026
        "place": "Prague, Czech Republic",
        "tags": ["Prague", "Study Abroad", "Everyday Life"],
        "text": "Prague is slowly starting to feel like home. Between classes at UNYP, exploring "
                "the city, and traveling whenever I get the chance, this semester has been so "
                "different from my normal routine. I already know I'm going to miss this "
                "chapter of my life.",
    },
    {
        "date": "2026-10-01",  # October 2026
        "place": "Barcelona, Spain",
        "tags": ["Barcelona", "Spain", "Travel"],
        "text": "Barcelona was so colorful and full of energy. I loved seeing Park Güell and all "
                "the different architecture around the city. It was so nice to spend a few days "
                "exploring somewhere completely new.",
    },
    {
        "date": "2026-10-01",  # October 2026
        "place": "Rome, Italy",
        "tags": ["Rome", "Italy", "Travel"],
        "text": "Rome was such a fun mix of history and exploring. I loved wandering around the "
                "city and seeing how much there was to discover around every corner. It's one "
                "of those places where even just walking around feels special.",
    },
    {
        "date": "2026-10-01",  # October 2026
        "place": "Amalfi Coast, Italy",
        "tags": ["Amalfi Coast", "Italy", "Travel"],
        "text": "The Amalfi Coast was so beautiful. Between the water, colorful buildings, little "
                "shops, and lemon-themed everything, it was such a nice place to slow down and "
                "enjoy the scenery.",
    },
    {
        "date": "2026-10-30",  # October 30 to November 2, 2026
        "place": "Dublin, Ireland",
        "tags": ["Dublin", "Ireland", "Halloween", "Travel"],
        "text": "Spent Halloween weekend in Ireland! Dublin had such a different atmosphere from "
                "Prague, and I loved getting to experience another new place during this "
                "semester abroad.",
    },
    {
        "date": "2026-11-06",  # November 6 to 9, 2026
        "place": "Marrakech and the Sahara, Morocco",
        "tags": ["Marrakech", "Morocco", "Sahara", "Travel"],
        "text": "Morocco felt so different from the other places I've visited this semester. "
                "Traveling from Marrakech toward the Sahara and seeing the desert landscapes was "
                "such a unique experience. It's amazing how many different places I've gotten "
                "to explore.",
    },
]


def load_demo() -> str:
    """Add a demo account with the sample entries to the current data
    directory, through the same code path as any other entry. Returns the
    account's password."""
    password = secrets.token_urlsafe(9)
    user_id = auth.register(DEMO_USERNAME, password)
    for sample in SAMPLE_ENTRIES:
        journal.create_entry(
            user_id, sample["text"], place=sample["place"], tags=sample["tags"],
            entry_date=sample["date"],
        )
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a separate demo journal with sample entries.")
    parser.add_argument("--reset", action="store_true", help="delete the demo journal and create it again")
    args = parser.parse_args(argv)

    if DEMO_DIR.exists():
        if not args.reset:
            print(f"{DEMO_DIR.name}/ already exists. Run `python demo.py --reset` to start over.")
            return 1
        shutil.rmtree(DEMO_DIR)

    # Point the app at the demo folder only. DB_PATH would override it, so drop it.
    os.environ["CALMCONNECT_DATA_DIR"] = str(DEMO_DIR)
    os.environ.pop("DB_PATH", None)
    password = load_demo()

    print(f"Created {DEMO_DIR.name}/ with {len(SAMPLE_ENTRIES)} sample entries.")
    print(f"Log in as '{DEMO_USERNAME}' with the password: {password}\n")
    print(f"  Browser:  CALMCONNECT_DATA_DIR={DEMO_DIR.name} flask --app api.main run")
    print(f"  Terminal: CALMCONNECT_DATA_DIR={DEMO_DIR.name} calmconnect login {DEMO_USERNAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
