import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from archive.provenance import ParentPieceRef, initialize_parent_table, store_parents
from archive.receipts import PublicationReceipt, initialize_receipt_table, write_success_receipt
from archive.reports import SignedReport, initialize_report_table, insert_report


@dataclass(frozen=True)
class PublicationDraft:
    threshold: Fraction
    lag_min: Fraction
    lag_max: Fraction
    duration: Fraction
    optimal_lags: tuple[tuple[Fraction, Fraction], ...]
    parents: tuple[ParentPieceRef, ParentPieceRef]


@dataclass(frozen=True)
class PublishedReport:
    report: SignedReport
    parents: tuple[ParentPieceRef, ParentPieceRef]
    receipt: PublicationReceipt


def _enable_foreign_keys(db: sqlite3.Connection) -> None:
    if db.in_transaction:
        raise sqlite3.ProgrammingError('archive writes require an idle connection')
    db.execute('PRAGMA foreign_keys = ON')


def initialize_archive(db: sqlite3.Connection) -> None:
    _enable_foreign_keys(db)
    db.execute('BEGIN IMMEDIATE')
    with db:
        initialize_report_table(db)
        initialize_parent_table(db)
        initialize_receipt_table(db)


def publish_report(db: sqlite3.Connection, draft: PublicationDraft) -> PublishedReport:
    _enable_foreign_keys(db)
    report = SignedReport(
        f'report-{uuid4().hex}', draft.threshold, draft.lag_min, draft.lag_max,
        draft.duration, draft.optimal_lags,
    )
    db.execute('BEGIN IMMEDIATE')
    with db:
        insert_report(db, report)
        store_parents(db, report.report_id, draft.parents)
        receipt = write_success_receipt(db, report.report_id)
    return PublishedReport(report, draft.parents, receipt)
