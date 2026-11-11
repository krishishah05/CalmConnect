import re
import unittest

from app import auth, journal
from tests.support import TempDataTestCase


class WebTestCase(TempDataTestCase):
    def setUp(self):
        super().setUp()
        from api.main import create_app
        self.client = create_app({"TESTING": True}).test_client()

    def csrf(self, path="/login"):
        html = self.client.get(path).get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def post(self, path, data, csrf_from="/login"):
        return self.client.post(path, data={"csrf_token": self.csrf(csrf_from), **data})

    def login(self, username="alice", password="correct horse"):
        return self.post("/login", {"username": username, "password": password})


class TestWebAuth(WebTestCase):
    def test_pages_require_login(self):
        for path in ["/", "/entries", "/entries/1", "/entries/1/edit", "/collections", "/reflect"]:
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp.headers["Location"].endswith("/login"))

    def test_register_logs_you_in(self):
        resp = self.post("/register", {"username": "alice", "password": "correct horse"}, "/register")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_bad_login(self):
        self.make_user()
        resp = self.login(password="wrong password")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Incorrect username or password", resp.get_data(as_text=True))

    def test_post_without_csrf_token_is_rejected(self):
        self.make_user()
        resp = self.client.post("/login", data={"username": "alice", "password": "correct horse"})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/login", data={"username": "alice", "password": "correct horse",
                                                "csrf_token": "guessed"})
        self.assertEqual(resp.status_code, 400)

    def test_logout_revokes_the_session_token(self):
        self.make_user()
        self.login()
        with self.client.session_transaction() as session:
            token = session["token"]
        self.assertIsNotNone(auth.user_for_token(token))
        self.post("/logout", {}, csrf_from="/")
        self.assertIsNone(auth.user_for_token(token))
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_session_cookie_flags(self):
        self.make_user()
        resp = self.login()
        cookie = resp.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)


class TestWebJournal(WebTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.login()

    def test_write_read_edit_delete(self):
        resp = self.post("/entries", {"text": "First night in Copenhagen. Tired but happy.",
                                      "title": "Arrival", "place": "Copenhagen",
                                      "tags": "travel, copenhagen", "date": ""}, "/")
        self.assertEqual(resp.status_code, 302)
        entry_id = int(resp.headers["Location"].rsplit("/", 1)[1])

        page = self.client.get(f"/entries/{entry_id}").get_data(as_text=True)
        self.assertIn("First night in Copenhagen", page)
        self.assertIn("Arrival", page)
        self.assertIn("copenhagen", page)

        resp = self.post(f"/entries/{entry_id}/edit",
                         {"text": "Edited text", "title": "Arrival", "place": "Copenhagen",
                          "tags": "copenhagen", "date": "2026-11-01"}, f"/entries/{entry_id}/edit")
        self.assertEqual(resp.status_code, 302)
        entry = journal.get_entry(self.user, entry_id)
        self.assertEqual((entry["text"], entry["tags"], entry["entry_date"]),
                         ("Edited text", ["copenhagen"], "2026-11-01"))

        self.assertIn("can't be undone", self.client.get(f"/entries/{entry_id}/delete").get_data(as_text=True))
        resp = self.post(f"/entries/{entry_id}/delete", {}, f"/entries/{entry_id}/delete")
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(journal.get_entry(self.user, entry_id))

    def test_validation_error_keeps_what_was_typed(self):
        resp = self.post("/entries", {"text": "My words", "tags": "bad/tag"}, "/")
        self.assertEqual(resp.status_code, 400)
        html = resp.get_data(as_text=True)
        self.assertIn("My words", html)
        self.assertIn("isn&#39;t a valid tag", html)

    def test_user_generated_text_is_escaped(self):
        entry = journal.create_entry(self.user, "<script>alert(1)</script>", title="<b>hi</b>")
        html = self.client.get(f"/entries/{entry['id']}").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_cannot_open_someone_elses_entry(self):
        bob = self.make_user("bob")
        entry = journal.create_entry(bob, "bob's entry", tags="bobtrip")
        for path in [f"/entries/{entry['id']}", f"/entries/{entry['id']}/edit",
                     f"/entries/{entry['id']}/delete", "/collections/bobtrip"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
        resp = self.post(f"/entries/{entry['id']}/delete", {}, "/")
        self.assertEqual(resp.status_code, 404)
        self.assertIsNotNone(journal.get_entry(bob, entry["id"]))

    def test_journal_filters_and_collection_page(self):
        journal.create_entry(self.user, "Mint tea in the medina", entry_date="2026-10-01", tags="morocco")
        journal.create_entry(self.user, "Back to class", entry_date="2026-10-10", tags="school")

        html = self.client.get("/entries?tag=morocco").get_data(as_text=True)
        self.assertIn("Mint tea", html)
        self.assertNotIn("Back to class", html)
        html = self.client.get("/entries?q=class").get_data(as_text=True)
        self.assertIn("Back to class", html)
        self.assertNotIn("Mint tea", html)
        self.assertEqual(self.client.get("/entries?page=100000000000000000000").status_code, 200)
        self.assertEqual(self.client.get("/entries/100000000000000000000").status_code, 404)
        resp = self.client.get("/entries?from=2026-10-10&to=2026-10-01")
        self.assertIn("on or before", resp.get_data(as_text=True))

        html = self.client.get("/collections").get_data(as_text=True)
        self.assertIn("morocco", html)
        html = self.client.get("/collections/morocco").get_data(as_text=True)
        self.assertIn("Mint tea", html)
        self.assertEqual(self.client.get("/collections/nothing").status_code, 404)

    def test_reflect_and_prompt_pages(self):
        self.assertIn("No entries in the last 7 days", self.client.get("/reflect").get_data(as_text=True))
        journal.create_entry(self.user, "A calm evening")
        self.assertIn("You wrote on 1 of the last 7 days", self.client.get("/reflect").get_data(as_text=True))
        html = self.client.get("/?prompt=1").get_data(as_text=True)
        self.assertTrue(any(p.replace("'", "&#39;") in html for p in journal.PROMPTS))


if __name__ == "__main__":
    unittest.main()
