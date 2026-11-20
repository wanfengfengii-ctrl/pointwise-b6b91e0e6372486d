import sqlite3
import unittest
from contextlib import closing

from archive.publish import initialize_archive
from intake.segments import AffineSegment
from issue.codec import decode_piece
from issue.receipts import issue
from issue.store import StationPieceStore
from review.assemble import sign
from revision.correction import Correction
from revision.freeze import freeze
from tests.fixtures import check_result, gap, independent_piece, prepare_station, reading


class TestIssuance(unittest.TestCase):
    def setUp(self):
        self.source = self.enterContext(closing(sqlite3.connect(':memory:')))

    def test_strict_exposure(self):
        revision = prepare_station(self.source, 'A', [reading(0, 2, 0, 2)])
        first = issue(self.source, 'A', revision.revision_id, 1)
        second = issue(self.source, 'A', revision.revision_id, 2)
        self.assertEqual((first.exposure, second.exposure), (1, 0))
        self.assertEqual(first.revision_id, revision.revision_id)
        self.assertEqual(decode_piece(first.piece_bytes).body, decode_piece(second.piece_bytes).body)

    def test_missing_revision(self):
        revision = prepare_station(self.source, 'A', [reading(0, 1)])
        receipt = issue(self.source, 'A', revision.revision_id, 4)
        with self.assertRaises(KeyError):
            issue(self.source, 'A', 'unknown', 4)
        with self.assertRaises(KeyError):
            issue(self.source, 'B', revision.revision_id, 4)
        self.assertEqual(self.source.execute('SELECT piece_id, receipt_id FROM station_issues').fetchall(), [
            (receipt.piece_id, receipt.receipt_id),
        ])

    def test_equal_plateau(self):
        revision = prepare_station(self.source, 'A', [reading(0, 2, 2)])
        hot = issue(self.source, 'A', revision.revision_id, 1)
        equal = issue(self.source, 'A', revision.revision_id, 2)
        self.assertEqual((hot.exposure, equal.exposure), (2, 0))
        self.assertEqual((hot.revision_id, equal.revision_id), (revision.revision_id, revision.revision_id))

    def test_gap_payload(self):
        original = prepare_station(self.source, 'A', [reading(0, 1, 3), gap(1, 2), reading(2, 3, 3)], offset=2)
        corrected = freeze(self.source, 'A', parent_revision_id=original.revision_id, correction=Correction(
            1, 2, (AffineSegment(1, 2, 5, 5),), 'restored calibrated backup',
        ))
        gapped = issue(self.source, 'A', original.revision_id, 4)
        continuous = issue(self.source, 'A', corrected.revision_id, 4)
        self.assertEqual((gapped.exposure, continuous.exposure), (2, 3))
        for receipt in (gapped, continuous):
            self.assertEqual(StationPieceStore(self.source).load_issue(receipt.piece_id), receipt)
        self.source.close()
        for receipt, revision in ((gapped, original), (continuous, corrected)):
            piece = decode_piece(receipt.piece_bytes)
            self.assertEqual((piece.station_id, piece.revision_id, piece.piece_id), ('A', revision.revision_id, receipt.piece_id))
            self.assertNotIn(b'restored calibrated backup', receipt.piece_bytes)
            self.assertNotIn(b'calibration_id', receipt.piece_bytes)
        center = self.enterContext(closing(sqlite3.connect(':memory:')))
        initialize_archive(center)
        for index, expected_gap in enumerate((1, 0, 1)):
            probe = independent_piece('B', f'probe-{index}', [(index, index + 1, 0, 8)])
            for receipt, expected in ((gapped, expected_gap), (continuous, 1)):
                with self.subTest(index=index, piece_id=receipt.piece_id):
                    check_result(self, sign(center, receipt.piece_bytes, probe, '9/2', 0, 0), expected, [(0, 0)])
                    check_result(self, sign(center, receipt.piece_bytes, probe, 5, 0, 0), 0, [(0, 0)])
