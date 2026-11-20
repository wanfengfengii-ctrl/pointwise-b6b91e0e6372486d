import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import read, read_stop
from archive.publish import PublishedReport, initialize_archive
from intake.calibration import CalibrationRegistry
from intake.recording import record
from intake.segments import AffineSegment
from intake.store import RecordingStore
from issue.codec import decode_stop_piece
from issue.receipts import IssueReceipt, issue, issue_stop
from issue.store import StationPieceStore
from review.assemble import sign, sign_stop
from revision.correction import Correction
from revision.freeze import freeze
from revision.snapshots import SnapshotStore
from stop_examples import SOURCES
from tests.fixtures import prepare_station


SAMPLES = Path(__file__).resolve().parent / 'samples'

STOP_BATCH_ID = 'coil-stop-01'
STOP_LEFT_COMMANDS = (('a0', 0), ('a1', 1))
STOP_RIGHT_COMMANDS = (('b0', 0),)
STOP_REQUEST = {'threshold': 5, 'dwell': 1, 'tolerance': 1, 'lag_min': 0, 'lag_max': 0}


def _prepare_station(source: Path, sample_path: Path) -> IssueReceipt:
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    with closing(sqlite3.connect(source)) as db:
        calibration = CalibrationRegistry(db)
        calibration.initialize()
        RecordingStore(db).initialize()
        SnapshotStore(db).initialize()
        StationPieceStore(db).initialize()
        calibration.register(sample['calibration_id'], sample['offset'])
        batch = record(db, sample['station_id'], sample['recording_id'], sample['rows'])
        revision = freeze(db, batch.station_id, recording_id=batch.recording_id)
        return issue(db, batch.station_id, revision.revision_id, '4')


def _result(publication: PublishedReport) -> dict:
    return {
        'duration': str(publication.report.duration),
        'optimal_lags': [[str(low), str(high)] for low, high in publication.report.optimal_lags],
    }


def _report_json(publication: PublishedReport) -> dict:
    report = publication.report
    return {
        'report_id': report.report_id,
        'threshold': str(report.threshold),
        'lag_window': [str(report.lag_min), str(report.lag_max)],
        **_result(publication),
        'parents': [asdict(parent) for parent in publication.parents],
        'receipt': asdict(publication.receipt),
    }


def _parent_ids(publication: PublishedReport) -> list[str]:
    return [parent.piece_id for parent in publication.parents]


def _stop_summary(result: dict) -> dict:
    return {
        'max_pairs': result['max_pairs'],
        'optimal_lags': [[str(low), str(high)] for low, high in result['optimal_lags']],
    }


def _stop_report_json(result: dict) -> dict:
    return {
        'report_id': result['report_id'],
        'batch_id': result['batch_id'],
        'threshold': str(result['threshold']),
        'dwell': str(result['dwell']),
        'tolerance': str(result['tolerance']),
        'lag_window': [str(result['lag_min']), str(result['lag_max'])],
        **_stop_summary(result),
        'eligible_commands': [
            [[command_id, str(moment)] for command_id, moment in side]
            for side in result['eligible_commands']
        ],
        'parents': [asdict(parent) for parent in result['parents']],
        'receipt': asdict(result['receipt']),
    }


