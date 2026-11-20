import sqlite3
import unittest
from contextlib import closing

from intake.calibration import CalibrationRegistry
from intake.quality import QualityMark
from intake.recording import read_recording, record
from intake.segments import AffineSegment
from revision.catalog import list_frozen_revisions, select_frozen_revision
from revision.correction import Correction
from revision.freeze import freeze
from tests.fixtures import gap, initialize_station, reading


class TestRecording(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(closing(sqlite3.connect(':memory:')))
        initialize_station(self.db)
        self.registry = CalibrationRegistry(self.db)
        self.registry.register('cal', 2)

    def test_calibration_and_gap(self):
        batch = record(self.db, 'A', 'day', [reading(2, 3, 4), gap(1, 2), reading(0, 1, 3)])
        self.assertEqual(batch.segments, (AffineSegment(0, 1, 5, 5), AffineSegment(2, 3, 6, 6)))
        self.assertEqual(tuple(window.quality for window in batch.windows), (
            QualityMark.VALID, QualityMark.MISSING, QualityMark.VALID,
        ))
        self.assertEqual((batch.windows[0].raw_start, batch.windows[0].calibration_id), (3, 'cal'))
        self.assertEqual(read_recording(self.db, 'A', 'day'), batch)

    def test_unknown_calibration(self):
        accepted = record(self.db, 'A', 'good', [reading(0, 1, 3)])
        with self.assertRaisesRegex(KeyError, 'unregistered'):
            record(self.db, 'A', 'bad', [reading(0, 1, 3), reading(1, 2, 3, calibration_id='unregistered')])
        with self.assertRaises(KeyError):
            read_recording(self.db, 'A', 'bad')
        self.assertEqual(read_recording(self.db, 'A', 'good'), accepted)
        self.registry.register('unregistered', 2)
        retried = record(self.db, 'A', 'bad', [reading(0, 1, 3, calibration_id='unregistered')])
        self.assertEqual(retried.segments, (AffineSegment(0, 1, 5, 5),))

    def test_freeze_initial(self):
        record(self.db, 'A', 'day', [reading(0, 1, 3), gap(1, 2), reading(2, 3, 3)])
        frozen = freeze(self.db, 'A', recording_id='day')
        self.assertEqual((frozen.origin.station_id, frozen.origin.recording_id), ('A', 'day'))
        self.assertIsNone(frozen.origin.parent_revision_id)
        self.assertIsNone(frozen.correction)
        self.assertEqual(frozen.segments, (AffineSegment(0, 1, 5, 5), AffineSegment(2, 3, 5, 5)))
        self.assertEqual(list_frozen_revisions(self.db, 'A'), (frozen,))
        self.assertEqual(select_frozen_revision(self.db, 'A', frozen.revision_id), frozen)

    def test_correction_from_parent(self):
        record(self.db, 'A', 'day', [reading(0, 3, -2, 1)])
        initial = freeze(self.db, 'A', recording_id='day')
        left = Correction(0, 1, (AffineSegment(0, 1, 9, 9),), 'recovered left evidence')
        right = Correction(2, 3, (AffineSegment(2, 3, 8, 8),), 'recovered right evidence')
        first = freeze(self.db, 'A', parent_revision_id=initial.revision_id, correction=left)
        second = freeze(self.db, 'A', parent_revision_id=initial.revision_id, correction=right)
        self.assertEqual(first.segments, (AffineSegment(0, 1, 9, 9), AffineSegment(1, 3, 1, 3)))
        self.assertEqual(second.segments, (AffineSegment(0, 2, 0, 2), AffineSegment(2, 3, 8, 8)))
        self.assertEqual(initial.segments, (AffineSegment(0, 3, 0, 3),))
        self.assertNotEqual(first.revision_id, second.revision_id)
        for revision, correction in ((first, left), (second, right)):
            self.assertEqual(revision.origin.parent_revision_id, initial.revision_id)
            self.assertEqual(revision.origin.recording_id, 'day')
            self.assertEqual(revision.correction, correction)
        self.assertEqual(list_frozen_revisions(self.db, 'A'), (initial, first, second))

    def test_invalid_segments(self):
        invalid_batches = (
            [reading(0, 2), gap(1, 3)],
            [reading(0, 1), reading(1, 2, '1/0')],
            [reading(1, 1)],
            [{**gap(0, 1), 'raw_start': 2}],
        )
        for rows in invalid_batches:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    record(self.db, 'A', 'bad', rows)
                with self.assertRaises(KeyError):
                    read_recording(self.db, 'A', 'bad')

    def test_illegal_correction(self):
        record(self.db, 'A', 'day', [reading(0, 3)])
        parent = freeze(self.db, 'A', recording_id='day')
        valid = Correction(0, 1, (), 'confirmed missing')
        with self.assertRaises(KeyError):
            freeze(self.db, 'A', parent_revision_id='unknown', correction=valid)
        with self.assertRaises(KeyError):
            freeze(self.db, 'B', parent_revision_id=parent.revision_id, correction=valid)
        with self.assertRaises(ValueError):
            freeze(self.db, 'A', recording_id='different', parent_revision_id=parent.revision_id, correction=valid)
        with self.assertRaises(ValueError):
            freeze(self.db, 'A', parent_revision_id=parent.revision_id, correction=Correction(
                0, 3, (AffineSegment(0, 2, 5, 5), AffineSegment(1, 3, 4, 4)), 'conflicting readings',
            ))
        self.assertEqual(list_frozen_revisions(self.db, 'A'), (parent,))

    def test_init_repeat(self):
        accepted = record(self.db, 'A', 'day', [reading(0, 1, 3)])
        frozen = freeze(self.db, 'A', recording_id='day')
        self.db.execute('CREATE TABLE operator_notes (note TEXT NOT NULL)')
        with self.db:
            self.db.execute('INSERT INTO operator_notes VALUES (?)', ('retain the initial run',))
            self.db.execute('UPDATE calibrations SET offset = ? WHERE calibration_id = ?', ('3', 'cal'))
        initialize_station(self.db)
        self.assertEqual(self.registry.resolve('cal').offset, 3)
        self.assertEqual(self.db.execute('SELECT note FROM operator_notes').fetchall(), [('retain the initial run',)])
        self.assertEqual(read_recording(self.db, 'A', 'day'), accepted)
        self.assertEqual(select_frozen_revision(self.db, 'A', frozen.revision_id), frozen)
        new_batch = record(self.db, 'A', 'later', [reading(0, 1, 3)])
        self.assertEqual(new_batch.segments, (AffineSegment(0, 1, 6, 6),))
