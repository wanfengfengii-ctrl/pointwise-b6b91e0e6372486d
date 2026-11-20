import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import read
from archive.publish import initialize_archive
from intake.segments import AffineSegment
from issue.receipts import issue
from review.assemble import sign
from revision.correction import Correction
from revision.freeze import freeze
from tests.fixtures import archive_counts, check_result, gap, independent_piece, issue_fixture, reading


class TestReview(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.archive = self.root / 'review.sqlite'
        with closing(sqlite3.connect(self.archive)) as db:
            initialize_archive(db)

    def _offline_pair(self):
        source_a, source_b = self.root / 'A.sqlite', self.root / 'B.sqlite'
        with closing(sqlite3.connect(source_a)) as db:
            left = issue_fixture(db, 'A', [reading(0, 1), gap(1, 2), reading(2, 3)])
        with closing(sqlite3.connect(source_b)) as db:
            right = issue_fixture(db, 'B', [reading(3, 5)])
        left_offline = self.root / 'A.offline'
        source_a.rename(left_offline)
        source_b.rename(self.root / 'B.offline')
        self.assertFalse(source_a.exists())
        self.assertFalse(source_b.exists())
        return left, right, left_offline

    def test_offline_gap(self):
        left, right, _ = self._offline_pair()
        with closing(sqlite3.connect(self.archive)) as db:
            signed = sign(db, left.piece_bytes, right.piece_bytes, 4, -4, 1)
            check_result(self, signed, 1, [(-4, -1)])
            self.assertEqual(signed, read(db, signed.report.report_id))
        self.assertEqual([parent.piece_id for parent in signed.parents], [left.piece_id, right.piece_id])
        self.assertEqual([parent.station_id for parent in signed.parents], ['A', 'B'])

    def _successive_reports(self):
        left, right, left_offline = self._offline_pair()
        with closing(sqlite3.connect(self.archive)) as db:
            old = sign(db, left.piece_bytes, right.piece_bytes, 4, -4, 1)
        with closing(sqlite3.connect(left_offline)) as source:
            revision = freeze(source, 'A', parent_revision_id=left.revision_id, correction=Correction(
                1, 2, (AffineSegment(1, 2, 5, 5),), 'verified backup reading',
            ))
            replacement = issue(source, 'A', revision.revision_id, 4)
        with closing(sqlite3.connect(self.archive)) as db:
            new = sign(db, replacement.piece_bytes, right.piece_bytes, 4, -4, 1)
        return old, new, left, replacement, right

    def test_old_report_after_correction(self):
        old, new, left, replacement, right = self._successive_reports()
        with closing(sqlite3.connect(self.archive)) as db:
            archived_old = read(db, old.report.report_id)
            archived_new = read(db, new.report.report_id)
        check_result(self, archived_old, 1, [(-4, -1)])
        check_result(self, archived_new, 2, [(-3, -2)])
        for archived, expected_left in ((archived_old, left), (archived_new, replacement)):
            self.assertEqual(
                [(parent.station_id, parent.revision_id, parent.piece_id) for parent in archived.parents],
                [(receipt.station_id, receipt.revision_id, receipt.piece_id) for receipt in (expected_left, right)],
            )
        self.assertNotEqual(old.report.report_id, new.report.report_id)

    def test_archive_init_repeat(self):
        old, new, _, _, _ = self._successive_reports()
        with closing(sqlite3.connect(self.archive)) as db:
            db.execute('CREATE TABLE shift_notes (note TEXT NOT NULL)')
            with db:
                db.execute('INSERT INTO shift_notes VALUES (?)', ('compare the original evidence',))
            initialize_archive(db)
            initialize_archive(db)
        with closing(sqlite3.connect(self.archive)) as db:
            self.assertEqual(archive_counts(db), (2, 4, 2))
            self.assertEqual(db.execute('SELECT note FROM shift_notes').fetchall(), [('compare the original evidence',)])
            for expected in (old, new):
                self.assertEqual(read(db, expected.report.report_id), expected)

    def test_unknown_report(self):
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaisesRegex(KeyError, 'unknown report'):
                read(db, 'missing')

    def test_independent_piece(self):
        gapped = independent_piece('A', 'a-gap', [(0, 1, 0, 5), (2, 3, 0, 5)])
        complete = independent_piece('A', 'a-complete', [(0, 3, 0, 5)])
        right = independent_piece('B', 'b', [(3, 5, 0, 5)])
        with closing(sqlite3.connect(self.archive)) as db:
            first = sign(db, gapped, right, 4, -4, 1)
            second = sign(db, complete, right, 4, -4, 1)
            check_result(self, first, 1, [(-4, -1)])
            check_result(self, second, 2, [(-3, -2)])
            self.assertEqual([parent.piece_id for parent in first.parents], ['a-gap', 'b'])
            self.assertEqual([parent.piece_id for parent in second.parents], ['a-complete', 'b'])

    def test_split_maxima(self):
        left = independent_piece('A', 'a', [(0, 1, 0, 5), (3, 4, 0, 5)])
        right = independent_piece('B', 'b', [(0, 1, 0, 5)])
        with closing(sqlite3.connect(self.archive)) as db:
            signed = sign(db, left, right, 4, 0, 3)
            archived = read(db, signed.report.report_id)
        check_result(self, archived, 1, [(0, 0), (3, 3)])

    def test_zero_overlap(self):
        left = independent_piece('A', 'a', [(0, 1, 0, 5)])
        right = independent_piece('B', 'b', [(0, 1, 0, 5)])
        empty = independent_piece('A', 'a-empty', [])
        with closing(sqlite3.connect(self.archive)) as db:
            check_result(self, sign(db, left, right, 5, -2, 3), 0, [(-2, 3)])
            check_result(self, sign(db, empty, right, 4, -2, 3), 0, [(-2, 3)])

    def test_rational_crossing(self):
        left = independent_piece('A', 'a', [(0, 2, 1, 0)])
        right = independent_piece('B', 'b', [(0, 2, 0, 2)])
        descending = independent_piece('A', 'a-down', [(0, 2, -1, 2)])
        with closing(sqlite3.connect(self.archive)) as db:
            for threshold, expected in (('1/2', '3/2'), (1, 1), (2, 0)):
                with self.subTest(threshold=threshold):
                    signed = sign(db, left, right, threshold, 0, 0)
                    check_result(self, read(db, signed.report.report_id), expected, [(0, 0)])
                    check_result(self, sign(db, descending, right, threshold, 0, 0), expected, [(0, 0)])

    def test_incomplete_piece(self):
        left = independent_piece('A', 'a', [(0, 1, 0, 5)])
        right = independent_piece('B', 'b', [(0, 1, 0, 5)])
        incomplete = json.loads(left)
        del incomplete['piece_id']
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaises(ValueError):
                sign(db, json.dumps(incomplete).encode(), right, 4, 0, 0)
            self.assertEqual(archive_counts(db), (0, 0, 0))
            signed = sign(db, left, right, 4, 0, 0)
            self.assertEqual(signed.parents[0].piece_id, 'a')

    def test_invalid_parameters(self):
        left = independent_piece('A', 'a', [(0, 1, 0, 5)])
        right = independent_piece('B', 'b', [(0, 1, 0, 5)])
        with closing(sqlite3.connect(self.archive)) as db:
            for parameters in (('1/0', 0, 1), (4, 1, 0), (4, 0.5, 1), (True, 0, 1)):
                with self.subTest(parameters=parameters):
                    with self.assertRaises(ValueError):
                        sign(db, left, right, *parameters)
            self.assertEqual(archive_counts(db), (0, 0, 0))

    def test_invalid_body_and_station_order(self):
        left = independent_piece('A', 'a', [(0, 1, 0, 5)])
        overlapping = independent_piece('B', 'bad-b', [(0, 2, 0, 5), (1, 3, 0, 5)])
        right = independent_piece('B', 'b', [(3, 4, 0, 5)])
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaises(ValueError):
                sign(db, left, overlapping, 4, -5, 5)
            with self.assertRaises(ValueError):
                sign(db, left, left, 4, -5, 5)
            self.assertEqual(archive_counts(db), (0, 0, 0))
            forward = sign(db, left, right, 4, -5, 5)
            reverse = sign(db, right, left, 4, -5, 5)
            check_result(self, forward, 1, [(-3, -3)])
            check_result(self, reverse, 1, [(3, 3)])
            self.assertEqual([parent.piece_id for parent in reverse.parents], ['b', 'a'])
