import unittest

from tests.support import TempDataTestCase


class APITestCase(TempDataTestCase):
    def setUp(self):
        super().setUp()
        from api.main import create_app
        self.client = create_app({"TESTING": True}).test_client()
        self.token = self.register_and_get_token("alice")

    def register_and_get_token(self, username, password="long enough password"):
        resp = self.client.post("/api/register", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 201, resp.get_json())
        resp = self.client.post("/api/tokens", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["token"]

    def headers(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}

    def create(self, text="Feeling okay", token=None, **fields):
        return self.client.post("/api/entries", json={"text": text, **fields},
                                headers=self.headers(token))


class TestAuthentication(APITestCase):
    def test_wrong_password(self):
        resp = self.client.post("/api/tokens", json={"username": "alice", "password": "nope"})
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn("token", resp.get_json())

    def test_duplicate_and_invalid_registration(self):
        resp = self.client.post("/api/register", json={"username": "ALICE", "password": "long enough password"})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post("/api/register", json={"username": "x", "password": "short"})
        self.assertEqual(resp.status_code, 400)

    def test_protected_routes_need_a_token(self):
        routes = [("get", "/api/entries"), ("post", "/api/entries"), ("get", "/api/entries/1"),
                  ("patch", "/api/entries/1"), ("delete", "/api/entries/1"), ("get", "/api/stats"),
                  ("get", "/api/tags"), ("get", "/api/tags/x"), ("get", "/api/revisit"), ("delete", "/api/tokens/current")]
        for method, url in routes:
            for headers in [{}, {"Authorization": "Bearer wrong"}, {"Authorization": self.token}]:
                with self.subTest(method=method, url=url, headers=headers):
                    resp = getattr(self.client, method)(url, headers=headers, json={})
                    self.assertEqual(resp.status_code, 401)
                    self.assertEqual(resp.headers["WWW-Authenticate"], "Bearer")

    def test_token_in_query_string_is_not_accepted(self):
        resp = self.client.get(f"/api/entries?token={self.token}")
        self.assertEqual(resp.status_code, 401)

    def test_revoking_a_token(self):
        resp = self.client.delete("/api/tokens/current", headers=self.headers())
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.client.get("/api/entries", headers=self.headers()).status_code, 401)

    def test_no_hardcoded_development_login(self):
        resp = self.client.post("/api/tokens", json={"username": "test_user", "password": "secret123"})
        self.assertEqual(resp.status_code, 401)


