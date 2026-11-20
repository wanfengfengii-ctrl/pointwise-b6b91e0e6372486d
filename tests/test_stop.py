import json
import sqlite3
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.export import read, read_stop
from archive.publish import initialize_archive
from intake.segments import AffineSegment
from issue.codec import decode_stop_piece
from issue.receipts import issue_stop
from review.assemble import sign, sign_stop
from revision.correction import Correction
from revision.freeze import freeze
from stop_examples import CASES, SOURCES
from tests.fixtures import independent_piece, prepare_station


BATCH_ID = 'coil-stop-01'
STEADY_AFFINE = [['-4', '12', '0', '5']]


def raw_stop_piece(station_id, piece_id, body, revision_id=None):
    envelope = {
        'version': 2,
        'station_id': station_id,
        'revision_id': revision_id or f'rev-{piece_id}',
        'piece_id': piece_id,
        'body': body,
    }
    return json.dumps(envelope).encode('utf-8')


def stop_body(commands=(), affine=(), batch_id=BATCH_ID):
    return {
        'batch_id': batch_id,
        'commands': [list(row) for row in commands],
        'affine': [list(row) for row in affine],
    }


def case_pieces(case):
    with closing(sqlite3.connect(':memory:')) as left_db, closing(sqlite3.connect(':memory:')) as right_db:
        left_revision = prepare_station(left_db, 'A', SOURCES[case['left']['source']]['rows'])
        right_revision = prepare_station(right_db, 'B', SOURCES[case['right']['source']]['rows'])
        left_piece = issue_stop(left_db, 'A', left_revision.revision_id, case['batch_id'], case['left']['commands'])
        right_piece = issue_stop(right_db, 'B', right_revision.revision_id, case['batch_id'], case['right']['commands'])
    return left_piece, right_piece


def stop_counts(db):
    tables = ('signed_stop_reports', 'stop_report_parents', 'stop_publication_receipts')
    return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables)


def as_fraction_rows(rows):
    return tuple((command_id, Fraction(moment)) for command_id, moment in rows)


