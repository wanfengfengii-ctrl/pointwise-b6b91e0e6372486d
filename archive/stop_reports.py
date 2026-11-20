import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from archive.provenance import ParentPieceRef
from archive.receipts import PublicationReceipt


@dataclass(frozen=True)
class SignedStopReport:
    report_id: str
    batch_id: str
    threshold: Fraction
    dwell: Fraction
    tolerance: Fraction
    lag_min: Fraction
    lag_max: Fraction
    max_pairs: int
    optimal_lags: tuple[tuple[Fraction, Fraction], ...]
    eligible_commands: tuple[tuple[tuple[str, Fraction], ...], tuple[tuple[str, Fraction], ...]]


def initialize_stop_tables(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS signed_stop_reports (
            report_id TEXT PRIMARY KEY NOT NULL,
            batch_id TEXT NOT NULL,
            threshold TEXT NOT NULL,
            dwell TEXT NOT NULL,
            tolerance TEXT NOT NULL,
            lag_min TEXT NOT NULL,
            lag_max TEXT NOT NULL,
            max_pairs INTEGER NOT NULL,
            optimal_lags_json TEXT NOT NULL,
            eligible_left_json TEXT NOT NULL,
            eligible_right_json TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS stop_report_parents (
            report_id TEXT NOT NULL REFERENCES signed_stop_reports(report_id),
            position INTEGER NOT NULL CHECK (position IN (0, 1)),
            station_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            piece_id TEXT NOT NULL,
            PRIMARY KEY (report_id, position),
            UNIQUE (report_id, station_id),
            UNIQUE (report_id, piece_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS stop_publication_receipts (
            report_id TEXT PRIMARY KEY NOT NULL REFERENCES signed_stop_reports(report_id),
            receipt_id TEXT UNIQUE NOT NULL
        )
    ''')


def insert_stop_report(db: sqlite3.Connection, report: SignedStopReport) -> None:
    intervals = json.dumps([[str(start), str(end)] for start, end in report.optimal_lags])
    eligible = [
        json.dumps([[command_id, str(moment)] for command_id, moment in side])
        for side in report.eligible_commands
    ]
    db.execute('''
        INSERT INTO signed_stop_reports (
            report_id, batch_id, threshold, dwell, tolerance, lag_min, lag_max,
            max_pairs, optimal_lags_json, eligible_left_json, eligible_right_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        report.report_id, report.batch_id, str(report.threshold), str(report.dwell),
        str(report.tolerance), str(report.lag_min), str(report.lag_max), report.max_pairs,
        intervals, eligible[0], eligible[1],
    ))


def load_stop_report(db: sqlite3.Connection, report_id: str) -> SignedStopReport:
    row = db.execute('''
        SELECT batch_id, threshold, dwell, tolerance, lag_min, lag_max,
               max_pairs, optimal_lags_json, eligible_left_json, eligible_right_json
        FROM signed_stop_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise KeyError(f'unknown stop report: {report_id}')
    (batch_id, threshold, dwell, tolerance, lag_min, lag_max, max_pairs,
     intervals, left_json, right_json) = row
    eligible = tuple(
        tuple((command_id, Fraction(moment)) for command_id, moment in json.loads(payload))
        for payload in (left_json, right_json)
    )
    return SignedStopReport(
        report_id, batch_id, Fraction(threshold), Fraction(dwell), Fraction(tolerance),
        Fraction(lag_min), Fraction(lag_max), int(max_pairs),
        tuple((Fraction(start), Fraction(end)) for start, end in json.loads(intervals)),
        eligible,
    )


def store_stop_parents(
    db: sqlite3.Connection, report_id: str, parents: tuple[ParentPieceRef, ParentPieceRef]
) -> None:
    if len(parents) != 2:
        raise ValueError('a signed stop report requires two parents')
    db.executemany('''
        INSERT INTO stop_report_parents (report_id, position, station_id, revision_id, piece_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        (report_id, position, parent.station_id, parent.revision_id, parent.piece_id)
        for position, parent in enumerate(parents)
    ))


def load_stop_parents(db: sqlite3.Connection, report_id: str) -> tuple[ParentPieceRef, ParentPieceRef]:
    rows = db.execute('''
        SELECT station_id, revision_id, piece_id FROM stop_report_parents
        WHERE report_id = ? ORDER BY position
    ''', (report_id,)).fetchall()
    if len(rows) != 2:
        raise sqlite3.DatabaseError(f'incomplete parents for stop report: {report_id}')
    return ParentPieceRef(*rows[0]), ParentPieceRef(*rows[1])


def write_stop_receipt(db: sqlite3.Connection, report_id: str) -> PublicationReceipt:
    receipt = PublicationReceipt(report_id, f'signed-{uuid4().hex}')
    db.execute(
        'INSERT INTO stop_publication_receipts (report_id, receipt_id) VALUES (?, ?)',
        (receipt.report_id, receipt.receipt_id),
    )
    return receipt


def load_stop_receipt(db: sqlite3.Connection, report_id: str) -> PublicationReceipt:
    row = db.execute(
        'SELECT receipt_id FROM stop_publication_receipts WHERE report_id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise sqlite3.DatabaseError(f'missing success receipt for stop report: {report_id}')
    return PublicationReceipt(report_id, row[0])
