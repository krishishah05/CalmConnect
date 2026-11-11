"""CalmConnect from the terminal.

    calmconnect register
    calmconnect journal --tags travel,copenhagen
    calmconnect history --tag copenhagen --oldest
    calmconnect reflect

Run `calmconnect <command> --help` for the options on each command.
"""

import argparse
import getpass
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import ValidationError, auth, journal
from app.stats import collection_summary, weekly_summary
from app.storage import data_dir

console = Console(highlight=False)

TONE_STYLE = {"positive": "green", "neutral": "yellow", "negative": "red"}

# Anything the user wrote goes through rich.markup.escape before printing, so
# text like "[/b]" in an entry is shown as-is instead of read as formatting.


class CliError(Exception):
    """A problem to report to the user, followed by exit status 1."""


# --- login session ----------------------------------------------------------

def _session_file() -> Path:
    return data_dir() / "cli_session"


def _save_session(token: str):
    """Store a new CLI login, revoking whichever one it replaces."""
    auth.revoke_token(_saved_token())
    path = _session_file()
    path.unlink(missing_ok=True)
    # Create the file readable only by the current OS user.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(token)


def _saved_token() -> str | None:
    path = _session_file()
    return path.read_text().strip() if path.exists() else None


def current_user() -> dict:
    user = auth.user_for_token(_saved_token())
    if user is None:
        raise CliError("You're not logged in. Run `calmconnect login` (or `register`) first.")
    return user


# --- input helpers ----------------------------------------------------------

def _read_multiline(intro: str) -> str:
    """Read an entry from stdin. Piped input is read as-is; at a terminal the
    user types until Ctrl-D so entries can have several paragraphs."""
    if not sys.stdin.isatty():
        return sys.stdin.read()
    console.print(intro)
    console.print("[dim]Finish with Ctrl-D on an empty line (Ctrl-Z then Enter on Windows). "
                  "Ctrl-C cancels.[/dim]\n")
    return sys.stdin.read()


def _edit_in_editor(text: str) -> str | None:
    """Open $VISUAL or $EDITOR on the text, like `git commit` does. Returns
    None if no editor is configured."""
    editor = os.getenv("VISUAL") or os.getenv("EDITOR")
    if not editor:
        return None
    # NamedTemporaryFile is created readable only by the current user.
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
        path = f.name
    try:
        subprocess.run([*shlex.split(editor), path], check=True)
        return Path(path).read_text()
    except (OSError, subprocess.CalledProcessError) as error:
        raise CliError(f"Couldn't run your editor ({editor}): {error}") from None
    finally:
        os.unlink(path)


def _ask_password(confirm: bool = False) -> str:
    password = getpass.getpass("Password: ")
    if confirm and getpass.getpass("Password again: ") != password:
        raise CliError("Those passwords didn't match.")
    return password


# --- output helpers ---------------------------------------------------------

def _tone(sentiment: str | None) -> str:
    if not sentiment:
        return "[dim]no entry[/dim]"
    return f"[{TONE_STYLE[sentiment]}]{sentiment}[/]"


def _entry_heading(entry: dict) -> str:
    parts = [journal.nice_date(entry["entry_date"])]
    if entry["place"]:
        parts.append(escape(entry["place"]))
    return " · ".join(parts)


def _entry_footer(entry: dict) -> str:
    parts = [f"tone: {_tone(entry['sentiment'])} ({entry['polarity']:+.2f})"]
    if entry["emotions"]:
        parts.append("feelings: " + ", ".join(entry["emotions"]))
    if entry["tags"]:
        parts.append("tags: " + ", ".join(f"#{t}" for t in entry["tags"]))
    return "  ·  ".join(parts)


def _snippet(entry: dict, length: int = 120) -> str:
    text = " ".join(entry["text"].split())
    text = escape(text if len(text) <= length else text[: length - 1].rstrip() + "…")
    return f"[bold]{escape(entry['title'])}[/bold]  {text}" if entry["title"] else text


