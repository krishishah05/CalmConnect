import os
import json

_DEV_TOKENS = {"test_user": "secret123"}


def _load_tokens():
    path = os.getenv("TOKENS_FILE", "data/tokens.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return _DEV_TOKENS


def authenticate(user_id, token):
    if not user_id or not token:
        return False
    return _load_tokens().get(user_id) == token
