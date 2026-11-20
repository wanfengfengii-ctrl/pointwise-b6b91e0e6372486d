import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class SignedReport:
    report_id: str
    threshold: Fraction
    lag_min: Fraction
    lag_max: Fraction
    duration: Fraction
    optimal_lags: tuple[tuple[Fraction, Fraction], ...]


def initialize_report_table(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS signed_reports (
            report_id TEXT PRIMARY KEY NOT NULL,
            threshold TEXT NOT NULL,
            lag_min TEXT NOT NULL,
            lag_max TEXT NOT NULL,
            duration TEXT NOT NULL,
            optimal_lags_json TEXT NOT NULL
        )
    ''')


def insert_report(db: sqlite3.Connection, report: SignedReport) -> None:
    intervals = json.dumps([[str(start), str(end)] for start, end in report.optimal_lags])
    db.execute('''
        INSERT INTO signed_reports (report_id, threshold, lag_min, lag_max, duration, optimal_lags_json)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        report.report_id, str(report.threshold), str(report.lag_min), str(report.lag_max),
        str(report.duration), intervals,
    ))


def load_report(db: sqlite3.Connection, report_id: str) -> SignedReport:
    row = db.execute('''
        SELECT threshold, lag_min, lag_max, duration, optimal_lags_json
        FROM signed_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise KeyError(f'unknown report: {report_id}')
    threshold, lag_min, lag_max, duration, intervals = row
    return SignedReport(
        report_id, Fraction(threshold), Fraction(lag_min), Fraction(lag_max), Fraction(duration),
        tuple((Fraction(start), Fraction(end)) for start, end in json.loads(intervals)),
    )
