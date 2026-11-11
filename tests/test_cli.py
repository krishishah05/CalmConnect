import io
import os
import stat
import sys
import unittest
from unittest.mock import patch

from rich.console import Console

import cli.main as cli
from app import journal
from tests.support import TempDataTestCase


class CliTestCase(TempDataTestCase):
    def setUp(self):
        super().setUp()
        self.output = io.StringIO()
        console = patch.object(cli, "console", Console(file=self.output, width=120, color_system=None))
        console.start()
        self.addCleanup(console.stop)

    def run_cli(self, *argv, password="correct horse", stdin=None, answer=None):
        self.output.seek(0)
        self.output.truncate()
        with patch("getpass.getpass", return_value=password), \
                patch("builtins.input", return_value=answer or ""), \
                patch("sys.stdin", io.StringIO(stdin or "")):
            code = cli.main(list(argv))
        return code, self.output.getvalue()


class TestCliAccounts(CliTestCase):
    def test_commands_require_login(self):
        for argv in [["journal", "hi"], ["history"], ["show", "1"], ["stats"], ["reflect"], ["tags"]]:
            with self.subTest(argv=argv):
                code, out = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("not logged in", out)

    def test_cannot_read_another_users_journal_by_name(self):
        # The old CLI took a username argument and trusted it.
        self.run_cli("register", "alice")
        self.run_cli("journal", "alice's secret")
        self.run_cli("logout")
        self.run_cli("register", "bob")
        code, out = self.run_cli("history")
        self.assertNotIn("secret", out)
        code, out = self.run_cli("show", "1")
        self.assertEqual(code, 1)

    def test_session_file_is_private_and_logout_revokes_it(self):
        self.run_cli("register", "alice")
        path = cli._session_file()
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        token = path.read_text()
        self.run_cli("logout")
        self.assertFalse(path.exists())
        from app import auth
        self.assertIsNone(auth.user_for_token(token))

    def test_wrong_password(self):
        self.run_cli("register", "alice")
        self.run_cli("logout")
        code, out = self.run_cli("login", "alice", password="wrong password")
        self.assertEqual(code, 1)
        self.assertIn("Incorrect", out)

    def test_mismatched_password_confirmation(self):
        with patch("getpass.getpass", side_effect=["correct horse", "different one"]):
            code = cli.main(["register", "alice"])
        self.assertEqual(code, 1)


class TestCliJournal(CliTestCase):
    def setUp(self):
        super().setUp()
        self.run_cli("register", "alice")

    def test_journal_history_show_edit_delete(self):
        code, out = self.run_cli("journal", "Got lost in Lisbon and loved it. Exhausted now.",
                                 "--title", "Lisbon", "--tags", "travel,lisbon", "--place", "Lisbon")
        self.assertEqual(code, 0)
        self.assertIn("Saved entry #1", out)
        self.assertIn("tired", out)

        code, out = self.run_cli("history", "--tag", "lisbon")
        self.assertIn("Lisbon", out)

        code, out = self.run_cli("show", "1")
        self.assertIn("Got lost in Lisbon", out)

        with patch.dict(os.environ, {"VISUAL": "", "EDITOR": ""}):
            code, out = self.run_cli("edit", "1", stdin="Rewritten from the train home.")
        self.assertEqual(code, 0)
        self.assertEqual(journal.get_entry(1, 1)["text"], "Rewritten from the train home.")

        code, out = self.run_cli("edit", "1", "--tags", "")
        self.assertEqual(journal.get_entry(1, 1)["tags"], [])

        code, out = self.run_cli("delete", "1", answer="n")
        self.assertIn("Kept it", out)
        self.assertIsNotNone(journal.get_entry(1, 1))
        code, out = self.run_cli("delete", "1", answer="y")
        self.assertIsNone(journal.get_entry(1, 1))

    def test_journal_reads_piped_text(self):
        code, out = self.run_cli("journal", "--prompt", stdin="Paragraph one.\n\nParagraph two.\n")
        self.assertEqual(code, 0)
        entry = journal.get_entry(1, 1)
        self.assertEqual(entry["text"], "Paragraph one.\n\nParagraph two.")
        self.assertIn(entry["prompt"], journal.PROMPTS)

    def test_edit_with_editor(self):
        journal.create_entry(1, "typo hre")
        # Stands in for vim/nano: fixes the typo in the file it's given.
        fake_editor = (f'"{sys.executable}" -c "import sys, pathlib; p = pathlib.Path(sys.argv[1]); '
                       f"p.write_text(p.read_text().replace('hre', 'here'))\"")
        with patch.dict(os.environ, {"VISUAL": fake_editor}):
            code, out = self.run_cli("edit", "1")
        self.assertEqual(code, 0, out)
        self.assertEqual(journal.get_entry(1, 1)["text"], "typo here")

    def test_square_brackets_in_entries_are_printed_literally(self):
        # Rich treats [tags] as formatting; an entry containing "[/b]" used to crash history.
        self.run_cli("journal", "Todo [/] and [red]this[/red]", "--title", "Notes [/b]", "--place", "Room [b]2")
        for argv in [("history",), ("show", "1"), ("reflect",)]:
            code, out = self.run_cli(*argv)
            self.assertEqual(code, 0, out)
        code, out = self.run_cli("show", "1")
        self.assertIn("Todo [/] and [red]this[/red]", out)
        self.assertIn("Notes [/b]", out)
        self.assertIn("Room [b]2", out)
        code, out = self.run_cli("journal", "x", "--tags", "[bad]")
        self.assertIn("'[bad]' isn't a valid tag", out)

    def test_friendly_errors(self):
        self.assertEqual(self.run_cli("journal", "   ")[0], 1)
        code, out = self.run_cli("journal", "hi", "--date", "2099-01-01")
        self.assertIn("future", out)
        code, out = self.run_cli("show", "42")
        self.assertIn("No entry #42", out)
        code, out = self.run_cli("history", "--from", "nope")
        self.assertEqual(code, 1)

    def test_stats_reflect_and_tags(self):
        journal.create_entry(1, "Nervous on the first day", entry_date="2026-10-01", tags="morocco")
        journal.create_entry(1, "Grateful for every minute", entry_date="2026-10-03", tags="morocco")
        journal.create_entry(1, "Calm evening at home")

        code, out = self.run_cli("stats")
        self.assertEqual(code, 0)
        self.assertIn("current streak 1", out)

        code, out = self.run_cli("reflect")
        self.assertIn("You wrote on 1 of the last 7 days", out)
        self.assertIn("Looking back", out)

        code, out = self.run_cli("tags")
        self.assertIn("#morocco", out)
        code, out = self.run_cli("tags", "morocco")
        self.assertIn("Nervous on the first day", out)
        self.assertLess(out.index("Nervous"), out.index("Grateful"))


if __name__ == "__main__":
    unittest.main()
