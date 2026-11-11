import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import ValidationError, auth, storage
from tests.support import TempDataTestCase


class TestRegistration(TempDataTestCase):
    def test_register_and_login(self):
        user_id = self.make_user("alice", "correct horse")
        user = auth.check_login("alice", "correct horse")
        self.assertEqual(user, {"id": user_id, "username": "alice"})

    def test_wrong_password_or_unknown_user(self):
        self.make_user("alice", "correct horse")
        self.assertIsNone(auth.check_login("alice", "wrong password"))
        self.assertIsNone(auth.check_login("nobody", "correct horse"))
        self.assertIsNone(auth.check_login("", ""))
        self.assertIsNone(auth.check_login(None, None))

    def test_usernames_are_case_insensitive_and_unique(self):
        self.make_user("Alice")
        with self.assertRaises(ValidationError):
            self.make_user("alice")
        self.assertIsNotNone(auth.check_login("ALICE", "correct horse"))

    def test_invalid_usernames(self):
        for name in ["", "ab", "has space", "x" * 33, "semi;colon", None]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                auth.register(name, "long enough password")

    def test_short_password(self):
        with self.assertRaises(ValidationError):
            auth.register("alice", "short")

    def test_password_is_not_stored_in_plain_text(self):
        self.make_user("alice", "correct horse")
        stored = storage.get_user_by_username("alice")["password_hash"]
        self.assertNotIn("correct horse", stored)
        self.assertTrue(stored.startswith(("scrypt:", "pbkdf2:")))


class TestTokens(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.user_id = self.make_user()

    def test_token_identifies_user(self):
        token = auth.issue_token(self.user_id)
        self.assertEqual(auth.user_for_token(token)["id"], self.user_id)

    def test_unknown_or_missing_token(self):
        self.assertIsNone(auth.user_for_token("not-a-real-token"))
        self.assertIsNone(auth.user_for_token(""))
        self.assertIsNone(auth.user_for_token(None))

    def test_only_a_hash_of_the_token_is_stored(self):
        token = auth.issue_token(self.user_id)
        conn = sqlite3.connect(storage.db_path())
        stored = [row[0] for row in conn.execute("SELECT token_hash FROM auth_tokens")]
        conn.close()
        self.assertEqual(len(stored), 1)
        self.assertNotEqual(stored[0], token)
        self.assertNotIn(token, stored[0])

    def test_revoked_token_stops_working(self):
        token = auth.issue_token(self.user_id)
        other = auth.issue_token(self.user_id)
        auth.revoke_token(token)
        self.assertIsNone(auth.user_for_token(token))
        self.assertIsNotNone(auth.user_for_token(other))

    def test_expired_token_stops_working(self):
        token = auth.issue_token(self.user_id)
        later = datetime.now(timezone.utc) + auth.TOKEN_LIFETIME + timedelta(seconds=5)
        with patch("app.auth._now", return_value=later.isoformat(timespec="seconds")):
            self.assertIsNone(auth.user_for_token(token))


if __name__ == "__main__":
    unittest.main()
