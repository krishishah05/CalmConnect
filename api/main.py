"""Flask app: a JSON API under /api plus the small web journal in web.py.

Run locally with:  flask --app api.main run
"""

import os
import secrets
from functools import wraps

from flask import Blueprint, Flask, current_app, g, jsonify, request
from werkzeug.exceptions import HTTPException

from app import ValidationError, auth, journal
from app.stats import collection_summary, weekly_summary
from app.storage import data_dir

api = Blueprint("api", __name__, url_prefix="/api")

MAX_PAGE_SIZE = 100
PUBLIC_ENTRY_FIELDS = (
    "id", "entry_date", "created_at", "updated_at", "title", "place", "tags",
    "text", "prompt", "sentiment", "polarity", "emotions",
)


def _error(message: str, status: int, **headers):
    return jsonify({"error": message}), status, headers


def _public(entry: dict) -> dict:
    return {field: entry[field] for field in PUBLIC_ENTRY_FIELDS}


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    return data


def _int_arg(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError(f"{name} must be a whole number.") from None
    if value < minimum or (maximum is not None and value > maximum):
        limit = f" and {maximum}" if maximum is not None else ""
        raise ValidationError(f"{name} must be between {minimum}{limit}.")
    return value


def _bearer_token() -> str | None:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else None


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = auth.user_for_token(_bearer_token())
        if user is None:
            return _error("Missing or invalid token.", 401, **{"WWW-Authenticate": "Bearer"})
        g.user = user
        return view(*args, **kwargs)
    return wrapper


# --- accounts ---------------------------------------------------------------

@api.post("/register")
def register():
    data = _json_body()
    user_id = auth.register(data.get("username"), data.get("password"))
    return jsonify({"id": user_id, "username": data["username"].strip()}), 201


@api.post("/tokens")
def create_token():
    data = _json_body()
    user = auth.check_login(data.get("username"), data.get("password"))
    if user is None:
        return _error("Incorrect username or password.", 401)
    token = auth.issue_token(user["id"])
    return jsonify({
        "token": token,
        "expires_in_days": auth.TOKEN_LIFETIME.days,
    }), 201


@api.delete("/tokens/current")
@token_required
def revoke_current_token():
    auth.revoke_token(_bearer_token())
    return "", 204


# --- entries ----------------------------------------------------------------

@api.get("/entries")
@token_required
def list_entries():
    order = request.args.get("order", "newest")
    if order not in ("newest", "oldest"):
        raise ValidationError("order must be 'newest' or 'oldest'.")
    entries = journal.find_entries(
        g.user["id"],
        search=request.args.get("q"),
        tag=request.args.get("tag"),
        oldest_first=order == "oldest",
        date_from=request.args.get("from"),
        date_to=request.args.get("to"),
        limit=_int_arg("limit", 20, minimum=1, maximum=MAX_PAGE_SIZE),
        offset=_int_arg("offset", 0),
    )
    return jsonify({"entries": [_public(e) for e in entries]})


@api.post("/entries")
@token_required
def create_entry():
    data = _json_body()
    entry = journal.create_entry(
        g.user["id"],
        data.get("text"),
        title=data.get("title"),
        place=data.get("place"),
        tags=data.get("tags"),
        entry_date=data.get("date"),
        prompt=data.get("prompt"),
    )
    return jsonify(_public(entry)), 201


@api.get("/entries/<int:entry_id>")
@token_required
def get_entry(entry_id):
    entry = journal.get_entry(g.user["id"], entry_id)
    # Someone else's entry gets the same 404 as a missing one, so ids can't
    # be used to probe what exists.
    if entry is None:
        return _error("Entry not found.", 404)
    return jsonify(_public(entry))


@api.patch("/entries/<int:entry_id>")
@token_required
def edit_entry(entry_id):
    entry = journal.edit_entry(g.user["id"], entry_id, _json_body())
    if entry is None:
        return _error("Entry not found.", 404)
    return jsonify(_public(entry))


@api.delete("/entries/<int:entry_id>")
@token_required
def delete_entry(entry_id):
    if not journal.delete_entry(g.user["id"], entry_id):
        return _error("Entry not found.", 404)
    return "", 204


# --- collections and reflection ---------------------------------------------

@api.get("/tags")
@token_required
def list_tags():
    return jsonify({"tags": journal.list_collections(g.user["id"])})


@api.get("/tags/<tag>")
@token_required
def tag_summary(tag):
    summary = collection_summary(g.user["id"], tag)
    if summary is None:
        return _error("No entries with that tag.", 404)
    summary["entries"] = [_public(e) for e in summary["entries"]]
    return jsonify(summary)


@api.get("/stats")
@token_required
def stats():
    return jsonify(weekly_summary(g.user["id"]))


@api.get("/revisit")
@token_required
def revisit():
    entry = journal.revisit_entry(g.user["id"])
    if entry is None:
        return jsonify({"entry": None})
    return jsonify({"entry": _public(entry), "age": journal.describe_age(entry["entry_date"])})


# --- app setup --------------------------------------------------------------

def _load_secret_key() -> str:
    """Use CALMCONNECT_SECRET_KEY if set. Otherwise generate a random key once
    and keep it in the (git-ignored) data directory so logins survive a
    restart."""
    key = os.getenv("CALMCONNECT_SECRET_KEY")
    if key:
        return key
    path = data_dir() / "secret_key"
    try:
        # O_EXCL: if two processes start at once, only one writes the key.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    with os.fdopen(fd, "w") as f:
        f.write(secrets.token_hex(32))
    return path.read_text().strip()


def _handle_error(error):
    wants_json = request.path.startswith("/api/")
    if isinstance(error, HTTPException):
        return _error(error.description, error.code) if wants_json else error
    if isinstance(error, ValidationError):
        return _error(str(error), 400) if wants_json else (str(error), 400)
    # Log the traceback for whoever runs the server, but never send it (or the
    # request body, which may be a journal entry) back to the client.
    current_app.logger.exception("Unhandled error on %s %s", request.method, request.path)
    if wants_json:
        return _error("Something went wrong on our side.", 500)
    return "Something went wrong on our side.", 500


def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
    # Journal pages and API responses shouldn't sit in shared or browser caches.
    if not request.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def create_app(config: dict | None = None) -> Flask:
    from api.web import web

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=_load_secret_key(),
        MAX_CONTENT_LENGTH=64 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Turn on when serving over HTTPS so the cookie is never sent in clear text.
        SESSION_COOKIE_SECURE=os.getenv("CALMCONNECT_SECURE_COOKIES") == "1",
        PERMANENT_SESSION_LIFETIME=auth.TOKEN_LIFETIME,
    )
    app.config.update(config or {})
    app.register_blueprint(api)
    app.register_blueprint(web)
    app.register_error_handler(Exception, _handle_error)
    app.after_request(_security_headers)
    return app


if __name__ == "__main__":
    # Debug mode stays off: the Werkzeug debugger allows running code from the browser.
    create_app().run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
    )