def _entries_table(entries: list[dict]) -> Table:
    # One line per entry: the text column absorbs any lack of space and the
    # rest keep their width.
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, expand=True)
    table.add_column("ID", justify="right", style="dim", no_wrap=True, min_width=2)
    table.add_column("Date", no_wrap=True, min_width=10)
    table.add_column("Entry", ratio=1, no_wrap=True, overflow="ellipsis")
    table.add_column("Tone", no_wrap=True, min_width=8)
    table.add_column("Tags", style="dim", no_wrap=True, overflow="ellipsis", max_width=24)
    for entry in entries:
        table.add_row(
            str(entry["id"]),
            entry["entry_date"],
            _snippet(entry),
            _tone(entry["sentiment"]),
            " ".join(f"#{t}" for t in entry["tags"]),
        )
    return table


def _show_entry(entry: dict):
    body = Text()
    if entry["prompt"]:
        body.append(entry["prompt"] + "\n\n", style="italic dim")
    body.append(entry["text"])
    console.print(Panel(
        body,
        title=f"[bold]{escape(entry['title'] or 'Journal entry')}[/bold]",
        subtitle=f"#{entry['id']} · {_entry_heading(entry)}",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print(_entry_footer(entry))


def _tone_bars(counts: dict, total: int):
    for label, count in counts.items():
        width = round(count / total * 20) if total else 0
        bar = "█" * width or "·"
        console.print(f"  {label:9} [{TONE_STYLE[label]}]{bar}[/] {count}")


def _day_strip(days: list[dict], by_date: bool = False):
    """One column per day with its tone. Collections are labelled by date
    ("Oct 1") since they can span weeks; the weekly view uses weekdays."""
    table = Table(box=None, show_header=True, pad_edge=False)
    for day in days:
        table.add_column(journal.short_date(day["date"]) if by_date else day["weekday"],
                         justify="center")
    table.add_row(*[_tone(d["sentiment"]) for d in days])
    console.print(table)


# --- commands ---------------------------------------------------------------

def cmd_register(args):
    username = args.username or input("Choose a username: ")
    user_id = auth.register(username, _ask_password(confirm=True))
    _save_session(auth.issue_token(user_id))
    console.print(f"Welcome, [bold]{username.strip()}[/bold]. You're logged in. "
                  "Try `calmconnect journal` whenever you're ready.")


def cmd_login(args):
    username = args.username or input("Username: ")
    user = auth.check_login(username, _ask_password())
    if user is None:
        raise CliError("Incorrect username or password.")
    _save_session(auth.issue_token(user["id"]))
    console.print(f"Logged in as [bold]{user['username']}[/bold].")


def cmd_logout(args):
    auth.revoke_token(_saved_token())
    _session_file().unlink(missing_ok=True)
    console.print("Logged out.")


def cmd_journal(args):
    user = current_user()
    prompt = journal.random_prompt() if args.prompt else None
    text = args.text
    if text is None:
        intro = f"[italic]{prompt}[/italic]" if prompt else "[bold]How was today?[/bold]"
        text = _read_multiline(intro)

    entry = journal.create_entry(
        user["id"], text, title=args.title, place=args.place, tags=args.tags,
        entry_date=args.date, prompt=prompt,
    )
    console.print(f"\n[green]Saved[/green] entry #{entry['id']} for {_entry_heading(entry)}.")
    console.print(_entry_footer(entry))


def cmd_history(args):
    user = current_user()
    date_from, date_to = (args.on, args.on) if args.on else (args.date_from, args.date_to)
    entries = journal.find_entries(
        user["id"], search=args.search, tag=args.tag, date_from=date_from,
        date_to=date_to, oldest_first=args.oldest, limit=args.limit,
    )
    if not entries:
        filtering = args.search or args.tag or date_from or date_to
        console.print("No entries match that." if filtering else
                      "No entries yet. Start with `calmconnect journal`.")
        return
    console.print(_entries_table(entries))
    console.print("[dim]Read one with `calmconnect show ID`.[/dim]")


def cmd_show(args):
    entry = journal.get_entry(current_user()["id"], args.id)
    if entry is None:
        raise CliError(f"No entry #{args.id} in your journal.")
    _show_entry(entry)


def cmd_edit(args):
    user = current_user()
    entry = journal.get_entry(user["id"], args.id)
    if entry is None:
        raise CliError(f"No entry #{args.id} in your journal.")

    changes = {
        field: value
        for field, value in (("text", args.text), ("title", args.title), ("place", args.place),
                             ("tags", args.tags), ("date", args.date))
        if value is not None
    }
    if not changes:
        # No options given: edit the text itself.
        new_text = _edit_in_editor(entry["text"])
        if new_text is None:
            console.print(Panel(Text(entry["text"]), title="Current text", box=box.ROUNDED))
            new_text = _read_multiline("Type the new text for this entry.")
        if new_text.strip() == entry["text"]:
            console.print("No changes made.")
            return
        changes["text"] = new_text

    updated = journal.edit_entry(user["id"], args.id, changes)
    console.print(f"[green]Updated[/green] entry #{args.id}.")
    console.print(_entry_footer(updated))


def cmd_delete(args):
    user = current_user()
    entry = journal.get_entry(user["id"], args.id)
    if entry is None:
        raise CliError(f"No entry #{args.id} in your journal.")
    if not args.yes:
        console.print(f"#{entry['id']} · {_entry_heading(entry)}\n  {_snippet(entry)}")
        if input("Delete this entry for good? [y/N] ").strip().lower() not in ("y", "yes"):
            console.print("Kept it.")
            return
    journal.delete_entry(user["id"], args.id)
    console.print(f"Deleted entry #{args.id}.")


def cmd_stats(args):
    summary = weekly_summary(current_user()["id"])
    console.print(f"\n[bold]Last 7 days[/bold]  [dim]{summary['start']} to {summary['end']}[/dim]\n")
    _day_strip(summary["daily"])

    console.print("\n[bold]Tone of entries[/bold]")
    _tone_bars(summary["sentiment_counts"], summary["total_entries"])
    if summary["average_polarity"] is not None:
        console.print(f"  average polarity {summary['average_polarity']:+.2f} "
                      f"({summary['average_sentiment']}), averaged per day")

    if summary["top_emotions"]:
        console.print("\n[bold]Feelings named most[/bold]")
        for item in summary["top_emotions"]:
            console.print(f"  {item['emotion']:9} {item['entries']} "
                          f"{'entry' if item['entries'] == 1 else 'entries'}")

    console.print("\n[bold]Consistency[/bold]")
    console.print(f"  wrote on {summary['days_journaled']} of {summary['days_in_period']} days, "
                  f"{summary['total_entries']} entries")
    console.print(f"  current streak {summary['current_streak']}, "
                  f"longest streak {summary['longest_streak']}\n")


def cmd_reflect(args):
    user = current_user()
    summary = weekly_summary(user["id"])
    console.print(Panel(
        "\n".join(summary["reflection"]),
        title="[bold]Your week[/bold]",
        subtitle="[dim]based on the words you wrote, not a diagnosis[/dim]",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    past = journal.revisit_entry(user["id"])
    if past:
        console.print(f"\n[bold]Looking back[/bold] [dim]{journal.describe_age(past['entry_date'])}[/dim]")
        _show_entry(past)


def cmd_tags(args):
    user = current_user()
    if not args.tag:
        tags = journal.list_collections(user["id"])
        if not tags:
            console.print("No tags yet. Add some with `calmconnect journal --tags travel,lisbon`.")
            return
        table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
        table.add_column("Tag")
        table.add_column("Entries", justify="right")
        table.add_column("Dates", style="dim")
        for t in tags:
            span = t["first_date"] if t["first_date"] == t["last_date"] else \
                f"{t['first_date']} to {t['last_date']}"
            table.add_row(f"#{t['tag']}", str(t["entries"]), span)
        console.print(table)
        console.print("[dim]Look back through one with `calmconnect tags TAG`.[/dim]")
        return

    summary = collection_summary(user["id"], args.tag)
    if summary is None:
        raise CliError(f"No entries tagged '{args.tag}'.")
    console.print(f"\n[bold]#{summary['tag']}[/bold]  [dim]{summary['total_entries']} entries, "
                  f"{summary['first_date']} to {summary['last_date']}[/dim]\n")
    _day_strip(summary["timeline"], by_date=True)
    if summary["tone_shift"]:
        console.print(summary["tone_shift"])
    if summary["top_emotions"]:
        console.print("Feelings named most: " + ", ".join(
            f"{e['emotion']} ({e['entries']})" for e in summary["top_emotions"]))
    console.print(_entries_table(summary["entries"]))


def cmd_import_legacy(args):
    count = journal.import_legacy(current_user()["id"], args.name)
    if count:
        console.print(f"Imported {count} entries saved under '{args.name}' by the old version.")
    else:
        console.print(f"No old entries found under '{args.name}'.")


# --- argument parsing -------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calmconnect",
        description="A quiet place to write at the end of the day.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("register", help="create an account")
    p.add_argument("username", nargs="?")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("login", help="log in on this computer")
    p.add_argument("username", nargs="?")
    p.set_defaults(func=cmd_login)

    sub.add_parser("logout", help="log out on this computer").set_defaults(func=cmd_logout)

    p = sub.add_parser("journal", help="write an entry",
                       description="Write an entry. Without TEXT, you can type several paragraphs.")
    p.add_argument("text", nargs="?", help="the entry (quote it), or leave out to type freely")
    p.add_argument("--title")
    p.add_argument("--place", help="where you were")
    p.add_argument("--tags", help="comma-separated, e.g. travel,copenhagen")
    p.add_argument("--date", help="write about an earlier day (YYYY-MM-DD)")
    p.add_argument("--prompt", action="store_true", help="show a question to get you started")
    p.set_defaults(func=cmd_journal)

    p = sub.add_parser("history", help="list and search past entries")
    p.add_argument("-s", "--search", help="match text, title or place")
    p.add_argument("-t", "--tag")
    p.add_argument("--on", metavar="DATE", help="only this day (YYYY-MM-DD)")
    p.add_argument("--from", dest="date_from", metavar="DATE")
    p.add_argument("--to", dest="date_to", metavar="DATE")
    p.add_argument("--oldest", action="store_true", help="oldest first, to read in order")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("show", help="read one entry")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("edit", help="change an entry",
                       description="Change an entry. With no options, edit the text in $EDITOR.")
    p.add_argument("id", type=int)
    p.add_argument("--text")
    p.add_argument("--title")
    p.add_argument("--place")
    p.add_argument("--tags", help="replaces the existing tags; pass '' to clear")
    p.add_argument("--date")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("delete", help="delete an entry")
    p.add_argument("id", type=int)
    p.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    p.set_defaults(func=cmd_delete)

    sub.add_parser("stats", help="numbers for the last 7 days").set_defaults(func=cmd_stats)
    sub.add_parser("reflect", help="a short look back at your week").set_defaults(func=cmd_reflect)

    p = sub.add_parser("tags", help="list tags, or look back through one")
    p.add_argument("tag", nargs="?")
    p.set_defaults(func=cmd_tags)

    p = sub.add_parser("import-legacy", help="bring in entries saved by the first version")
    p.add_argument("name", help="the user_id you used with the old CLI")
    p.set_defaults(func=cmd_import_legacy)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValidationError, CliError) as error:
        console.print(f"[red]{escape(str(error))}[/red]")
        return 1
    except (KeyboardInterrupt, EOFError):
        console.print("\nCancelled. Nothing was saved.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