class TestStopExamples(unittest.TestCase):
    EXPECTED_ELIGIBLE = {
        'shared-command': ((('a0', 0), ('a1', 1)), (('b0', 0),)),
        'empty-log': ((('a0', 0), ('a1', 1)), ()),
        'missing-evidence': ((('a0', 0), ('a1', 1)), ()),
        'touching-at-zero': ((('a0', 0), ('a1', 10)), (('b0', 1), ('b1', 9))),
        'split-optimum': ((('a0', 0),), (('b0', -3), ('b1', 0))),
        'excluded-right-end': ((('a0', 0), ('a1', 1)), (('b0', 0),)),
    }

    def test_cases(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                left_piece, right_piece = case_pieces(case)
                with closing(sqlite3.connect(':memory:')) as center:
                    initialize_archive(center)
                    result = sign_stop(center, left_piece, right_piece, **case['request'])
                    self.assertEqual(result['max_pairs'], case['expected']['max_pairs'])
                    self.assertEqual(result['optimal_lags'], tuple(
                        (Fraction(low), Fraction(high)) for low, high in case['expected']['optimal_lags']
                    ))
                    expected_left, expected_right = self.EXPECTED_ELIGIBLE[case['name']]
                    self.assertEqual(result['eligible_commands'], (
                        as_fraction_rows(expected_left), as_fraction_rows(expected_right),
                    ))
                    self.assertEqual(result['batch_id'], case['batch_id'])
                    self.assertEqual([parent.station_id for parent in result['parents']], ['A', 'B'])
                    self.assertEqual(result['receipt'].report_id, result['report_id'])
                    self.assertEqual(read_stop(center, result['report_id']), result)


class TestStopIssuance(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(closing(sqlite3.connect(':memory:')))
        self.revision = prepare_station(self.db, 'B', SOURCES['steady']['rows'])

    def issue(self, commands=(('b0', 0),), batch_id=BATCH_ID):
        return issue_stop(self.db, 'B', self.revision.revision_id, batch_id, commands)

    def test_piece_format_and_order(self):
        piece = self.issue((('b1', '1/2'), ('b0', 0), ('b2', -4)))
        envelope = decode_stop_piece(piece)
        self.assertEqual((envelope.station_id, envelope.revision_id), ('B', self.revision.revision_id))
        self.assertEqual(envelope.body, {
            'batch_id': BATCH_ID,
            'commands': [['b1', '1/2'], ['b0', '0'], ['b2', '-4']],
            'affine': STEADY_AFFINE,
        })
        again = self.issue()
        self.assertNotEqual(decode_stop_piece(again).piece_id, envelope.piece_id)

    def test_empty_commands(self):
        piece = self.issue(())
        self.assertEqual(decode_stop_piece(piece).body['commands'], [])

    def test_unknown_revision(self):
        with self.assertRaises(KeyError):
            issue_stop(self.db, 'B', 'unknown', BATCH_ID, ())
        with self.assertRaises(KeyError):
            issue_stop(self.db, 'A', self.revision.revision_id, BATCH_ID, ())

    def test_invalid_commands(self):
        invalid = (
            'not-a-list',
            [('b0',)],
            [('b0', 0, 0)],
            [42],
            [('', 0)],
            [('b0', 0), ('b0', 1)],
            [('b0', '1/0')],
            [('b0', 0.5)],
            [('b0', True)],
        )
        for commands in invalid:
            with self.subTest(commands=commands):
                with self.assertRaises(ValueError):
                    self.issue(commands)
        with self.assertRaises(ValueError):
            self.issue(batch_id='')


class TestStopAdmission(unittest.TestCase):
    def setUp(self):
        self.center = self.enterContext(closing(sqlite3.connect(':memory:')))
        initialize_archive(self.center)
        self.left = raw_stop_piece('A', 'a', stop_body([['a0', '0']], STEADY_AFFINE))
        self.right = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE))

    def sign(self, left=None, right=None, request=(5, 1, 1, 0, 0)):
        return sign_stop(self.center, left or self.left, right or self.right, *request)

    def test_documented_piece(self):
        documented = (
            b'{"version":2,"station_id":"B","revision_id":"rev-demo-b","piece_id":"piece-demo-b",'
            b'"body":{"batch_id":"coil-stop-01","commands":[["b0","0"]],"affine":[["-4","12","0","5"]]}}'
        )
        result = self.sign(right=documented)
        self.assertEqual(result['max_pairs'], 1)
        self.assertEqual(result['batch_id'], BATCH_ID)
        self.assertEqual([parent.piece_id for parent in result['parents']], ['a', 'piece-demo-b'])
        self.assertEqual([parent.revision_id for parent in result['parents']], ['rev-a', 'rev-demo-b'])

    def test_result_members(self):
        result = self.sign()
        self.assertEqual(result['threshold'], Fraction(5))
        self.assertEqual(result['dwell'], Fraction(1))
        self.assertEqual(result['tolerance'], Fraction(1))
        self.assertEqual((result['lag_min'], result['lag_max']), (Fraction(0), Fraction(0)))
        self.assertIsInstance(result['max_pairs'], int)
        self.assertEqual(result['optimal_lags'], ((Fraction(0), Fraction(0)),))
        self.assertEqual(result['eligible_commands'], (
            (('a0', Fraction(0)),), (('b0', Fraction(0)),),
        ))
        self.assertEqual(result['receipt'].report_id, result['report_id'])

    def _assert_rejected(self, left, right, request=(5, 1, 1, 0, 0)):
        with self.assertRaises(ValueError):
            sign_stop(self.center, left, right, *request)
        self.assertEqual(stop_counts(self.center), (0, 0, 0))

    def test_mixed_versions(self):
        v1 = independent_piece('B', 'b-v1', [(-4, 12, 0, 5)])
        self._assert_rejected(self.left, v1)
        v2 = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE))
        with self.assertRaises(ValueError):
            sign(self.center, independent_piece('A', 'a-v1', [(-4, 12, 0, 5)]), v2, 4, 0, 0)

    def test_batch_mismatch(self):
        right = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE, batch_id='coil-stop-02'))
        self._assert_rejected(self.left, right)

    def test_same_station_and_piece(self):
        same_station = raw_stop_piece('A', 'b', stop_body([['b0', '0']], STEADY_AFFINE))
        self._assert_rejected(self.left, same_station)
        self._assert_rejected(self.left, self.left)

    def test_bad_envelope(self):
        self._assert_rejected(self.left, 'not-bytes')
        self._assert_rejected(self.left, b'{"version":2,"version":2}')
        incomplete = json.loads(self.right)
        del incomplete['piece_id']
        self._assert_rejected(self.left, json.dumps(incomplete).encode())
        wrong_version = json.loads(self.right)
        wrong_version['version'] = 3
        self._assert_rejected(self.left, json.dumps(wrong_version).encode())

    def test_bad_body(self):
        missing_field = raw_stop_piece('B', 'b', {'batch_id': BATCH_ID, 'commands': []})
        self._assert_rejected(self.left, missing_field)
        extra_field = raw_stop_piece('B', 'b', {**stop_body(), 'note': 'x'})
        self._assert_rejected(self.left, extra_field)
        duplicate_commands = raw_stop_piece('B', 'b', stop_body([['b0', '0'], ['b0', '1']], STEADY_AFFINE))
        self._assert_rejected(self.left, duplicate_commands)
        bad_command_row = raw_stop_piece('B', 'b', stop_body([['b0']], STEADY_AFFINE))
        self._assert_rejected(self.left, bad_command_row)

    def test_bad_affine(self):
        overlapping = raw_stop_piece('B', 'b', stop_body([['b0', '0']], [['-4', '2', '0', '5'], ['1', '12', '0', '5']]))
        self._assert_rejected(self.left, overlapping)
        empty_segment = raw_stop_piece('B', 'b', stop_body([['b0', '0']], [['1', '1', '0', '5']]))
        self._assert_rejected(self.left, empty_segment)
        short_row = raw_stop_piece('B', 'b', stop_body([['b0', '0']], [['-4', '12', '0']]))
        self._assert_rejected(self.left, short_row)

    def test_invalid_request(self):
        invalid_requests = (
            (5, 0, 1, 0, 0),
            (5, -1, 1, 0, 0),
            (5, 1, -1, 0, 0),
            (5, 1, 1, 1, 0),
            ('1/0', 1, 1, 0, 0),
            (5, 'soon', 1, 0, 0),
            (5, 1, 1, 0.5, 1),
            (5, 1, True, 0, 0),
        )
        for request in invalid_requests:
            with self.subTest(request=request):
                self._assert_rejected(self.left, self.right, request)


