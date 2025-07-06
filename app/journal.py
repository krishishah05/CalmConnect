import datetime

def create_entry(text, user_id):
    return {
        "user_id": user_id,
        "date": datetime.date.today().isoformat(),
        "text": text
    }