def run_stop_demo(root: Path) -> None:
    source_a, source_b = root / 'stop-A.sqlite', root / 'stop-B.sqlite'
    with closing(sqlite3.connect(source_a)) as db:
        left_revision = prepare_station(db, 'A', SOURCES['steady']['rows'])
        left_piece = issue_stop(db, 'A', left_revision.revision_id, STOP_BATCH_ID, STOP_LEFT_COMMANDS)
    with closing(sqlite3.connect(source_b)) as db:
        right_revision = prepare_station(db, 'B', SOURCES['missing']['rows'])
        right_piece = issue_stop(db, 'B', right_revision.revision_id, STOP_BATCH_ID, STOP_RIGHT_COMMANDS)
    left_piece_id = decode_stop_piece(left_piece).piece_id
    right_piece_id = decode_stop_piece(right_piece).piece_id
    source_a_offline, source_b_offline = root / 'stop-A.closed', root / 'stop-B.closed'
    source_a.rename(source_a_offline)
    source_b.rename(source_b_offline)
    archive = root / 'stop-archive.sqlite'
    with closing(sqlite3.connect(archive)) as db:
        initialize_archive(db)
        old = sign_stop(db, left_piece, right_piece, **STOP_REQUEST)
    with closing(sqlite3.connect(source_b_offline)) as db:
        corrected = freeze(db, 'B', parent_revision_id=right_revision.revision_id, correction=Correction(
            Fraction(1, 2), Fraction(3, 4),
            (AffineSegment(Fraction(1, 2), Fraction(3, 4), 5, 5),),
            '恢复一段恒温五度的备用记录',
        ))
        corrected_piece = issue_stop(db, 'B', corrected.revision_id, STOP_BATCH_ID, STOP_RIGHT_COMMANDS)
    corrected_piece_id = decode_stop_piece(corrected_piece).piece_id
    with closing(sqlite3.connect(archive)) as db:
        current = sign_stop(db, left_piece, corrected_piece, **STOP_REQUEST)
    with closing(sqlite3.connect(archive)) as db:
        old_copy = read_stop(db, old['report_id'])
        current_copy = read_stop(db, current['report_id'])

    expected_old = {'max_pairs': 0, 'optimal_lags': [['0', '0']]}
    expected_new = {'max_pairs': 1, 'optimal_lags': [['0', '0']]}
    if _stop_summary(old) != expected_old or _stop_summary(current) != expected_new:
        raise AssertionError('unexpected stop confirmation result')
    if old_copy != old or current_copy != current:
        raise AssertionError('archive changed signed stop content on reopening')
    if old['eligible_commands'] != ((('a0', Fraction(0)), ('a1', Fraction(1))), ()):
        raise AssertionError('unexpected original eligible commands')
    if current['eligible_commands'][1] != (('b0', Fraction(0)),):
        raise AssertionError('unexpected corrected eligible commands')
    if [parent.piece_id for parent in old_copy['parents']] != [left_piece_id, right_piece_id]:
        raise AssertionError('archive stop parents differ from the issued pieces')
    if [parent.piece_id for parent in current_copy['parents']] != [left_piece_id, corrected_piece_id]:
        raise AssertionError('archive stop parents differ from the issued pieces')

    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'stop-confirm',
        'input': {
            'batch_id': STOP_BATCH_ID,
            'left_commands': [[command_id, str(Fraction(moment))] for command_id, moment in STOP_LEFT_COMMANDS],
            'right_commands': [[command_id, str(Fraction(moment))] for command_id, moment in STOP_RIGHT_COMMANDS],
            'request': {name: str(value) for name, value in STOP_REQUEST.items()},
            'piece_ids': [left_piece_id, right_piece_id],
            'source_paths_available': [source_a.exists(), source_b.exists()],
        },
        'expected': expected_old,
        'actual': _stop_summary(old),
        'downstream_expected': expected_new,
        'downstream_actual': _stop_summary(current),
        'code_paths': ['issue/receipts.py', 'review/stop.py', 'archive/publish.py', 'archive/export.py'],
        'oracle': 'The right command dwell window [0,1) crosses the missing span [1/2,3/4) until the correction restores constant temperature 5 there.',
    }, sort_keys=True))
    print(json.dumps({'stop_original': _stop_report_json(old_copy), 'stop_corrected': _stop_report_json(current_copy)}, sort_keys=True))