class TestStopAnalysis(unittest.TestCase):
    def setUp(self):
        self.center = self.enterContext(closing(sqlite3.connect(':memory:')))
        initialize_archive(self.center)

    def sign_pair(self, left_commands, right_commands, request, left_affine=None, right_affine=None):
        left = raw_stop_piece('A', 'a', stop_body(left_commands, left_affine if left_affine is not None else STEADY_AFFINE))
        right = raw_stop_piece('B', 'b', stop_body(right_commands, right_affine if right_affine is not None else STEADY_AFFINE))
        return sign_stop(self.center, left, right, *request)

    def test_interval_optimum(self):
        result = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 1, 1, -2, 2))
        self.assertEqual(result['max_pairs'], 1)
        self.assertEqual(result['optimal_lags'], ((Fraction(-1), Fraction(1)),))

    def test_zero_tolerance(self):
        result = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 1, 0, -1, 1))
        self.assertEqual((result['max_pairs'], result['optimal_lags']), (1, ((Fraction(0), Fraction(0)),)))

    def test_split_intervals(self):
        result = self.sign_pair([['a0', '0'], ['a1', '10']], [['b0', '0']], (5, 1, 1, -12, 12))
        self.assertEqual(result['max_pairs'], 1)
        self.assertEqual(result['optimal_lags'], ((Fraction(-1), Fraction(1)), (Fraction(9), Fraction(11))))

    def test_same_time_commands(self):
        result = self.sign_pair([['a0', '0'], ['a1', '0']], [['b0', '0'], ['b1', '0']], (5, 1, 0, 0, 0))
        self.assertEqual(result['max_pairs'], 2)
        limited = self.sign_pair([['a0', '0'], ['a1', '0']], [['b0', '0']], (5, 1, 0, 0, 0))
        self.assertEqual(limited['max_pairs'], 1)

    def test_zero_pairs_whole_window(self):
        result = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 1, 0, 5, 7))
        self.assertEqual((result['max_pairs'], result['optimal_lags']), (0, ((Fraction(5), Fraction(7)),)))
        empty_affine = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 1, 1, -2, 2), right_affine=[])
        self.assertEqual((empty_affine['max_pairs'], empty_affine['optimal_lags']), (0, ((Fraction(-2), Fraction(2)),)))

    def test_threshold_equality(self):
        equal = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 1, 1, 0, 0))
        self.assertEqual(equal['max_pairs'], 1)
        below = self.sign_pair([['a0', '0']], [['b0', '0']], ('9/2', 1, 1, 0, 0))
        self.assertEqual(below['max_pairs'], 0)
        self.assertEqual(below['eligible_commands'], ((), ()))

    def test_sloped_affine(self):
        sloped = [['0', '4', '1', '0']]
        result = self.sign_pair(
            [['a0', '0'], ['a1', '1'], ['a2', '2']], [['b0', '0']], (2, 2, 0, 0, 0), left_affine=sloped,
        )
        self.assertEqual(result['eligible_commands'][0], (('a0', Fraction(0)),))
        self.assertEqual(result['max_pairs'], 0)

    def test_gap_and_adjacent_segments(self):
        adjacent = [['0', '1', '0', '5'], ['1', '4', '0', '5']]
        covered = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 2, 0, 0, 0), left_affine=adjacent)
        self.assertEqual(covered['eligible_commands'][0], (('a0', Fraction(0)),))
        gapped = [['0', '1', '0', '5'], ['2', '4', '0', '5']]
        broken = self.sign_pair([['a0', '0']], [['b0', '0']], (5, 2, 0, 0, 0), left_affine=gapped)
        self.assertEqual(broken['eligible_commands'][0], ())

    def test_lag_shifts_right_side(self):
        left = raw_stop_piece('A', 'a', stop_body([['a0', '3']], STEADY_AFFINE))
        right = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE))
        forward = sign_stop(self.center, left, right, 5, 1, 0, 3, 3)
        self.assertEqual(forward['max_pairs'], 1)
        reverse = sign_stop(self.center, right, left, 5, 1, 0, -3, -3)
        self.assertEqual(reverse['max_pairs'], 1)
        self.assertEqual([parent.piece_id for parent in reverse['parents']], ['b', 'a'])


