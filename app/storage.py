import json
import os

DATA_FILE = "data/journal_entries.json"

def load_entries():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_entry(entry):
    entries = load_entries()
    entries.append(entry)
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2)

def get_user_entries(user_id):
    return [e for e in load_entries() if e["user_id"] == user_id]
