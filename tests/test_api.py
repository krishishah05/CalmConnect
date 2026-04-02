import os
import tempfile
import unittest
from unittest.mock import patch


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_api.db")
        self._patch = patch.dict("os.environ", {"DB_PATH": self.db_path})
        self._patch.start()

        from api.main import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self._patch.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _submit(self, text="Feeling okay", token="secret123", user_id="test_user"):
        return self.client.post("/submit", json={
            "user_id": user_id,
            "token": token,
            "text": text,
        })

    # --- /submit ---

    def test_submit_valid(self):
        resp = self._submit("I feel great today")
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertIn("mood", data)
        self.assertIn("polarity", data)
        self.assertIn("emotions", data)

    def test_submit_unauthorized(self):
        resp = self._submit(token="wrong_token")
        self.assertEqual(resp.status_code, 401)

    def test_submit_missing_text(self):
        resp = self.client.post("/submit", json={
            "user_id": "test_user",
            "token": "secret123",
            "text": "",
        })
        self.assertEqual(resp.status_code, 400)

    def test_submit_invalid_json(self):
        resp = self.client.post("/submit", data="not json",
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_submit_returns_correct_user(self):
        resp = self._submit("good morning")
        self.assertEqual(resp.get_json()["user_id"], "test_user")

    # --- /logs ---

    def test_get_logs_empty(self):
        resp = self.client.get("/logs/test_user?token=secret123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [])

    def test_get_logs_after_submit(self):
        self._submit("Hard day at work")
        resp = self.client.get("/logs/test_user?token=secret123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()), 1)

    def test_get_logs_unauthorized(self):
        resp = self.client.get("/logs/test_user?token=bad")
        self.assertEqual(resp.status_code, 401)

    def test_get_logs_limit(self):
        for i in range(4):
            self._submit(f"Entry number {i}")
        resp = self.client.get("/logs/test_user?token=secret123&limit=2")
        self.assertEqual(len(resp.get_json()), 2)

    # --- /stats ---

    def test_stats_structure(self):
        self._submit("Had a wonderful day")
        resp = self.client.get("/stats/test_user?token=secret123")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("weekly", data)
        self.assertIn("streak", data)
        self.assertIn("entries", data["weekly"])
        self.assertIn("mood_counts", data["weekly"])

    def test_stats_unauthorized(self):
        resp = self.client.get("/stats/test_user?token=nope")
        self.assertEqual(resp.status_code, 401)

    def test_stats_empty_user(self):
        resp = self.client.get("/stats/test_user?token=secret123")
        data = resp.get_json()
        self.assertEqual(data["weekly"]["entries"], 0)
        self.assertEqual(data["streak"], 0)


if __name__ == "__main__":
    unittest.main()
