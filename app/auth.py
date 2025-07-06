TOKENS = {
    "test_user": "secret123"
}

def authenticate(user_id, token):
    return TOKENS.get(user_id) == token
