import os
import shutil
import tempfile
import unittest
from unittest.mock import patch


class TempDataTestCase(unittest.TestCase):
    """Gives each test its own empty data directory (database, secret key and
    CLI session), so tests never touch real journal data or each other."""

    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        env = patch.dict(os.environ, {"CALMCONNECT_DATA_DIR": self.data_dir})
        env.start()
        os.environ.pop("DB_PATH", None)
        os.environ.pop("CALMCONNECT_SECRET_KEY", None)
        self.addCleanup(env.stop)
        self.addCleanup(shutil.rmtree, self.data_dir, ignore_errors=True)

    def make_user(self, username="alice", password="correct horse"):
        from app import auth
        return auth.register(username, password)
