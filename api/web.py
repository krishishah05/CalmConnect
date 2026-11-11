"""Server-rendered pages for writing, reading and reflecting in a browser.

Login uses the same revocable tokens as the CLI and API; the token is kept in
Flask's signed, HttpOnly session cookie. Every POST form carries a CSRF token.
"""

import secrets
from datetime import datetime
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   session, url_for)

from app import ValidationError, auth, journal
from app.stats import collection_summary, weekly_summary

web = Blueprint("web", __name__)

PAGE_SIZE = 20


@web.before_request
def load_user_and_check_csrf():
    g.user = auth.user_for_token(session.get("token"))
    if request.method == "POST":
        expected = session.get("csrf_token")
        sent = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Your form expired. Please go back, refresh and try again.")


# Template globals rather than a context processor, so macros imported into a
# template can use them too.

@web.app_template_global()
def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@web.app_template_global()
def local_time(utc_timestamp: str) -> str:
    """Show a stored UTC timestamp in the server's local time, e.g. 'Nov 11, 9:42 PM'."""
    moment = datetime.fromisoformat(utc_timestamp).astimezone()
    return f"{moment:%b} {moment.day}, {moment.hour % 12 or 12}:{moment:%M %p}"


web.add_app_template_global(journal.nice_date, "nice_date")
web.add_app_template_global(journal.short_date, "short_date")
web.add_app_template_global(journal.describe_age, "describe_age")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("web.login"))
        return view(*args, **kwargs)
    return wrapper


def _start_session(user_id: int):
    session.clear()  # drop anything from before login, including the old CSRF token
    session["token"] = auth.issue_token(user_id)
    session.permanent = True


def _owned_entry_or_404(entry_id: int) -> dict:
    entry = journal.get_entry(g.user["id"], entry_id)
    if entry is None:
        abort(404)
    return entry


# --- accounts ---------------------------------------------------------------

@web.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "")
        try:
            user_id = auth.register(username, request.form.get("password", ""))
        except ValidationError as error:
            flash(str(error), "error")
            return render_template("auth.html", mode="register", username=username), 400
        _start_session(user_id)
        return redirect(url_for("web.write"))
    return render_template("auth.html", mode="register")


@web.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        user = auth.check_login(username, request.form.get("password", ""))
        if user is None:
            flash("Incorrect username or password.", "error")
            return render_template("auth.html", mode="login", username=username), 401
        _start_session(user["id"])
        return redirect(url_for("web.write"))
    if g.user:
        return redirect(url_for("web.write"))
    return render_template("auth.html", mode="login")


@web.post("/logout")
def logout():
    auth.revoke_token(session.get("token"))
    session.clear()
    return redirect(url_for("web.login"))


# --- writing ----------------------------------------------------------------

@web.get("/")
@login_required
def write():
    prompt = journal.random_prompt() if request.args.get("prompt") else None
    return render_template(
        "write.html", prompt=prompt, today=journal.local_today().isoformat()
    )


@web.post("/entries")
@login_required
def create_entry():
    form = request.form
    try:
        entry = journal.create_entry(
            g.user["id"],
            form.get("text", ""),
            title=form.get("title"),
            place=form.get("place"),
            tags=form.get("tags"),
            entry_date=form.get("date"),
            prompt=form.get("prompt"),
        )
    except ValidationError as error:
        flash(str(error), "error")
        return render_template(
            "write.html", prompt=form.get("prompt"), form=form,
            today=journal.local_today().isoformat(),
        ), 400
    flash("Saved. Thanks for writing today.", "success")
    return redirect(url_for("web.show_entry", entry_id=entry["id"]))


# --- reading ----------------------------------------------------------------

@web.get("/entries")
@login_required
def entries():
    filters = {
        "q": request.args.get("q", "").strip(),
        "tag": request.args.get("tag", "").strip(),
        "from": request.args.get("from", ""),
        "to": request.args.get("to", ""),
        "order": "oldest" if request.args.get("order") == "oldest" else "newest",
    }
    page = max(request.args.get("page", 1, type=int), 1)
    try:
        # Ask for one extra entry to know whether there's another page.
        found = journal.find_entries(
            g.user["id"], search=filters["q"], tag=filters["tag"],
            date_from=filters["from"], date_to=filters["to"],
            oldest_first=filters["order"] == "oldest",
            limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE,
        )
    except ValidationError as error:
        flash(str(error), "error")
        found = []
    return render_template(
        "entries.html",
        entries=found[:PAGE_SIZE],
        has_more=len(found) > PAGE_SIZE,
        page=page,
        filters=filters,
        tags=journal.list_collections(g.user["id"]),
    )


@web.get("/entries/<int:entry_id>")
@login_required
def show_entry(entry_id):
    return render_template("entry.html", entry=_owned_entry_or_404(entry_id))


@web.route("/entries/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit_entry(entry_id):
    entry = _owned_entry_or_404(entry_id)
    today = journal.local_today().isoformat()
    if request.method == "POST":
        form = request.form
        changes = {field: form.get(field, "") for field in ("text", "title", "place", "tags", "date")}
        try:
            journal.edit_entry(g.user["id"], entry_id, changes)
        except ValidationError as error:
            flash(str(error), "error")
            return render_template("edit.html", entry=entry, form=form, today=today), 400
        flash("Entry updated.", "success")
        return redirect(url_for("web.show_entry", entry_id=entry_id))
    return render_template("edit.html", entry=entry, form=None, today=today)


@web.route("/entries/<int:entry_id>/delete", methods=["GET", "POST"])
@login_required
def delete_entry(entry_id):
    entry = _owned_entry_or_404(entry_id)
    if request.method == "POST":
        journal.delete_entry(g.user["id"], entry_id)
        flash("Entry deleted.", "success")
        return redirect(url_for("web.entries"))
    return render_template("delete.html", entry=entry)


# --- collections and reflecting --------------------------------------------

@web.get("/collections")
@login_required
def collections():
    return render_template("collections.html", tags=journal.list_collections(g.user["id"]))


@web.get("/collections/<tag>")
@login_required
def collection(tag):
    summary = collection_summary(g.user["id"], tag)
    if summary is None:
        abort(404)
    return render_template("collection.html", summary=summary)


@web.get("/reflect")
@login_required
def reflect():
    return render_template(
        "reflect.html",
        summary=weekly_summary(g.user["id"]),
        past_entry=journal.revisit_entry(g.user["id"]),
    )
