"""Accounts and login tokens.

Passwords are hashed with Werkzeug (scrypt), which ships with Flask.

After logging in, the web app, CLI and API all get the same kind of token: 32
random bytes that the client keeps and sends back. The database only stores a
SHA-256 hash of each token, so a leaked database file can't be used to log in.
A plain hash is enough here (unlike passwords) because the tokens are random
and long, so there's nothing to brute-force. Because tokens live in the
database, logging out really revokes them.
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app import ValidationError, storage

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256

TOKEN_LIFETIME = {
    "web": timedelta(days=14),
    "cli": timedelta(days=30),
    "api": timedelta(days=30),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register(username: str, password: str) -> int:
    """Create an account and return the user id."""
    username = (username or "").strip()
    password = password or ""
    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Usernames are 3-32 characters: letters, numbers, '.', '_' or '-'."
        )
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValidationError(
            f"Passwords need at least {MIN_PASSWORD_LENGTH} characters."
        )
    user_id = storage.create_user(username, generate_password_hash(password), _now())
    if user_id is None:
        raise ValidationError("That username is already taken.")
    return user_id


def check_login(username: str, password: str) -> dict | None:
    """Return {"id", "username"} if the credentials are right, else None."""
    if not username or not password or len(password) > MAX_PASSWORD_LENGTH:
        return None
    user = storage.get_user_by_username(username.strip())
    if user is None or not check_password_hash(user["password_hash"], password):
        return None
    return {"id": user["id"], "username": user["username"]}


def issue_token(user_id: int, kind: str) -> str:
    """Create a login token. Only its hash is stored, so this is the one
    chance to hand the real token to the client."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + TOKEN_LIFETIME[kind]
    storage.save_token(
        user_id,
        _hash_token(token),
        kind,
        now.isoformat(timespec="seconds"),
        expires.isoformat(timespec="seconds"),
    )
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    return storage.get_user_for_token(_hash_token(token), _now())


def revoke_token(token: str | None):
    if token:
        storage.delete_token(_hash_token(token))