def run_demo() -> None:
    with TemporaryDirectory(prefix='furnace-review-') as directory:
        root = Path(directory)
        source_a, source_b = root / 'A.sqlite', root / 'B.sqlite'
        source_a_offline, source_b_offline = root / 'A.closed', root / 'B.closed'
        archive = root / 'archive.sqlite'
        left = _prepare_station(source_a, SAMPLES / 'station-a.json')
        right = _prepare_station(source_b, SAMPLES / 'station-b.json')
        a_piece, b_piece = root / 'A.json', root / 'B.json'
        a_piece.write_bytes(left.piece_bytes)
        b_piece.write_bytes(right.piece_bytes)
        source_a.rename(source_a_offline)
        source_b.rename(source_b_offline)
        with closing(sqlite3.connect(archive)) as db:
            initialize_archive(db)
            old = sign(db, a_piece.read_bytes(), b_piece.read_bytes(), '4', '-4', '1')

        with closing(sqlite3.connect(source_a_offline)) as db:
            correction = Correction(1, 2, (AffineSegment(1, 2, 5, 5),), '恢复一段有依据的备用记录')
            revision = freeze(db, 'A', parent_revision_id=left.revision_id, correction=correction)
            corrected = issue(db, 'A', revision.revision_id, '4')
        corrected_piece = root / 'A-corrected.json'
        corrected_piece.write_bytes(corrected.piece_bytes)
        with closing(sqlite3.connect(archive)) as db:
            current = sign(db, corrected_piece.read_bytes(), b_piece.read_bytes(), '4', '-4', '1')
        with closing(sqlite3.connect(archive)) as db:
            old_copy = read(db, old.report.report_id)
            current_copy = read(db, current.report.report_id)

        expected_old = {'duration': '1', 'optimal_lags': [['-4', '-1']]}
        expected_new = {'duration': '2', 'optimal_lags': [['-3', '-2']]}
        expected_parents = [left.piece_id, right.piece_id]
        if (left.exposure, right.exposure, corrected.exposure) != (2, 2, 3):
            raise AssertionError('unexpected local exposure')
        if _result(old) != expected_old or _result(current) != expected_new:
            raise AssertionError('unexpected common heat result')
        if old_copy != old or current_copy != current:
            raise AssertionError('archive changed signed content on reopening')
        if _parent_ids(old_copy) != expected_parents or _parent_ids(current_copy) != [corrected.piece_id, right.piece_id]:
            raise AssertionError('archive parents differ from the issued pieces')

        expected_history = {**expected_old, 'piece_ids': expected_parents}
        actual_history = {**_result(old_copy), 'piece_ids': _parent_ids(old_copy)}
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v5',
            'input': {
                'left_hot_windows': [['0', '1'], ['2', '3']],
                'right_hot_windows': [['3', '5']],
                'threshold': '4', 'lag_window': ['-4', '1'],
                'piece_ids': expected_parents,
                'source_paths_available': [source_a.exists(), source_b.exists()],
            },
            'expected': expected_old,
            'actual': _result(old),
            'downstream_expected': expected_history,
            'downstream_actual': actual_history,
            'code_paths': ['issue/evidence.py', 'review/overlap.py', 'archive/publish.py', 'archive/export.py'],
            'oracle': 'Hand-translate the two-minute right window across the two one-minute left windows and their one-minute gap.',
        }, sort_keys=True))
        print(json.dumps({'original': _report_json(old_copy), 'corrected': _report_json(current_copy)}, sort_keys=True))
        run_stop_demo(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Review furnace evidence after station handoff.')
    commands = parser.add_subparsers(dest='command')
    signing = commands.add_parser('sign')
    signing.add_argument('archive', type=Path)
    signing.add_argument('left', type=Path)
    signing.add_argument('right', type=Path)
    signing.add_argument('--threshold', required=True)
    signing.add_argument('--lag-min', required=True)
    signing.add_argument('--lag-max', required=True)
    reading = commands.add_parser('read')
    reading.add_argument('archive', type=Path)
    reading.add_argument('report_id')
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            run_demo()
        elif args.command == 'sign':
            left_bytes, right_bytes = args.left.read_bytes(), args.right.read_bytes()
            with closing(sqlite3.connect(args.archive)) as db:
                initialize_archive(db)
                publication = sign(db, left_bytes, right_bytes, args.threshold, args.lag_min, args.lag_max)
            print(json.dumps(_report_json(publication), sort_keys=True))
        else:
            with closing(sqlite3.connect(args.archive.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                publication = read(db, args.report_id)
            print(json.dumps(_report_json(publication), sort_keys=True))
    except (LookupError, ValueError, sqlite3.Error, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
