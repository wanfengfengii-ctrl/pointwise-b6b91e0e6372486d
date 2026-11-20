import sqlite3
from dataclasses import dataclass
from fractions import Fraction
from uuid import uuid4

from archive.provenance import ParentPieceRef, initialize_parent_table, store_parents
from archive.receipts import PublicationReceipt, initialize_receipt_table, write_success_receipt
from archive.reports import SignedReport, initialize_report_table, insert_report
from archive.stop_reports import (
    SignedStopReport,
    initialize_stop_tables,
    insert_stop_report,
    store_stop_parents,
    write_stop_receipt,
)


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


@dataclass(frozen=True)
class StopPublicationDraft:
    batch_id: str
    threshold: Fraction
    dwell: Fraction
    tolerance: Fraction
    lag_min: Fraction
    lag_max: Fraction
    max_pairs: int
    optimal_lags: tuple[tuple[Fraction, Fraction], ...]
    eligible_commands: tuple[tuple[tuple[str, Fraction], ...], tuple[tuple[str, Fraction], ...]]
    parents: tuple[ParentPieceRef, ParentPieceRef]


@dataclass(frozen=True)
class PublishedStopReport:
    report: SignedStopReport
    parents: tuple[ParentPieceRef, ParentPieceRef]
    receipt: PublicationReceipt

    def as_dict(self) -> dict:
        report = self.report
        return {
            'report_id': report.report_id,
            'batch_id': report.batch_id,
            'threshold': report.threshold,
            'dwell': report.dwell,
            'tolerance': report.tolerance,
            'lag_min': report.lag_min,
            'lag_max': report.lag_max,
            'max_pairs': report.max_pairs,
            'optimal_lags': report.optimal_lags,
            'eligible_commands': report.eligible_commands,
            'parents': self.parents,
            'receipt': self.receipt,
        }


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
        initialize_stop_tables(db)


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


def publish_stop_report(db: sqlite3.Connection, draft: StopPublicationDraft) -> PublishedStopReport:
    _enable_foreign_keys(db)
    report = SignedStopReport(
        f'report-{uuid4().hex}', draft.batch_id, draft.threshold, draft.dwell, draft.tolerance,
        draft.lag_min, draft.lag_max, draft.max_pairs, draft.optimal_lags, draft.eligible_commands,
    )
    db.execute('BEGIN IMMEDIATE')
    with db:
        insert_stop_report(db, report)
        store_stop_parents(db, report.report_id, draft.parents)
        receipt = write_stop_receipt(db, report.report_id)
    return PublishedStopReport(report, draft.parents, receipt)