class TestStopArchive(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.archive = self.root / 'stop-review.sqlite'
        self.left = raw_stop_piece('A', 'a', stop_body([['a0', '0']], STEADY_AFFINE))
        self.right = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE))

    def test_reopen_and_kind_separation(self):
        with closing(sqlite3.connect(self.archive)) as db:
            initialize_archive(db)
            v1_left = independent_piece('A', 'a-v1', [(-4, 12, 0, 5)])
            v1_right = independent_piece('B', 'b-v1', [(-4, 12, 0, 5)])
            v1 = sign(db, v1_left, v1_right, 4, 0, 0)
            stop = sign_stop(db, self.left, self.right, 5, 1, 1, 0, 0)
            with self.assertRaises(KeyError):
                read_stop(db, v1.report.report_id)
            with self.assertRaises(KeyError):
                read(db, stop['report_id'])
            with self.assertRaises(KeyError):
                read_stop(db, 'missing')
            with self.assertRaises(ValueError):
                read_stop(db, '')
        with closing(sqlite3.connect(self.archive)) as db:
            self.assertEqual(read(db, v1.report.report_id), v1)
            self.assertEqual(read_stop(db, stop['report_id']), stop)
            self.assertEqual(stop_counts(db), (1, 2, 1))

    def test_correction_keeps_old_report(self):
        with closing(sqlite3.connect(':memory:')) as left_db, closing(sqlite3.connect(':memory:')) as right_db:
            left_revision = prepare_station(left_db, 'A', SOURCES['steady']['rows'])
            right_revision = prepare_station(right_db, 'B', SOURCES['missing']['rows'])
            left_piece = issue_stop(left_db, 'A', left_revision.revision_id, BATCH_ID, (('a0', 0), ('a1', 1)))
            right_piece = issue_stop(right_db, 'B', right_revision.revision_id, BATCH_ID, (('b0', 0),))
            with closing(sqlite3.connect(self.archive)) as center:
                initialize_archive(center)
                old = sign_stop(center, left_piece, right_piece, 5, 1, 1, 0, 0)
                self.assertEqual(old['max_pairs'], 0)
                corrected = freeze(right_db, 'B', parent_revision_id=right_revision.revision_id, correction=Correction(
                    Fraction(1, 2), Fraction(3, 4),
                    (AffineSegment(Fraction(1, 2), Fraction(3, 4), 5, 5),),
                    'restored constant-five backup',
                ))
                corrected_piece = issue_stop(right_db, 'B', corrected.revision_id, BATCH_ID, (('b0', 0),))
                new = sign_stop(center, left_piece, corrected_piece, 5, 1, 1, 0, 0)
                self.assertEqual(new['max_pairs'], 1)
                self.assertEqual(new['eligible_commands'][1], (('b0', Fraction(0)),))
                self.assertNotEqual(old['report_id'], new['report_id'])
                self.assertEqual(read_stop(center, old['report_id']), old)
                self.assertEqual(read_stop(center, new['report_id']), new)
        with closing(sqlite3.connect(self.archive)) as center:
            archived_old = read_stop(center, old['report_id'])
            self.assertEqual(archived_old['max_pairs'], 0)
            self.assertEqual(archived_old, old)


