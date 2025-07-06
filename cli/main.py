import argparse
from app.journal import create_entry
from app.analysis import analyze_sentiment
from app.storage import save_entry

def cli():
    parser = argparse.ArgumentParser(description="Log your daily mood entry")
    parser.add_argument("user_id", help="Your user ID")
    parser.add_argument("entry", help="Your journal text")
    args = parser.parse_args()

    entry = create_entry(args.entry, args.user_id)
    sentiment = analyze_sentiment(args.entry)
    entry.update(sentiment)
    save_entry(entry)
    print(f"Entry saved. Mood detected: {sentiment['mood']} (polarity {sentiment['polarity']:.2f})")

if __name__ == "__main__":
    cli()
