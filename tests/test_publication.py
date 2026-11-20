import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import read
from archive.publish import initialize_archive
from review.assemble import sign
from tests.fixtures import archive_counts, check_result, independent_piece


class TestPublication(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.archive = self.root / 'review.sqlite'
        self.left = independent_piece('A', 'a', [(0, 2, 0, 5)])
        self.right = independent_piece('B', 'b', [(0, 2, 0, 5)])
        with closing(sqlite3.connect(self.archive)) as db:
            initialize_archive(db)
            self.old = sign(db, self.left, self.right, 4, 0, 0)
            self._install_commit_failure(db)

    def _install_commit_failure(self, db):
        # The trigger writes a deferred foreign-key violation during receipt
        # insertion. SQLite detects it only when the real transaction commits.
        db.execute('CREATE TABLE commit_permissions (id INTEGER PRIMARY KEY)')
        db.execute('''
            CREATE TABLE commit_gate (
                report_id TEXT NOT NULL REFERENCES signed_reports(report_id),
                permission INTEGER NOT NULL REFERENCES commit_permissions(id) DEFERRABLE INITIALLY DEFERRED
            )
        ''')
        db.execute('''
            CREATE TRIGGER reject_report_commit AFTER INSERT ON publication_receipts
            BEGIN
                INSERT INTO commit_gate (report_id, permission) VALUES (NEW.report_id, 1);
            END
        ''')

    def _check_unchanged(self, db):
        self.assertEqual(archive_counts(db), (1, 2, 1))
        self.assertEqual(db.execute('SELECT report_id FROM commit_gate').fetchall(), [])
        self.assertEqual(read(db, self.old.report.report_id), self.old)

    def test_failed_commit(self):
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                sign(db, self.left, self.right, 4, -1, 1)
            self.assertFalse(db.in_transaction)
            self._check_unchanged(db)
        with closing(sqlite3.connect(self.archive)) as db:
            self._check_unchanged(db)

    def test_retry_after_rollback(self):
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                sign(db, self.left, self.right, 3, -1, 1)
        with closing(sqlite3.connect(self.archive)) as db:
            self._check_unchanged(db)
            db.execute('DROP TRIGGER reject_report_commit')
            new = sign(db, self.left, self.right, 3, -1, 1)
        with closing(sqlite3.connect(self.archive)) as db:
            self.assertEqual(archive_counts(db), (2, 4, 2))
            self.assertEqual(read(db, self.old.report.report_id), self.old)
            self.assertEqual(read(db, new.report.report_id), new)
            self.assertEqual(new.receipt.report_id, new.report.report_id)
            self.assertEqual([parent.piece_id for parent in new.parents], ['a', 'b'])
            check_result(self, new, 2, [(0, 0)])

    def test_cli_failed_commit(self):
        left_path, right_path = self.root / 'a.json', self.root / 'b.json'
        left_path.write_bytes(self.left)
        right_path.write_bytes(self.right)
        entry = Path(__file__).resolve().parents[1] / 'demo.py'
        result = subprocess.run([
            sys.executable, '-B', str(entry), 'sign', str(self.archive), str(left_path), str(right_path),
            '--threshold=4', '--lag-min=-1', '--lag-max=1',
        ], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FOREIGN KEY', result.stderr)
        self.assertEqual(result.stdout, '')
        with closing(sqlite3.connect(self.archive)) as db:
            self._check_unchanged(db)