class TestStopPublication(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.archive = self.root / 'stop-review.sqlite'
        self.left = raw_stop_piece('A', 'a', stop_body([['a0', '0']], STEADY_AFFINE))
        self.right = raw_stop_piece('B', 'b', stop_body([['b0', '0']], STEADY_AFFINE))
        with closing(sqlite3.connect(self.archive)) as db:
            initialize_archive(db)
            self.old = sign_stop(db, self.left, self.right, 5, 1, 1, 0, 0)
            self._install_commit_failure(db)

    def _install_commit_failure(self, db):
        # The trigger writes a deferred foreign-key violation during receipt
        # insertion. SQLite detects it only when the real transaction commits.
        db.execute('CREATE TABLE stop_commit_permissions (id INTEGER PRIMARY KEY)')
        db.execute('''
            CREATE TABLE stop_commit_gate (
                report_id TEXT NOT NULL REFERENCES signed_stop_reports(report_id),
                permission INTEGER NOT NULL REFERENCES stop_commit_permissions(id) DEFERRABLE INITIALLY DEFERRED
            )
        ''')
        db.execute('''
            CREATE TRIGGER reject_stop_commit AFTER INSERT ON stop_publication_receipts
            BEGIN
                INSERT INTO stop_commit_gate (report_id, permission) VALUES (NEW.report_id, 1);
            END
        ''')

    def _check_unchanged(self, db):
        self.assertEqual(stop_counts(db), (1, 2, 1))
        self.assertEqual(db.execute('SELECT report_id FROM stop_commit_gate').fetchall(), [])
        self.assertEqual(read_stop(db, self.old['report_id']), self.old)

    def test_failed_commit(self):
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                sign_stop(db, self.left, self.right, 5, 1, 1, -1, 1)
            self.assertFalse(db.in_transaction)
            self._check_unchanged(db)
        with closing(sqlite3.connect(self.archive)) as db:
            self._check_unchanged(db)

    def test_retry_after_rollback(self):
        with closing(sqlite3.connect(self.archive)) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
                sign_stop(db, self.left, self.right, 5, 1, 1, -1, 1)
        with closing(sqlite3.connect(self.archive)) as db:
            self._check_unchanged(db)
            db.execute('DROP TRIGGER reject_stop_commit')
            new = sign_stop(db, self.left, self.right, 5, 1, 1, -1, 1)
        with closing(sqlite3.connect(self.archive)) as db:
            self.assertEqual(stop_counts(db), (2, 4, 2))
            self.assertEqual(read_stop(db, self.old['report_id']), self.old)
            self.assertEqual(read_stop(db, new['report_id']), new)
            self.assertEqual(new['receipt'].report_id, new['report_id'])
            self.assertEqual([parent.piece_id for parent in new['parents']], ['a', 'b'])
            self.assertEqual(new['max_pairs'], 1)
            self.assertEqual(new['optimal_lags'], ((Fraction(-1), Fraction(1)),))


if __name__ == '__main__':
    unittest.main()
