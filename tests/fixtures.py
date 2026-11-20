import json
from fractions import Fraction

from intake.calibration import CalibrationRegistry
from intake.recording import record
from intake.store import RecordingStore
from issue.receipts import issue
from issue.store import StationPieceStore
from revision.freeze import freeze
from revision.snapshots import SnapshotStore


def initialize_station(db):
    CalibrationRegistry(db).initialize()
    RecordingStore(db).initialize()
    SnapshotStore(db).initialize()
    StationPieceStore(db).initialize()


def reading(start, end, raw_start=5, raw_end=None, calibration_id='cal'):
    return {
        'start': start, 'end': end, 'quality': 'valid', 'calibration_id': calibration_id,
        'raw_start': raw_start, 'raw_end': raw_start if raw_end is None else raw_end,
    }


def gap(start, end):
    return {'start': start, 'end': end, 'quality': 'missing'}


def prepare_station(db, station_id, rows, offset=0):
    initialize_station(db)
    CalibrationRegistry(db).register('cal', offset)
    batch = record(db, station_id, 'day', rows)
    return freeze(db, station_id, recording_id=batch.recording_id)


def issue_fixture(db, station_id, rows, local_threshold=4):
    revision = prepare_station(db, station_id, rows)
    return issue(db, station_id, revision.revision_id, local_threshold)


def independent_piece(station_id, piece_id, affine_rows):
    # A separately prepared V1 transfer, without the station issuer or encoder.
    envelope = {
        'version': 1,
        'station_id': station_id,
        'piece_id': piece_id,
        'revision_id': 'independent-' + piece_id,
        'body': {'affine': [[str(value) for value in row] for row in affine_rows]},
    }
    return json.dumps(envelope).encode('utf-8')


def check_result(test, published, duration, ranges):
    test.assertEqual(published.report.duration, Fraction(duration))
    test.assertEqual(published.report.optimal_lags, tuple((Fraction(a), Fraction(b)) for a, b in ranges))


def archive_counts(db):
    tables = ('signed_reports', 'report_parents', 'publication_receipts')
    return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables)