class TestEntries(APITestCase):
    def test_create(self):
        resp = self.create("Exhausted but happy after the hike", title="Hike",
                           place="Sintra", tags=["travel", "Portugal"])
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data["title"], "Hike")
        self.assertEqual(data["tags"], ["portugal", "travel"])
        self.assertEqual(data["emotions"], ["tired", "happy"])
        self.assertIn(data["sentiment"], ("positive", "neutral", "negative"))
        self.assertNotIn("user_id", data)

    def test_create_invalid(self):
        bad_bodies = [{"text": ""}, {"text": "   "}, {}, {"text": 5}, {"text": "ok", "date": "nope"},
                      {"text": "ok", "tags": "has/slash"}, {"text": "x" * 10_001}]
        for body in bad_bodies:
            with self.subTest(body=body):
                resp = self.client.post("/api/entries", json=body, headers=self.headers())
                self.assertEqual(resp.status_code, 400)
                self.assertIn("error", resp.get_json())

    def test_body_must_be_a_json_object(self):
        for kwargs in [{"data": "not json", "content_type": "application/json"}, {"json": ["a list"]}]:
            resp = self.client.post("/api/entries", headers=self.headers(), **kwargs)
            self.assertEqual(resp.status_code, 400)

    def test_huge_request_is_rejected(self):
        resp = self.create("x" * 70_000)
        self.assertEqual(resp.status_code, 413)
        self.assertIn("error", resp.get_json())

    def test_get_edit_delete(self):
        entry_id = self.create("Hard day at work").get_json()["id"]

        resp = self.client.get(f"/api/entries/{entry_id}", headers=self.headers())
        self.assertEqual(resp.get_json()["text"], "Hard day at work")

        resp = self.client.patch(f"/api/entries/{entry_id}", headers=self.headers(),
                                 json={"text": "Hard day, but I feel calm now", "tags": ["work"]})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["emotions"], ["calm"])
        self.assertEqual(data["tags"], ["work"])
        self.assertIsNotNone(data["updated_at"])

        resp = self.client.patch(f"/api/entries/{entry_id}", headers=self.headers(), json={"colour": "blue"})
        self.assertEqual(resp.status_code, 400)

        self.assertEqual(self.client.delete(f"/api/entries/{entry_id}", headers=self.headers()).status_code, 204)
        self.assertEqual(self.client.get(f"/api/entries/{entry_id}", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/entries/{entry_id}", headers=self.headers()).status_code, 404)

    def test_out_of_range_numbers_are_handled(self):
        # Larger than SQLite's 64-bit integers; these used to cause a 500.
        huge = 10**20
        self.assertEqual(self.client.get(f"/api/entries/{huge}", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/entries/{huge}", headers=self.headers()).status_code, 404)
        self.assertEqual(self.client.get(f"/api/entries?offset={huge}", headers=self.headers()).status_code, 400)

    def test_users_cannot_touch_each_others_entries(self):
        entry_id = self.create("alice's private thoughts", tags=["secret"]).get_json()["id"]
        bob = self.register_and_get_token("bob")

        self.assertEqual(self.client.get(f"/api/entries/{entry_id}", headers=self.headers(bob)).status_code, 404)
        resp = self.client.patch(f"/api/entries/{entry_id}", headers=self.headers(bob), json={"text": "edited"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.client.delete(f"/api/entries/{entry_id}", headers=self.headers(bob)).status_code, 404)
        self.assertEqual(self.client.get("/api/entries", headers=self.headers(bob)).get_json(), {"entries": []})
        self.assertEqual(self.client.get("/api/tags/secret", headers=self.headers(bob)).status_code, 404)

        resp = self.client.get(f"/api/entries/{entry_id}", headers=self.headers())
        self.assertEqual(resp.get_json()["text"], "alice's private thoughts")

    def test_list_filters(self):
        self.create("Landed in Copenhagen", date="2026-11-01", tags=["copenhagen"])
        self.create("Canal walk in the rain", date="2026-11-02", tags=["copenhagen"])
        self.create("Back to classes", date="2026-11-05", tags=["school"])

        def texts(query):
            resp = self.client.get(f"/api/entries?{query}", headers=self.headers())
            self.assertEqual(resp.status_code, 200)
            return [e["text"] for e in resp.get_json()["entries"]]

        self.assertEqual(texts("tag=copenhagen&order=oldest"), ["Landed in Copenhagen", "Canal walk in the rain"])
        self.assertEqual(texts("q=CANAL"), ["Canal walk in the rain"])
        self.assertEqual(texts("from=2026-11-02&to=2026-11-05"), ["Back to classes", "Canal walk in the rain"])
        self.assertEqual(len(texts("limit=1")), 1)
        self.assertEqual(texts("limit=1&offset=2"), ["Landed in Copenhagen"])

    def test_list_invalid_params(self):
        for query in ["limit=abc", "limit=0", "limit=101", "offset=-1", "order=sideways",
                      "from=2026-02-30", "from=2026-11-05&to=2026-11-01"]:
            with self.subTest(query=query):
                resp = self.client.get(f"/api/entries?{query}", headers=self.headers())
                self.assertEqual(resp.status_code, 400)


class TestReflectionEndpoints(APITestCase):
    def test_stats_for_empty_journal(self):
        data = self.client.get("/api/stats", headers=self.headers()).get_json()
        self.assertEqual(data["total_entries"], 0)
        self.assertEqual(data["current_streak"], 0)
        self.assertEqual(len(data["daily"]), 7)
        self.assertTrue(data["reflection"])

    def test_stats_after_writing(self):
        self.create("Had a wonderful day")
        data = self.client.get("/api/stats", headers=self.headers()).get_json()
        self.assertEqual(data["total_entries"], 1)
        self.assertEqual(data["current_streak"], 1)
        self.assertEqual(data["sentiment_counts"]["positive"], 1)

    def test_tags_and_collection(self):
        self.create("Arrived in Fes", date="2026-10-01", tags=["morocco", "travel"])
        self.create("Leaving tomorrow", date="2026-10-04", tags=["morocco"])
        tags = self.client.get("/api/tags", headers=self.headers()).get_json()["tags"]
        self.assertEqual({t["tag"] for t in tags}, {"morocco", "travel"})

        data = self.client.get("/api/tags/morocco", headers=self.headers()).get_json()
        self.assertEqual(data["total_entries"], 2)
        self.assertEqual(data["days_spanned"], 4)
        self.assertEqual([e["text"] for e in data["entries"]], ["Arrived in Fes", "Leaving tomorrow"])
        self.assertNotIn("user_id", data["entries"][0])

    def test_revisit(self):
        self.assertIsNone(self.client.get("/api/revisit", headers=self.headers()).get_json()["entry"])
        self.create("An older memory", date="2026-01-01")
        data = self.client.get("/api/revisit", headers=self.headers()).get_json()
        self.assertEqual(data["entry"]["text"], "An older memory")
        self.assertIn("ago", data["age"])


class TestErrorsAndHeaders(APITestCase):
    def test_unknown_route_and_wrong_method_return_json(self):
        resp = self.client.get("/api/nope")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.get_json())
        resp = self.client.put("/api/entries", headers=self.headers())
        self.assertEqual(resp.status_code, 405)
        self.assertIn("error", resp.get_json())

    def test_security_headers(self):
        resp = self.client.get("/api/entries", headers=self.headers())
        self.assertEqual(resp.headers["Cache-Control"], "no-store")
        self.assertEqual(resp.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", resp.headers["Content-Security-Policy"])

    def test_unexpected_errors_do_not_leak_details(self):
        from unittest.mock import patch
        with patch("app.journal.storage.list_entries", side_effect=RuntimeError("db path /secret")), \
                self.assertLogs("api.main", level="ERROR"):
            resp = self.client.get("/api/entries", headers=self.headers())
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("secret", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
