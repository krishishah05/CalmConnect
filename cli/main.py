import argparse
import sys

from rich.console import Console
from rich.table import Table
from rich import box

from app.journal import create_entry
from app.analysis import analyze_sentiment
from app.storage import save_entry, get_user_entries
from app.stats import get_streak, get_weekly_summary

console = Console()

MOOD_COLOR = {"positive": "green", "negative": "red", "neutral": "yellow"}


def cmd_log(args):
    entry = create_entry(args.text, args.user_id)
    result = analyze_sentiment(args.text)
    entry.update(result)
    save_entry({**entry, "emotions": ",".join(entry["emotions"])})

    color = MOOD_COLOR.get(result["mood"], "white")
    console.print(
        f"Entry saved. Mood: [{color}]{result['mood']}[/{color}] "
        f"(polarity {result['polarity']:.2f})"
    )
    if result["emotions"]:
        console.print(f"Detected emotions: {', '.join(result['emotions'])}")


def cmd_history(args):
    entries = get_user_entries(args.user_id, limit=args.limit)
    if not entries:
        console.print("No entries found.")
        return

    table = Table(box=box.SIMPLE_HEAD, show_header=True, expand=False)
    table.add_column("Date", style="dim", min_width=10)
    table.add_column("Mood", min_width=8)
    table.add_column("Score", justify="right", min_width=6)
    table.add_column("Entry")

    for e in entries:
        color = MOOD_COLOR.get(e["mood"], "white")
        snippet = e["text"][:70] + ("…" if len(e["text"]) > 70 else "")
        table.add_row(
            e["date"],
            f"[{color}]{e['mood']}[/{color}]",
            f"{e['polarity']:.2f}",
            snippet,
        )

    console.print(table)


def cmd_stats(args):
    summary = get_weekly_summary(args.user_id)
    streak = get_streak(args.user_id)

    console.print(f"\n[bold]Weekly summary — {args.user_id}[/bold]")
    console.print(f"  Entries logged:   {summary['entries']}")

    if summary["avg_polarity"] is not None:
        console.print(f"  Avg polarity:     {summary['avg_polarity']:.2f}")

    for mood, count in sorted(summary.get("mood_counts", {}).items()):
        color = MOOD_COLOR.get(mood, "white")
        console.print(f"  [{color}]{mood.capitalize():10}[/{color}] {count}")

    day_word = "day" if streak == 1 else "days"
    console.print(f"  Current streak:   {streak} {day_word}\n")


def main():
    parser = argparse.ArgumentParser(
        prog="calmconnect",
        description="Track your mood from the command line.",
    )
    parser.add_argument("user_id", help="Your user ID")
    sub = parser.add_subparsers(dest="command", required=True)

    log_p = sub.add_parser("log", help="Log a journal entry")
    log_p.add_argument("text", help="Your journal text (use quotes)")

    hist_p = sub.add_parser("history", help="View recent entries")
    hist_p.add_argument("--limit", type=int, default=10, metavar="N")

    sub.add_parser("stats", help="Weekly mood summary and streak")

    args = parser.parse_args()

    if args.command == "log":
        cmd_log(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
